"""Research coverage before selection, without exposing the draft to the researcher."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from zoneinfo import ZoneInfo

from .edition_audit import IndependentChecklist
from .structured_output import review_schema


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
    for event in checklist.events:
        for source in event.sources:
            if source.publishedAt.tzinfo is None or source.publishedAt > min(cutoff, checked) + timedelta(minutes=5):
                raise ValueError("Discovery source publication date is naive or after cutoff")
    return checklist.model_dump(mode="json")


def discover_coverage(output, cutoff, profile, checklist_file=None):
    """Return and persist a validated checklist; errors leave the prior file untouched."""
    output = Path(output)
    if checklist_file is not None:
        payload = json.loads(Path(checklist_file).read_text())
    else:
        executable = shutil.which(os.environ.get("NEWS_EDITOR_CODEX_BIN", "codex"))
        if not executable:
            raise RuntimeError("Codex CLI required for independent discovery; previous paper retained")
        prompt_path = Path(__file__).resolve().parents[2] / "config" / "coverage-discovery-prompt.md"
        with tempfile.TemporaryDirectory(prefix="news-discovery-") as directory:
            root = Path(directory)
            schema, result = root / "schema.json", root / "checklist.json"
            schema.write_text(json.dumps(review_schema(IndependentChecklist)))
            command = [executable, "exec", "--ignore-user-config", "--ephemeral",
                       "--skip-git-repo-check", "--sandbox", "read-only", "-C", directory,
                       "--disable", "shell_tool", "--disable", "unified_exec", "--disable", "apps",
                       "--disable", "hooks", "--disable", "browser_use", "--disable", "computer_use",
                       "-c", 'web_search="live"', "--output-schema", str(schema), "-o", str(result), "-"]
            model = os.environ.get("NEWS_EDITOR_MODEL")
            if model:
                command[2:2] = ["--model", model]
            environment = {key: value for key, value in os.environ.items()
                           if key in {"PATH", "HOME", "TMPDIR", "CODEX_HOME", "SSL_CERT_FILE", "TERM"}}
            prompt = prompt_path.read_text() + "\nRESEARCH INPUT:\n" + json.dumps(
                {"cutoff": cutoff.isoformat(), "profile": profile}, ensure_ascii=False)
            run = subprocess.run(command, input=prompt, text=True, capture_output=True,
                                 env=environment, timeout=600)
            if run.returncode or not result.exists():
                raise RuntimeError(f"Independent discovery failed (exit {run.returncode}); previous paper retained")
            payload = json.loads(result.read_text())
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
    return validated
