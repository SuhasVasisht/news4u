from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from news_collector.pipeline import editorial
from test_editorial import packet, decision, row


def test_candidate_ids_are_constrained_and_hash_confusion_gets_specific_feedback(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(editorial.shutil, "which", lambda _: "/bin/codex")
    def run(command, **kwargs):
        contract = json.loads(editorial.Path(command[command.index("--output-schema") + 1]).read_text())
        assert contract["$defs"]["Decision"]["properties"]["id"]["enum"] == [packet()["id"]]
        calls.append(kwargs["input"])
        item = decision(id="wrong-input-hash") if len(calls) == 1 else decision()
        editorial.Path(command[command.index("-o") + 1]).write_text(editorial.ReviewBatch(decisions=[item]).model_dump_json())
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(editorial.subprocess, "run", run)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Review the evidence")
    assert editorial.codex_review([packet()], prompt, tmp_path).decisions[0].id == packet()["id"]
    assert f"missing=['{packet()['id']}']" in calls[1]
    assert "unknown=['wrong-input-hash']" in calls[1]


def test_capacity_retries_same_model_without_relaxing_validation(tmp_path, monkeypatch):
    calls, delays = [], []
    monkeypatch.setattr(editorial.shutil, "which", lambda _: "/bin/codex")
    monkeypatch.setattr(editorial.time, "sleep", delays.append)
    def run(command, **kwargs):
        calls.append(command.copy())
        if len(calls) == 1:
            return SimpleNamespace(returncode=1, stderr="ERROR: Selected model is at capacity.")
        editorial.Path(command[command.index("-o") + 1]).write_text(editorial.ReviewBatch(decisions=[decision()]).model_dump_json())
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(editorial.subprocess, "run", run)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Review the evidence")
    assert editorial.codex_review([packet()], prompt, tmp_path).decisions
    assert len(calls) == 2 and calls[0] == calls[1]
    assert delays == [20]


@pytest.mark.parametrize("error, attempts", [("ERROR: Selected model is at capacity.", 3), ("ERROR: Authentication failed.", 1)])
def test_capacity_retries_are_bounded_and_auth_errors_are_not_retried(tmp_path, monkeypatch, error, attempts):
    calls = []
    monkeypatch.setattr(editorial.shutil, "which", lambda _: "/bin/codex")
    monkeypatch.setattr(editorial.time, "sleep", lambda _: None)
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1, stderr=error)
    monkeypatch.setattr(editorial.subprocess, "run", run)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Review the evidence")
    with pytest.raises(RuntimeError, match="previous paper retained"):
        editorial.codex_review([packet()], prompt, tmp_path)
    assert len(calls) == attempts


@pytest.mark.parametrize("allow_web", [False, True])
def test_live_verification_is_explicit_without_enabling_shells(tmp_path, monkeypatch, allow_web):
    monkeypatch.setattr(editorial.shutil, "which", lambda _: "/bin/codex")
    monkeypatch.setenv("NEWS_EDITOR_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("NEWS_EDITOR_REASONING_EFFORT", "medium")
    def run(command, **kwargs):
        assert command[command.index("--model") + 1] == "gpt-5.6-luna"
        assert 'model_reasoning_effort="medium"' in command
        assert ('web_search="live"' if allow_web else 'web_search="disabled"') in command
        assert "shell_tool" in command and "unified_exec" in command and "apps" in command
        editorial.Path(command[command.index("-o") + 1]).write_text(editorial.ReviewBatch(decisions=[decision()]).model_dump_json())
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(editorial.subprocess, "run", run)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Verify this report")
    assert editorial.codex_review([packet()], prompt, tmp_path, allow_web=allow_web).decisions


@pytest.mark.parametrize("recovers", [True, False])
def test_invalid_admission_gets_one_bounded_retry(tmp_path, monkeypatch, recovers):
    calls = []
    monkeypatch.setattr(editorial.shutil, "which", lambda _: "/bin/codex")
    def run(command, **kwargs):
        calls.append(kwargs["input"])
        item = decision(decision="hold" if recovers and len(calls) == 2 else "admit")
        editorial.Path(command[command.index("-o") + 1]).write_text(editorial.ReviewBatch(decisions=[item]).model_dump_json())
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(editorial.subprocess, "run", run)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Do not admit truncated evidence")
    packets = [{**packet(), "truncated": True}]
    if recovers:
        assert editorial.codex_review(packets, prompt, tmp_path).decisions[0].decision == "hold"
    else:
        with pytest.raises(ValueError, match="completeness gate"):
            editorial.codex_review(packets, prompt, tmp_path)
    assert len(calls) == 2
    assert "VALIDATION FEEDBACK" in calls[1]
    assert len(list((tmp_path / "responses").glob("*.json"))) == 2


def test_completed_batches_survive_a_later_failure(tmp_path, monkeypatch):
    current = datetime.now(timezone.utc).isoformat()
    rows = [row(canonical_url=f"https://example.com/{i}", published_at=current) for i in range(15)]
    repository = SimpleNamespace(fetch_recent_items=lambda **_: rows)
    settings = SimpleNamespace(project_root=tmp_path / "scripts/news_collector", user_agent="test")
    config = {"collectors": [{"name": "ars_technica", "editorial_limit": 20}]}
    monkeypatch.setattr(editorial, "content_packet", lambda r, *_: {**packet(), "id": r["canonical_url"].rsplit("/", 1)[-1], "url": r["canonical_url"]})
    calls = []
    def review(packets, *_):
        calls.append(packets)
        if len(calls) == 2:
            raise RuntimeError("review unavailable")
        return editorial.ReviewBatch(decisions=[decision(id=p["id"]) for p in packets])
    monkeypatch.setattr(editorial, "codex_review", review)
    with pytest.raises(RuntimeError, match="unavailable"):
        editorial.run_editorial(repository, settings, config)
    result = editorial.run_editorial(repository, settings, config, prepare_only=True)
    assert len(result["decisions"]) == 10
    assert result["pending"] == 5
    assert not (tmp_path / "data/editorial/latest.json").exists()
