"""Bounded, evidence-reviewed sports desk with timestamped score/table snapshots."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import feedparser
import httpx
import yaml
from rapidfuzz import fuzz

from news_collector.pipeline.editorial import clean_text, content_packet, validate_external_review
from news_collector.pipeline.images import download, quality_image
from news_collector.pipeline.publication_history import load_history, prior_match, history_hash
from news_collector.utils import canonicalize_url, parse_datetime

LIMITS = {"NFL": 2, "Soccer": 3, "NBA": 2, "Elsewhere": 2}
NOISE = re.compile(r"\b(fantasy|betting|odds|picks|power rankings|tiers|predictions|follow live|live updates|grading the move|offseason recap|early.season preview|transfer rumo\w*|gossip|talking points|as opener nears)\b", re.I)


def config_for(settings):
    return yaml.safe_load((settings.project_root / "config/sports.yaml").read_text())


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def get_json(client, url, params=None):
    response = client.get(url, params=params)
    response.raise_for_status()
    return response.json()


def score_games(payload, start, end, now):
    if not isinstance(payload.get("events"), list):
        raise ValueError("Scoreboard missing events array")
    games = []
    for event in payload["events"]:
        date = parse_datetime(event.get("date"))
        if not date or not start <= date <= end:
            continue
        competition = event["competitions"][0]
        status = competition.get("status", event.get("status", {})).get("type", {})
        state = status.get("state")
        completed = status.get("completed") is True
        if state not in {"pre", "in", "post"} or (completed and state != "post"):
            raise ValueError("Invalid game state")
        if date > now + timedelta(minutes=5) and state != "pre":
            raise ValueError("Future game has a played score")
        teams = {c["homeAway"]: c for c in competition["competitors"]}
        if set(teams) != {"home", "away"}:
            raise ValueError("Missing home/away competitor")
        def side(key):
            c = teams[key]
            score = c.get("score")
            if isinstance(score, dict):
                score = score.get("displayValue")
            if state != "pre" and (score is None or not re.fullmatch(r"\d+", str(score))):
                raise ValueError("Played game lacks numeric score")
            return {"name": c["team"]["displayName"], "score": None if state == "pre" else str(score)}
        links = [l["href"] for l in event.get("links", []) if l.get("href", "").startswith("https://www.espn.com/")]
        detail = status.get("detail") or status.get("description") or "Scheduled"
        penalties = [c.get("shootoutScore") for c in [teams["away"], teams["home"]]]
        if all(p is not None for p in penalties):
            detail += f"; penalties {penalties[0]}-{penalties[1]} (away-home)"
        games.append({"id": str(event["id"]), "date": date.isoformat(), "state": state,
                      "completed": completed, "detail": detail, "away": side("away"), "home": side("home"),
                      "url": links[0] if links else "https://www.espn.com/"})
    return sorted({g["id"]: g for g in games}.values(), key=lambda g: g["date"])


def standings_tables(payload, group):
    tables = []
    def visit(node):
        standing = node.get("standings")
        if standing:
            rows = []
            for entry in standing.get("entries", []):
                stats = {s["name"]: s for s in entry.get("stats", [])}
                def stat(name):
                    return str(stats.get(name, {}).get("displayValue", ""))
                if not stat("wins") or not stat("losses"):
                    continue
                rank = stats.get("rank" if group == "Soccer" else "playoffSeed", {}).get("value")
                played = sum(float(stats.get(k, {}).get("value", 0)) for k in ["wins", "losses", "ties"])
                rows.append({"team": entry["team"]["displayName"], "rank": int(rank) if rank and float(rank) > 0 else None,
                             "record": "-".join(filter(lambda x: x != "", [stat("wins"), stat("losses"), stat("ties") if group != "NBA" else ""])),
                             "points": stat("points") if group == "Soccer" else None, "played": played})
            rows.sort(key=lambda r: (r["rank"] or 999, r["team"]))
            if rows:
                links = [l["href"] for l in standing.get("links", []) if l.get("href", "").startswith("https://www.espn.com/")]
                tables.append({"name": node.get("name", "Standings"), "url": links[0] if links else None, "season": str(standing.get("seasonDisplayName") or standing.get("season") or "Season not supplied"),
                               "started": any(r["played"] > 0 for r in rows), "rows": rows[:3]})
        for child in node.get("children", []):
            visit(child)
    visit(payload)
    if not tables:
        raise ValueError("No usable standings tables")
    return tables


def collect_scores(config, now, client):
    start, end = now - timedelta(hours=24), now + timedelta(hours=24)
    dates = f"{start:%Y%m%d}-{end:%Y%m%d}"
    leagues, health = [], []
    for league in config["leagues"]:
        result = {k: league[k] for k in ["id", "group", "name", "url"]}
        result.update(games=[], tables=[], season="", scheduleStatus="ok", standingsStatus="ok")
        for kind in ["scoreboard", "standings"]:
            name = f"espn_{league['id']}_{kind}"
            error = None
            try:
                if kind == "scoreboard":
                    data = get_json(client, f"https://site.api.espn.com/apis/site/v2/sports/{league['path']}/scoreboard", {"dates": dates, "limit": 100})
                    result["games"] = score_games(data, start, end, now)
                    result["season"] = str((data.get("leagues") or [{}])[0].get("season", {}).get("displayName", ""))
                else:
                    data = get_json(client, f"https://site.api.espn.com/apis/v2/sports/{league['path']}/standings")
                    result["tables"] = standings_tables(data, league["group"])
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:150]}"
                result["scheduleStatus" if kind == "scoreboard" else "standingsStatus"] = "unavailable"
            count = len(result["games"] if kind == "scoreboard" else result["tables"])
            health.append({"name": name, "status": "error" if error else "ok", "count": count, "collected": count,
                           "latest": now.isoformat() if not error else None, "reason": error, "checkedAt": now.isoformat()})
        leagues.append(result)
    return {"checkedAt": now.isoformat(), "windowStart": start.isoformat(), "windowEnd": end.isoformat(), "leagues": leagues}, health


def prepare_sports(settings, repository, now, zone):
    config = config_for(settings)
    root = settings.project_root.parent.parent
    history = load_history(root, now.astimezone(ZoneInfo(zone)).date().isoformat())
    packets, health, seen = [], [], set()
    # ESPN's JSON service accepts the standard HTTP client user-agent, unlike the
    # custom crawler agent used for publisher article retrieval.
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        scores, score_health = collect_scores(config, now, client)
        for feed in config["feeds"]:
            count, eligible, error = 0, 0, None
            latest = None
            try:
                body, _ = download(client, feed["url"], 3_000_000)
                parsed = feedparser.parse(body)
                if not parsed.entries:
                    raise ValueError("Feed contains no entries")
                count = len(parsed.entries)
                candidates = []
                for e in parsed.entries:
                    date = parse_datetime(e.get("published") or e.get("updated"))
                    title, url = clean_text(e.get("title")), canonicalize_url(e.get("link", ""))
                    if date and (latest is None or date.isoformat() > latest):
                        latest = date.isoformat()
                    if not date or not now - timedelta(hours=48) <= date <= now + timedelta(minutes=5) or not url.startswith("https://") or not title or NOISE.search(title):
                        continue
                    if url in seen or prior_match(url, title, history, now.astimezone(ZoneInfo(zone)).date().isoformat()):
                        continue
                    candidates.append((date, title, url, e))
                eligible = len(candidates)
                for date, title, url, e in sorted(candidates, key=lambda c: c[0], reverse=True)[:8]:
                    if url in seen:
                        continue
                    seen.add(url)
                    row = {"canonical_url": url, "url": url, "title": title, "published_at": date.isoformat(),
                           "source": feed["name"], "category": "other", "text": clean_text(e.get("summary", "")), "raw_json": "{}"}
                    packet = content_packet(row, repository, settings.user_agent)
                    if packet["id"] in {p["id"] for p in packets}:
                        continue
                    packet["sportsGroup"] = feed["group"]
                    packets.append(packet)
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:150]}"
            health.append({"name": feed["name"], "status": "error" if error else "ok", "count": count, "collected": count,
                           "eligible": eligible, "candidates": sum(p["source"] == feed["name"] for p in packets),
                           "latest": latest, "reason": error, "checkedAt": now.isoformat()})
    prompt = (settings.project_root / "config/sports-prompt.md").read_text()
    request = {"generatedAt": now.isoformat(), "date": now.astimezone(ZoneInfo(zone)).date().isoformat(), "timezone": zone,
               "packets": packets, "scores": scores, "sources": health + score_health, "historyHash": history_hash(history), "previouslyPublished": history,
               "policy": fingerprint({"config": config, "prompt": prompt})}
    request["requestHash"] = fingerprint(request)
    return request


def publish_sports(request, review, settings, repository, now, zone):
    from news_collector.jobs.export_edition import publisher
    today = now.astimezone(ZoneInfo(zone)).date().isoformat()
    if request["date"] != today or not timedelta(0) <= now - parse_datetime(request["generatedAt"]) <= timedelta(hours=6):
        raise ValueError("Prepare fresh sports data for today before applying review")
    if request["requestHash"] != fingerprint({k: v for k, v in request.items() if k != "requestHash"}):
        raise ValueError("Sports request integrity check failed")
    policy = fingerprint({"config": config_for(settings), "prompt": (settings.project_root / "config/sports-prompt.md").read_text()})
    history = load_history(settings.project_root.parent.parent, today)
    if policy != request["policy"] or history_hash(history) != request["historyHash"]:
        raise ValueError("Sports policy or publication history changed; prepare again")
    reviewed = validate_external_review(review, request["requestHash"], request["packets"], now)
    decisions = {d.id: d for d in reviewed.decisions}
    admitted = {d.id for d in reviewed.decisions if d.decision == "admit"}
    selected = reviewed.selection.selected_ids
    accounted = selected + [d.id for d in reviewed.selection.excluded]
    if len(accounted) != len(set(accounted)) or set(accounted) != admitted:
        raise ValueError("Sports selection must account for admissions once")
    packets = {p["id"]: p for p in request["packets"]}
    stories, counts = [], Counter()
    for id in selected:
        d, p = decisions[id], packets[id]
        group = p["sportsGroup"]
        counts[group] += 1
        if counts[group] > LIMITS[group] or len(d.summary.split()) > 95 or len(d.points) > 2 or d.sections:
            raise ValueError("Sports brief exceeds its section or length budget")
        if prior_match(p["url"], d.headline, history, today):
            raise ValueError("Previously published sports story selected again")
        if any(fuzz.token_set_ratio(s["title"], d.headline) >= 85 for s in stories):
            raise ValueError("Overlapping sports headlines selected")
        image = quality_image(repository, p["url"], [], settings.user_agent)["image"]
        stories.append({"id": id, "title": d.headline, "summary": d.summary, "sector": "Sports", "sportsGroup": group,
                        "url": p["url"], "image": image, "publishedAt": p["publishedAt"], "score": round((d.quality * .7 + d.importance * .3) / 10, 1),
                        "publisher": "ESPN" if "espn.com" in p["url"] else publisher(p["url"]), "collectors": [p["source"]], "coverage": [],
                        "kind": d.kind, "points": d.points, "sections": [], "caveats": d.caveats, "quality": d.quality,
                        "importance": d.importance, "contentBasis": p["basis"], "editorialReason": d.reason})
    sources = []
    for source in request["sources"]:
        sources.append({**source, "reviewed": sum(d.quality > 0 and packets[d.id]["source"] == source["name"] for d in reviewed.decisions),
                        "published": sum(source["name"] in s["collectors"] for s in stories)})
    return {"date": today, "generatedAt": now.isoformat(), "requestHash": request["requestHash"],
            "reviewedAt": reviewed.reviewedAt.isoformat(), "stories": stories, "sports": request["scores"], "sources": sources}


def attach_sports(snapshot, sports, now):
    if sports["date"] != snapshot["date"] or not timedelta(0) <= now - parse_datetime(sports["sports"]["checkedAt"]) <= timedelta(hours=24):
        raise ValueError("Sports snapshot is stale; run the sports pipeline for today's paper")
    existing = {s["id"] for s in snapshot["stories"]}
    if any(s["id"] in existing for s in sports["stories"]):
        raise ValueError("Sports article duplicates main paper")
    offset = len(snapshot["stories"])
    snapshot["stories"].extend({**s, "editorialRank": offset + i} for i, s in enumerate(sports["stories"]))
    snapshot["sports"] = sports["sports"]
    snapshot["sources"].extend(sports["sources"])


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)
