"""Evidence-bound editorial admission and notes, before snapshot export."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Literal
from urllib.parse import urlparse, parse_qs

import httpx
from pydantic import BaseModel, ConfigDict, Field
from selectolax.parser import HTMLParser

from news_collector.pipeline.extract import extract_text_from_html
from news_collector.pipeline.structured_output import review_schema
from news_collector.pipeline.edition_audit import StoryAuditReview
from news_collector.pipeline.images import download
from news_collector.pipeline.publishers import publisher, limit_publishers
from news_collector.utils import parse_datetime
from news_collector.pipeline.publication_history import load_history, history_hash, prior_match
from zoneinfo import ZoneInfo

POLICY_VERSION = "editorial-v1"
PROFILE_PATH = Path(__file__).resolve().parents[2] / "config/editorial-profile.json"


def reader_profile():
    profile = json.loads(PROFILE_PATH.read_text())
    if profile.get("version") != 1 or not profile.get("priorityDesks") or not profile.get("selectionPrinciples"):
        raise ValueError("Editorial reader profile is missing or invalid")
    return profile
LONGFORM = {"lenny", "dwarkesh", "interconnects", "latent_space", "simon_willison", "bytebytego"}
BLOCKED_HOSTS = {"producthunt.com", "marketbeat.com", "marketscreener.com", "accessnewswire.com",
                 "globenewswire.com", "prnewswire.com", "kalkine.com.au", "intellectia.ai",
                 "tickerreport.com", "themarketsdaily.com"}
PROMO = re.compile(r"\b(sponsored|partner content|coupon|promo code|deals of the|best deals|buy rating|price target|stock unloaded|takes .* position|average rating|stock rating|here.s how much|invested.*years ago)\b", re.I)


class NoteSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heading: str
    body: str
    evidence: list[str]


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    decision: Literal["admit", "hold", "reject"]
    quality: int = Field(ge=0, le=100)
    importance: int = Field(ge=0, le=100)
    kind: Literal["reporting", "analysis", "podcast", "announcement"]
    reason: str
    headline: str
    summary: str
    points: list[str]
    sections: list[NoteSection]
    caveats: list[str]
    evidence: list[str]
    duplicate_of: str | None
    sector: Literal["Technology", "AI", "Markets", "Economy", "Deals & regulation", "World", "Policy", "Science & health", "Reading room", "Listening room"] | None = None


class ReviewBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisions: list[Decision]


class SelectionRejection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    reason: str


class EditionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected_ids: list[str]
    excluded: list[SelectionRejection]


class ExternalReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestHash: str
    reviewer: str = Field(min_length=1)
    reviewedAt: datetime
    decisions: list[Decision]
    selection: EditionSelection


def validate_external_review(payload, request_hash, pending_packets, now):
    reviewed = ExternalReview.model_validate(payload)
    if reviewed.requestHash != request_hash:
        raise ValueError("Review file does not match current source packets and policy")
    if reviewed.reviewedAt.tzinfo is None or not timedelta(minutes=-5) <= now - reviewed.reviewedAt <= timedelta(hours=24):
        raise ValueError("Review file must have a current timezone-aware review timestamp")
    validate_decisions(ReviewBatch(decisions=reviewed.decisions), pending_packets)
    validate_ranking_review(reviewed.decisions, pending_packets)
    return reviewed


def validate_ranking_review(decisions, packets):
    """Catch bulk priority dismissals before they can bypass the final edition desk."""
    known = {packet["id"]: packet for packet in packets}
    blanket = Counter()
    for decision in decisions:
        packet = known[decision.id]
        if (decision.decision == "hold" and decision.quality == decision.importance == 0
                and not decision.duplicate_of and packet["wordCount"] >= 200
                and not packet.get("truncated")
                and re.search(r"lower incremental value|lower priority|less important|more consequential event|edition screening",
                              decision.reason, re.I)):
            blanket[re.sub(r"\s+", " ", decision.reason.strip().lower())] += 1
    if any(count >= 4 for count in blanket.values()):
        raise ValueError("Blanket ranking holds on substantive evidence require item-specific review and scoring before selection")


def clean_text(value):
    parser = HTMLParser(value or "")
    for node in parser.css("script,style,nav,footer,form"):
        node.decompose()
    return re.sub(r"[ \t]+", " ", parser.text(separator="\n")).strip()


def audio_url(raw):
    links = [*raw.get("enclosures", []), *raw.get("links", [])]
    return next((e.get("href") or e.get("url") for e in links
                 if e.get("type", "").startswith("audio/")), None)


def exclusion(row, now):
    host = (urlparse(row["canonical_url"]).hostname or "").removeprefix("www.")
    if host in BLOCKED_HOSTS or row["source"] in {"producthunt", "x_search", "reddit", "alphavantage_movers"}:
        return "discovery_or_promotional_source"
    if PROMO.search(row["title"]):
        return "routine_alert_or_promotion"
    date = parse_datetime(row.get("published_at"))
    window = timedelta(days=30) if row["source"] in LONGFORM else timedelta(days=7) if row["source"] in {"sec_press", "federal_reserve", "doj_antitrust"} else timedelta(hours=48)
    if not date or date > now + timedelta(minutes=5) or date < now - window:
        return "outside_editorial_window"
    return None


def content_packet(row, repository, user_agent):
    raw = json.loads(row.get("raw_json") or "{}")
    published_at = row["published_at"]
    from news_collector.pipeline.publication_dates import needs_publisher_date
    newsletter_date = needs_publisher_date(row)
    if newsletter_date:
        from news_collector.pipeline.publication_dates import article_publication_date
        with httpx.Client(timeout=15, follow_redirects=False, headers={"User-Agent": user_agent}) as client:
            body, _ = download(client, row["url"], 3_000_000)
        date = article_publication_date(body.decode("utf-8", errors="replace"))
        if not date:
            raise ValueError("Newsletter discovery lacks a verified publisher publication date")
        published_at = date.isoformat()
        if exclusion({**row, "published_at": published_at}, datetime.now(timezone.utc)):
            raise ValueError("Original article date is outside the editorial window")
    text = clean_text(row.get("text") or row.get("summary"))
    audio = audio_url(raw)
    kind = "podcast" if audio and row["source"] in LONGFORM else raw.get("_editorial_type", "reporting")
    if kind == "podcast" and not audio:
        kind = "analysis"
    basis = "Publisher transcript" if audio and len(text.split()) > 2500 else "Publisher article" if len(text.split()) >= 400 else "Feed excerpt"
    if (len(text.split()) < 400 or row["source"] == "doj_antitrust") and kind != "podcast":
        cached = repository.get_cached_content(row["canonical_url"])
        checked = parse_datetime(cached.get("checked_at")) if cached else None
        fresh_cache = checked and timedelta(0) <= datetime.now(timezone.utc) - checked < timedelta(hours=6)
        cache_status = "editorial-full-doj-v2" if row["source"] == "doj_antitrust" else "editorial-full"
        if cached and cached.get("status") == cache_status and fresh_cache:
            text = cached["content_text"]
        else:
            try:
                with httpx.Client(timeout=15, follow_redirects=False, headers={"User-Agent": user_agent}) as client:
                    body, final_url = download(client, row["url"], 3_000_000)
                extracted = extract_text_from_html(body.decode("utf-8", errors="replace"), final_url) or ""
                if len(extracted.split()) > len(text.split()):
                    text = extracted
                    repository.set_cached_content(row["canonical_url"], text, datetime.now(timezone.utc).isoformat(), status=cache_status)
            except Exception:
                pass
        basis = "Publisher article" if len(text.split()) >= 400 else "Feed excerpt"
    duration = None
    if row["source"] == "theo_video":
        from youtube_transcript_api import YouTubeTranscriptApi
        video_id = parse_qs(urlparse(row["url"]).query).get("v", [None])[0]
        if not video_id:
            raise ValueError("No public long-form video transcript")
        transcript = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
        text = "\n".join(f"[{int(part.start) // 60:02d}:{int(part.start) % 60:02d}] {part.text}" for part in transcript)
        basis = "Public video captions"
    if audio and len(text.split()) < 2500:
        from news_collector.pipeline.podcasts import transcribe_episode
        transcript = transcribe_episode(audio, repository, user_agent)
        text, duration = transcript["text"], transcript["duration"]
        basis = "Machine transcript (full audio)"
    # Do not truncate long interviews: review every supplied transcript chunk.
    max_words = 45000 if kind == "podcast" or row["source"] == "theo_video" else 5000
    words = text.split()
    truncated = len(words) > max_words
    words = words[:max_words]
    chunks = [{"id": f"p{i // 350 + 1}", "text": " ".join(words[i:i + 350])} for i in range(0, len(words), 350)]
    return {"id": hashlib.sha256(row["canonical_url"].encode()).hexdigest()[:20],
            "inputHash": source_hash(row),
            "url": row["canonical_url"], "source": row["source"], "title": row["title"],
            "publishedAt": published_at, "kind": kind, "basis": basis,
            **({"publicationDateBasis": "publisher_metadata"} if newsletter_date else {}),
            "audio": audio, "duration": duration, "truncated": truncated, "chunks": chunks,
            "wordCount": len(words), "category": row["category"], "sector": raw.get("_edition_sector")}


def source_hash(row):
    return hashlib.sha256(json.dumps({k: row.get(k) for k in
        ["canonical_url", "title", "published_at", "text", "summary"]}, sort_keys=True).encode()).hexdigest()


def codex_review(packets, prompt_path, output_dir, result_type=ReviewBatch, *, allow_web=False, validate_result=None):
    from .editor_availability import quota_path, active_quota_block, record_quota_error
    quota_file = quota_path(output_dir)
    if active_quota_block(quota_file):
        raise RuntimeError("Editor account usage is exhausted; fund the account before retrying. See editor-quota.json")
    executable = shutil.which(os.environ.get("NEWS_EDITOR_CODEX_BIN", "codex"))
    if not executable:
        raise RuntimeError("Codex CLI required for editorial review. Previous paper retained.")
    with tempfile.TemporaryDirectory(prefix="news-editor-") as directory:
        root = Path(directory)
        schema = root / "schema.json"
        contract = review_schema(result_type)
        if issubclass(result_type, ReviewBatch):
            candidates = packets if isinstance(packets, list) else packets["packets"]
            contract["$defs"]["Decision"]["properties"]["id"]["enum"] = [p["id"] for p in candidates]
            refs = sorted({chunk["id"] for p in candidates for chunk in p["chunks"]})
            for name in ("Decision", "NoteSection"):
                evidence = contract["$defs"][name]["properties"]["evidence"]
                if refs:
                    evidence["items"]["enum"] = refs
                else:
                    evidence["maxItems"] = 0
        elif result_type is EditionSelection:
            ids = [p["id"] for p in packets["shortlist"]]
            contract = {"type": "object", "additionalProperties": False,
                        "properties": {
                            "selected_ids": {"type": "array", "maxItems": 28,
                                             "items": {"type": "string", **({"enum": ids} if ids else {})}},
                            "reasons": {"type": "object", "additionalProperties": False,
                                        "properties": {id: {"type": "string"} for id in ids}, "required": ids}},
                        "required": ["selected_ids", "reasons"]}
        elif result_type is StoryAuditReview:
            definitions = contract["$defs"]
            story_contracts = {}
            evidence = {p["id"]: [c["id"] for c in p["chunks"]] for p in packets["packets"]}
            for decision in packets["decisions"]:
                story = deepcopy(definitions["StoryAudit"])
                story["properties"]["id"]["enum"] = [decision["id"]]
                claim = deepcopy(definitions["ClaimCheck"])
                passages = [decision["headline"], decision["summary"], *decision["points"],
                            *decision.get("caveats", []),
                            *[text for section in decision["sections"] for text in (section["heading"], section["body"])]]
                claim["properties"]["passage"]["enum"] = list(dict.fromkeys(p for p in passages if p.strip()))
                refs = evidence[decision["id"]]
                for array in [claim["properties"]["evidence"], story["properties"]["materialUpdateEvidence"]]:
                    if refs:
                        array["items"]["enum"] = refs
                    else:
                        array["maxItems"] = 0
                story["properties"]["claims"]["items"] = claim
                story_contracts[decision["id"]] = story
            contract["properties"]["stories"] = {"type": "object", "additionalProperties": False,
                "properties": story_contracts, "required": list(story_contracts)}
        schema.write_text(json.dumps(contract))
        result_path = root / "review.json"
        command = [executable, "exec", "--ignore-user-config", "--ephemeral",
                   "--skip-git-repo-check", "--sandbox", "read-only", "-C", directory,
                   "--disable", "shell_tool", "--disable", "unified_exec", "--disable", "apps",
                   "--disable", "hooks", "--disable", "browser_use", "--disable", "computer_use",
                   "-c", 'web_search="live"' if allow_web else 'web_search="disabled"', "--output-schema", str(schema),
                   "-o", str(result_path), "-"]
        model = os.environ.get("NEWS_EDITOR_MODEL")
        if model:
            command[2:2] = ["--model", model]
        effort = os.environ.get("NEWS_EDITOR_REASONING_EFFORT")
        if effort:
            if effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
                raise ValueError("Invalid NEWS_EDITOR_REASONING_EFFORT")
            command[2:2] = ["-c", f'model_reasoning_effort="{effort}"']
        environment = {key: value for key, value in os.environ.items()
                       if key in {"PATH", "HOME", "TMPDIR", "CODEX_HOME", "SSL_CERT_FILE", "TERM"}}
        prompt = prompt_path.read_text() + "\nREADER EDITORIAL PROFILE:\n" + json.dumps(reader_profile()) + "\nUNTRUSTED SOURCE PACKETS:\n" + json.dumps(packets, ensure_ascii=False)
        if result_type is EditionSelection:
            prompt += ("\nOUTPUT FORMAT: Return selected_ids with at most 28 unique shortlist IDs, "
                       "plus a reasons object containing an editorial reason for EVERY shortlist ID, selected or excluded. "
                       "Do not return an excluded array; the application derives it from IDs absent from selected_ids.")
        elif result_type is StoryAuditReview:
            prompt += ("\nOUTPUT FORMAT: Return stories as an object keyed by every requested story ID. "
                       "Each claim passage must be one complete published block allowed by the schema. "
                       "Audit every factual assertion in each block; use multiple checks with the same passage "
                       "if its assertions have different verdicts. Cite only the supplied chunk IDs.")
        response_dir = Path(output_dir) / "responses"
        response_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256((prompt + schema.read_text()).encode()).hexdigest()
        feedback = ""
        for attempt in range(2):
            result_path.unlink(missing_ok=True)
            for transport_attempt in range(3):
                result_path.unlink(missing_ok=True)
                run = subprocess.run(command, input=prompt + feedback, text=True, capture_output=True, env=environment,
                                     timeout=600)
                transient = run.returncode and re.search(
                    r"^ERROR:.*(?:at capacity|rate limit|temporarily unavailable|overloaded)",
                    run.stderr[-2000:], flags=re.I | re.M)
                if not transient or transport_attempt == 2:
                    break
                delay = 20 * (transport_attempt + 1)
                print(f"Editor temporarily unavailable; retrying the same model in {delay}s", flush=True)
                time.sleep(delay)
            if run.returncode or not result_path.exists():
                record_quota_error(run.stderr, quota_file)
                raise RuntimeError(f"Editorial review failed (exit {run.returncode}); previous paper retained. {run.stderr[-400:]}")
            response = result_path.read_text()
            (response_dir / f"{prompt_path.stem}-{key}-{attempt}.json").write_text(response)
            try:
                if result_type is EditionSelection:
                    raw = json.loads(response)
                    reasons = raw.get("reasons") if isinstance(raw, dict) else None
                    if not isinstance(reasons, dict) or set(reasons) != {p["id"] for p in packets["shortlist"]}:
                        raise ValueError("Selection must contain exactly every shortlist ID")
                    if any(not isinstance(reason, str) for reason in reasons.values()):
                        raise ValueError("Each selection requires an editorial reason")
                    selected = raw.get("selected_ids")
                    if not isinstance(selected, list) or any(not isinstance(id, str) for id in selected):
                        raise ValueError("Selection requires a selected_ids list")
                    reviewed = result_type.model_validate({
                        "selected_ids": selected,
                        "excluded": [{"id": id, "reason": reason} for id, reason in reasons.items() if id not in selected]})
                elif result_type is StoryAuditReview:
                    raw = json.loads(response)
                    stories = raw.get("stories") if isinstance(raw, dict) else None
                    if not isinstance(stories, dict) or set(stories) != set(packets["auditStoryIds"]):
                        raise ValueError("Audit must return every requested story ID exactly once")
                    reviewed = result_type.model_validate({"stories": [stories[id] for id in packets["auditStoryIds"]]})
                else:
                    reviewed = result_type.model_validate_json(response)
                if isinstance(reviewed, ReviewBatch):
                    validate_decisions(reviewed, packets if isinstance(packets, list) else packets["packets"])
                elif isinstance(reviewed, EditionSelection):
                    validate_selection(reviewed, packets["shortlist"])
                if validate_result is not None:
                    validate_result(reviewed)
                return reviewed
            except ValueError as exc:
                if attempt:
                    raise
                feedback = ("\nVALIDATION FEEDBACK: The previous response failed the output contract: "
                            + str(exc)[:400] + ". Regenerate a complete response for every input ID. "
                            "Hold evidence-ineligible items; never relax the stated requirements.")
                print(f"Retrying review after output validation failed: {str(exc)[:400]}", flush=True)


def validate_selection(selection, shortlist):
    known = {s["id"] for s in shortlist}
    accounted = selection.selected_ids + [s.id for s in selection.excluded]
    if len(accounted) != len(set(accounted)) or set(accounted) != known or len(selection.selected_ids) > 28:
        raise ValueError("Final editorial selection must account for each item once, maximum 28. "
                         "Selected IDs must never appear in excluded, even with reason 'Selected'. "
                         f"Missing IDs: {sorted(known - set(accounted))}; "
                         f"unknown IDs: {sorted(set(accounted) - known)}")


def validate_decisions(reviewed, packets):
    known = {p["id"]: p for p in packets}
    if len(reviewed.decisions) != len(known) or {d.id for d in reviewed.decisions} != set(known):
        actual = [d.id for d in reviewed.decisions]
        raise ValueError("Review must decide every candidate exactly once; "
                         f"missing={sorted(set(known) - set(actual))}; "
                         f"unknown={sorted(set(actual) - set(known))}; "
                         f"repeated={sorted(k for k, count in Counter(actual).items() if count > 1)}")
    for decision in reviewed.decisions:
        packet = known[decision.id]
        refs = {c["id"] for c in packet["chunks"]}
        if decision.duplicate_of and decision.duplicate_of not in known:
            raise ValueError("Unknown duplicate reference")
        if not set(decision.evidence).issubset(refs) or any(not set(s.evidence).issubset(refs) for s in decision.sections):
            raise ValueError(f"Invalid evidence reference for {decision.id}; use only individual chunk IDs: {sorted(refs)}")
        if decision.decision == "admit":
            if not decision.evidence or not decision.summary or not decision.headline or packet["wordCount"] < 80:
                raise ValueError("Admitted story lacks evidence")
            if decision.quality < 65 or packet["truncated"]:
                raise ValueError(f"Admitted story fails quality/completeness gate: {decision.id} (quality={decision.quality}, truncated={packet['truncated']})")
            if packet["kind"] == "podcast" and (len(decision.sections) < 6 or packet["wordCount"] < 2500):
                raise ValueError("Podcast requires substantive transcript-based notes")
            if packet["kind"] == "podcast":
                cited = {int(ref[1:]) for section in decision.sections for ref in section.evidence}
                total = len(packet["chunks"])
                if not cited or min(cited) > max(2, total // 3) or max(cited) < total * .8:
                    raise ValueError("Podcast notes must cover the beginning and final part of the transcript")


def run_editorial(repository, settings, config, review_file=None, prepare_only=False):
    now = datetime.now(timezone.utc)
    validation_now = now
    output = settings.project_root.parent.parent / "data/editorial"
    output.mkdir(parents=True, exist_ok=True)
    if review_file:
        prepared = json.loads((output / "review-request.json").read_text())
        supplied = json.loads(Path(review_file).read_text())
        cutoff = parse_datetime(prepared.get("generatedAt"))
        if supplied.get("requestHash") != prepared.get("requestHash") or not cutoff or not timedelta(0) <= now - cutoff <= timedelta(hours=24):
            raise ValueError("Review file must match a current prepared review request")
        if cutoff.astimezone(ZoneInfo(os.environ.get("APP_TIMEZONE", "America/Los_Angeles"))).date() != now.astimezone(ZoneInfo(os.environ.get("APP_TIMEZONE", "America/Los_Angeles"))).date():
            raise ValueError("Prepare a new review request for today's edition")
        now = cutoff
    prompt_path = Path(__file__).resolve().parents[2] / "config/editorial-prompt.md"
    enabled = {c["name"] for c in config["collectors"] if c.get("enabled", True)}
    source_config = {c["name"]: c for c in config["collectors"]}
    edition_date = now.astimezone(ZoneInfo(os.environ.get("APP_TIMEZONE", "America/Los_Angeles"))).date().isoformat()
    history = load_history(settings.project_root.parent.parent, edition_date)
    rows = repository.fetch_recent_items(limit_hours=30 * 24)
    # A source can return a large feed where the newest entries are market noise
    # and an older, high-signal story would otherwise fall past its candidate cap.
    def candidate_priority(row):
        try:
            score = float(row.get("importance_score") or 0)
        except (TypeError, ValueError):
            score = 0
        published = parse_datetime(row.get("published_at"))
        return score, published.timestamp() if published else 0
    rows.sort(key=candidate_priority, reverse=True)
    candidates, excluded, counts, seen = [], [], Counter(), set()
    podcast_sources = set()
    # Per-source bounds keep a high-volume feed from consuming the review budget.
    for row in rows:
        reason = exclusion(row, now) or ("disabled_source" if row["source"] not in enabled else None)
        raw = json.loads(row.get("raw_json") or "{}")
        has_audio = bool(audio_url(raw))
        if not reason and has_audio and row["source"] in LONGFORM:
            if row["source"] in podcast_sources:
                excluded.append({"url": row["canonical_url"], "source": row["source"], "reason": "older_podcast_episode"})
                continue
            podcast_sources.add(row["source"])
        prior = prior_match(row["canonical_url"], row["title"], history, edition_date) if not reason else None
        if prior:
            excluded.append({"url": row["canonical_url"], "source": row["source"], "reason": "previously_published", "previous": prior})
            continue
        if reason:
            excluded.append({"url": row["canonical_url"], "source": row["source"], "reason": reason})
            continue
        if row["canonical_url"] in seen:
            excluded.append({"url": row["canonical_url"], "source": row["source"], "reason": "duplicate_url"})
            continue
        bucket = (row["source"], has_audio, None if has_audio else row["category"])
        limit = 1 if has_audio and row["source"] in LONGFORM else int(source_config[row["source"]].get("editorial_limit", 8))
        if counts[bucket] >= limit:
            excluded.append({"url": row["canonical_url"], "source": row["source"], "reason": "candidate_budget"})
            continue
        counts[bucket] += 1
        seen.add(row["canonical_url"])
        candidates.append(row)
    packets = []
    def prepare(row):
        try:
            return content_packet(row, repository, settings.user_agent)
        except Exception as exc:
            return {"failed_url": row["canonical_url"], "source": row["source"], "error": str(exc)[:200]}
    if review_file:
        # Apply the evidence snapshot the desk actually reviewed. Re-fetching here
        # made unrelated live pages change the hash midway through publication.
        current = {row["canonical_url"]: row for row in candidates}
        packets = prepared["packets"]
        for packet in packets:
            row = current.get(packet["url"])
            if row is None or (packet.get("inputHash") and source_hash(row) != packet["inputHash"]):
                raise ValueError("Source changed since review preparation; prepare and review again")
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for result in pool.map(prepare, candidates):
                if "failed_url" in result:
                    excluded.append({"url": result["failed_url"], "source": result["source"], "reason": "content_unavailable", "detail": result["error"]})
                else:
                    packets.append(result)
    decisions, pending = {}, []
    profile = reader_profile()
    policy = hashlib.sha256((POLICY_VERSION + prompt_path.read_text() + json.dumps(profile, sort_keys=True) + os.environ.get("NEWS_EDITOR_MODEL", "default") + os.environ.get("NEWS_EDITOR_REASONING_EFFORT", "default")).encode()).hexdigest()
    for packet in packets:
        key = hashlib.sha256((policy + json.dumps({k: v for k, v in packet.items() if k != "inputHash"}, sort_keys=True)).encode()).hexdigest()
        packet_path = output / f"packet-{packet['id']}.json"
        packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2))
        cache = output / f"review-{key}.json"
        if cache.exists():
            result = ReviewBatch.model_validate_json(cache.read_text())
            validate_decisions(result, [packet])
            decisions[packet["id"]] = result.decisions[0].model_dump()
        else:
            pending.append((packet, cache))
    news = [p for p in pending if p[0]["kind"] != "podcast"]
    selection_prompt = prompt_path.with_name("edition-selection-prompt.md")
    request_hash = hashlib.sha256((policy + json.dumps(packets, sort_keys=True) + selection_prompt.read_text() + history_hash(history)).encode()).hexdigest()
    request = {"requestHash": request_hash, "generatedAt": now.isoformat(), "policy": policy,
               "pending": [p for p, _ in pending], "cachedDecisions": decisions, "packets": packets,
               "publicationHistory": history, "historyHash": history_hash(history), "readerProfile": profile}
    (output / "review-request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2))
    if prepare_only:
        return {"decisions": decisions, "pending": len(pending), "request": str(output / "review-request.json")}
    external = None
    if review_file:
        external = validate_external_review(json.loads(Path(review_file).read_text()), request_hash, [p for p, _ in pending], validation_now)
        for decision in external.decisions:
            decisions[decision.id] = decision.model_dump()
        news = []
    batches = [news[i:i + 10] for i in range(0, len(news), 10)]
    if external is None:
        batches += [[p] for p in pending if p[0]["kind"] == "podcast"]
    for i, batch in enumerate(batches):
        print(f"Editorial review {i + 1}/{len(batches)}: {len(batch)} candidates", flush=True)
        review = codex_review([p for p, _ in batch], prompt_path, output)
        validate_ranking_review(review.decisions, [p for p, _ in batch])
        for decision in review.decisions:
            # Edition-wide dedupe is recomputed during assembly, not cached as cross-batch IDs.
            if decision.duplicate_of:
                decision.decision = "hold"
                decision.duplicate_of = None
            decisions[decision.id] = decision.model_dump()
            cache = next(c for p, c in batch if p["id"] == decision.id)
            # Cache only validated candidate work. The complete edition must still
            # clear the global ranking, selection and independent factual gates.
            temporary_cache = cache.with_suffix(".tmp")
            temporary_cache.write_text(ReviewBatch(decisions=[decision]).model_dump_json(indent=2))
            temporary_cache.replace(cache)
    from news_collector.pipeline.audit_repair import plain_review_prose
    normalized = plain_review_prose(ReviewBatch(decisions=[Decision.model_validate(d) for d in decisions.values()]))
    decisions = {decision.id: decision.model_dump() for decision in normalized.decisions}
    validate_ranking_review([Decision.model_validate(d) for d in decisions.values()], packets)
    shortlist = [{**decisions[p["id"]], "source": p["source"], "url": p["url"], "publishedAt": p["publishedAt"], "publisher": publisher(p["url"])}
                 for p in packets if decisions[p["id"]]["decision"] == "admit"]
    selection_key = hashlib.sha256((json.dumps(shortlist, sort_keys=True) + selection_prompt.read_text() + history_hash(history)).encode()).hexdigest()
    selection_path = output / f"selection-{selection_key}.json"
    if external is not None:
        selection = external.selection
    elif selection_path.exists():
        selection = EditionSelection.model_validate_json(selection_path.read_text())
    else:
        print("Editorial desk: reviewing the complete proposed edition", flush=True)
        selection = codex_review({"shortlist": shortlist, "previouslyPublished": history}, selection_prompt, output, EditionSelection)
    validate_selection(selection, shortlist)
    selection = EditionSelection.model_validate(limit_publishers(selection.model_dump(), packets))
    selection_path.write_text(selection.model_dump_json(indent=2))
    payload = {"policy": policy, "cutoff": now.isoformat(), "generatedAt": datetime.now(timezone.utc).isoformat(), "packets": packets,
               "selection": selection.model_dump(),
               "decisions": decisions, "excluded": excluded, "historyHash": history_hash(history)}
    if external is not None:
        payload["reviewProvenance"] = {"mode": "review-file", "reviewer": external.reviewer,
                                       "requestHash": request_hash, "reviewedAt": external.reviewedAt.isoformat()}
    temporary = output / "latest.json.tmp"
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    temporary.replace(output / "latest.json")
    return payload
