"""Research coverage before selection, without exposing the draft to the researcher."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import httpx

from .edition_audit import IndependentChecklist


def validate_checklist(payload, cutoff, profile, now=None):
    now = now or datetime.now(timezone.utc)
    if cutoff.tzinfo is None:
        raise ValueError("Discovery cutoff must be timezone-aware")
    checklist = IndependentChecklist.model_validate(payload)
    local = ZoneInfo(profile.get("timezone", "America/Los_Angeles"))
    checked = checklist.checkedAt
    if (checked.tzinfo is None or not timedelta(minutes=-5) <= now - checked <= timedelta(hours=6)
            or abs(cutoff - checked) > timedelta(hours=6)
            or checked.astimezone(local).date() != cutoff.astimezone(local).date()):
        raise ValueError("Discovery checklist must be from this local day and within six hours")
    if any(not item.strip() for item in [checklist.researcher, *checklist.scope, *checklist.queries]):
        raise ValueError("Discovery requires a researcher, real scope and research queries")
    if len({event.id for event in checklist.events}) != len(checklist.events):
        raise ValueError("Discovery event IDs must be unique")
    eligible_events = []
    for event in checklist.events:
        # Research can return a guessed or just-after-cutoff timestamp. Such
        # sources cannot establish today's coverage requirement; discard them
        # instead of failing an otherwise usable edition.
        event.sources = [source for source in event.sources
                         if source.publishedAt.tzinfo is not None
                         and source.publishedAt <= min(cutoff, checked) + timedelta(minutes=5)]
        if not event.sources:
            continue
        # A stale background item can remain useful context, but it must not be
        # allowed to block today's edition as a must-cover event.
        if event.mustCover and not any(source.publishedAt >= cutoff - timedelta(hours=48) for source in event.sources):
            event.mustCover = False
        eligible_events.append(event)
    checklist.events = eligible_events
    return checklist.model_dump(mode="json")



def verify_must_cover_sources(payload, cutoff, cache=None):
    """Research cannot impose blocking requirements using guessed dates or URLs."""
    from .images import download
    from .publication_dates import article_publication_date
    from .extract import extract_text_from_html
    from .publishers import publisher
    cache = cache if cache is not None else {}
    events = [event for event in payload["events"] if event["mustCover"]]
    if not events:
        return
    if sum(len(event["sources"]) for event in events) > 30:
        raise ValueError("Must-cover source verification is limited to 30 direct sources")
    with httpx.Client(timeout=10, follow_redirects=False, headers={"User-Agent": "News4u coverage verifier"}) as client:
        for event in events:
            verified = []
            for source in event["sources"]:
                url = source["url"]
                if url not in cache:
                    try:
                        body, final_url = download(client, url, 2_000_000)
                        html = body.decode("utf-8", errors="replace")
                        date = article_publication_date(html)
                        text = extract_text_from_html(html, final_url) or ""
                        cache[url] = (date, len(text.split()), final_url)
                    except (httpx.HTTPError, ValueError, OSError) as exc:
                        cache[url] = (None, 0, url)
                        print(f"Coverage source unavailable: {url} ({type(exc).__name__})", flush=True)
                actual, words, final_url = cache[url]
                claimed = datetime.fromisoformat(source["publishedAt"])
                if (actual is not None and actual.tzinfo is not None and words >= 80
                        and claimed.date() in {actual.date(), actual.astimezone(timezone.utc).date()} and actual <= cutoff + timedelta(minutes=5)):
                    verified.append((actual, (urlparse(final_url).hostname or "").removeprefix("www."), publisher(final_url)))
            fresh = [(date, host, identity) for date, host, identity in verified if date >= cutoff - timedelta(hours=48)]
            primary = any(host.endswith((".gov", ".gov.uk", ".europa.eu", ".int"))
                          or host in {"ecb.europa.eu", "who.int"} for _, host, _ in fresh)
            if not fresh or not (primary or len({identity for _, _, identity in verified}) >= 2):
                raise ValueError(f"Must-cover event {event['id']} lacks accessible publisher-dated evidence of a new development. "
                                 "Find direct dated primary evidence or independent corroboration; "
                                 "background topic pages and unavailable articles cannot establish a blocking requirement.")
            print(f"Coverage requirement verified: {event['id']} ({len(verified)} dated sources)", flush=True)

def discover_coverage(output, cutoff, profile, checklist_file=None):
    """Return and persist a validated checklist; errors leave the prior file untouched."""
    output = Path(output)
    prompt_path = Path(__file__).resolve().parents[2] / "config" / "coverage-discovery-prompt.md"
    context = {"sourceVerificationVersion": 1, "profile": profile, "prompt": prompt_path.read_text(),
               "model": os.environ.get("NEWS_EDITOR_MODEL", "default"),
               "effort": os.environ.get("NEWS_EDITOR_REASONING_EFFORT", "default")}
    context_path = output.with_suffix(".context.json")
    if checklist_file is None and output.exists() and context_path.exists():
        try:
            if json.loads(context_path.read_text()) == context:
                cached = validate_checklist(json.loads(output.read_text()), cutoff, profile)
                print(f"Coverage discovery: reusing {len(cached['events'])} current validated events", flush=True)
                return cached
        except (ValueError, TypeError):
            pass  # A new day or expired research requires fresh discovery.
    if checklist_file is not None:
        payload = json.loads(Path(checklist_file).read_text())
    else:
        from .editorial import codex_review
        research = {"cutoff": cutoff.isoformat(), "profile": profile,
                    "windowStart": (cutoff - timedelta(hours=48)).isoformat()}
        checked_sources = {}
        def validate_research(result):
            candidate = validate_checklist(result.model_dump(mode="json"), cutoff, profile)
            verify_must_cover_sources(candidate, cutoff, checked_sources)
        print(f"Coverage discovery: starting independent research for cutoff {cutoff.isoformat()}", flush=True)
        result = codex_review(research, prompt_path, output.parent, IndependentChecklist,
            allow_web=True, validate_result=validate_research)
        payload = result.model_dump(mode="json")
        validate_research(result)
    validated = validate_checklist(payload, cutoff, profile)
    print(f"Coverage discovery complete: {len(validated['events'])} events, "
          f"{sum(event['mustCover'] for event in validated['events'])} mandatory", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    # A failed write or validation must never replace the previous reviewed checklist.
    with tempfile.NamedTemporaryFile(mode="w", dir=output.parent, delete=False, suffix=".tmp") as handle:
        temporary = Path(handle.name)
        try:
            json.dump(validated, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    context_path.write_text(json.dumps(context, sort_keys=True))
    return validated
