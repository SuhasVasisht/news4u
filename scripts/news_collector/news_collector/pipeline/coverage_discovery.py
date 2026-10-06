"""Research coverage before selection, without exposing the draft to the researcher."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

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


def discover_coverage(output, cutoff, profile, checklist_file=None):
    """Return and persist a validated checklist; errors leave the prior file untouched."""
    output = Path(output)
    prompt_path = Path(__file__).resolve().parents[2] / "config" / "coverage-discovery-prompt.md"
    context = {"profile": profile, "prompt": prompt_path.read_text(),
               "model": os.environ.get("NEWS_EDITOR_MODEL", "default"),
               "effort": os.environ.get("NEWS_EDITOR_REASONING_EFFORT", "default")}
    context_path = output.with_suffix(".context.json")
    if checklist_file is None and output.exists() and context_path.exists():
        try:
            if json.loads(context_path.read_text()) == context:
                return validate_checklist(json.loads(output.read_text()), cutoff, profile)
        except (ValueError, TypeError):
            pass  # A new day or expired research requires fresh discovery.
    if checklist_file is not None:
        payload = json.loads(Path(checklist_file).read_text())
    else:
        from .editorial import codex_review
        research = {"cutoff": cutoff.isoformat(), "profile": profile,
                    "windowStart": (cutoff - timedelta(hours=48)).isoformat()}
        result = codex_review(research, prompt_path, output.parent, IndependentChecklist,
            allow_web=True, validate_result=lambda result: validate_checklist(result.model_dump(mode="json"), cutoff, profile))
        payload = result.model_dump(mode="json")
    validated = validate_checklist(payload, cutoff, profile)
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
