from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from news_collector.pipeline import editorial
from test_editorial import packet, decision, row


def test_story_audit_schema_binds_ids_passages_and_evidence(tmp_path, monkeypatch):
    from test_edition_audit import fixture
    from news_collector.pipeline.edition_audit import StoryAuditReview
    request, envelope = fixture()
    request["auditStoryIds"] = ["a"]
    request["decisions"][0].setdefault("sections", [])
    monkeypatch.setattr(editorial.shutil, "which", lambda _: "/bin/codex")
    def run(command, **kwargs):
        schema = json.loads(editorial.Path(command[command.index("--output-schema") + 1]).read_text())
        stories = schema["properties"]["stories"]
        assert stories["required"] == ["a"]
        claim = stories["properties"]["a"]["properties"]["claims"]["items"]
        assert request["decisions"][0]["headline"] in claim["properties"]["passage"]["enum"]
        assert claim["properties"]["evidence"]["items"]["enum"] == ["p1"]
        result = {"stories": {"a": envelope["review"]["stories"][0]}}
        editorial.Path(command[command.index("-o") + 1]).write_text(json.dumps(result))
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(editorial.subprocess, "run", run)
    prompt = tmp_path / "audit.md"
    prompt.write_text("Audit")
    assert editorial.codex_review(request, prompt, tmp_path, StoryAuditReview).stories[0].id == "a"


@pytest.mark.parametrize("recovers", [True, False])
def test_semantic_validation_uses_bounded_retry(tmp_path, monkeypatch, recovers):
    calls = []
    monkeypatch.setattr(editorial.shutil, "which", lambda _: "/bin/codex")
    def run(command, **kwargs):
        calls.append(kwargs["input"])
        editorial.Path(command[command.index("-o") + 1]).write_text(editorial.ReviewBatch(decisions=[decision()]).model_dump_json())
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(editorial.subprocess, "run", run)
    def validate(result):
        if not recovers or len(calls) == 1:
            raise ValueError("Unknown audit evidence p99; use supplied chunk p1")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Review")
    if recovers:
        assert editorial.codex_review([packet()], prompt, tmp_path, validate_result=validate).decisions
    else:
        with pytest.raises(ValueError, match="Unknown audit evidence"):
            editorial.codex_review([packet()], prompt, tmp_path, validate_result=validate)
    assert len(calls) == 2
    assert "use supplied chunk p1" in calls[1]


@pytest.mark.parametrize("count", [1, 29])
def test_selection_mapping_preserves_exclusions_and_enforces_edition_limit(tmp_path, monkeypatch, count):
    monkeypatch.setattr(editorial.shutil, "which", lambda _: "/bin/codex")
    entries = {str(i): {"selected": True, "reason": "Important"} for i in range(count)}
    entries["held"] = {"selected": False, "reason": "Lower priority"}
    def run(command, **kwargs):
        editorial.Path(command[command.index("-o") + 1]).write_text(json.dumps({"selected_ids": [id for id, entry in entries.items() if entry["selected"]], "reasons": {id: entry["reason"] for id, entry in entries.items()}}))
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(editorial.subprocess, "run", run)
    prompt = tmp_path / "selection.md"
    prompt.write_text("Select")
    packets = {"shortlist": [{"id": id} for id in entries]}
    if count > 28:
        with pytest.raises(ValueError, match="maximum 28"):
            editorial.codex_review(packets, prompt, tmp_path, editorial.EditionSelection)
    else:
        result = editorial.codex_review(packets, prompt, tmp_path, editorial.EditionSelection)
        assert result.selected_ids == ["0"]
        assert [(e.id, e.reason) for e in result.excluded] == [("held", "Lower priority")]


@pytest.mark.parametrize("recovers", [True, False])
def test_selection_requires_every_candidate_and_retries_omissions(tmp_path, monkeypatch, recovers):
    calls = []
    monkeypatch.setattr(editorial.shutil, "which", lambda _: "/bin/codex")
    def run(command, **kwargs):
        calls.append(kwargs["input"])
        contract = json.loads(editorial.Path(command[command.index("--output-schema") + 1]).read_text())
        assert contract["properties"]["reasons"]["required"] == ["a"]
        entries = {"a": {"selected": True, "reason": "Important"}} if recovers and len(calls) == 2 else {}
        editorial.Path(command[command.index("-o") + 1]).write_text(json.dumps({"selected_ids": [id for id, entry in entries.items() if entry["selected"]], "reasons": {id: entry["reason"] for id, entry in entries.items()}}))
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(editorial.subprocess, "run", run)
    prompt = tmp_path / "selection.md"
    prompt.write_text("Select the complete edition")
    if recovers:
        assert editorial.codex_review({"shortlist": [{"id": "a"}]}, prompt, tmp_path, editorial.EditionSelection).selected_ids == ["a"]
    else:
        with pytest.raises(ValueError, match="exactly every shortlist ID"):
            editorial.codex_review({"shortlist": [{"id": "a"}]}, prompt, tmp_path, editorial.EditionSelection)
    assert len(calls) == 2
    assert "exactly every shortlist ID" in calls[1]


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


def test_sports_subclass_schema_constrains_exact_evidence_and_retry_explains_ids(tmp_path, monkeypatch):
    from news_collector.jobs.sports import SportsReview
    calls = []
    monkeypatch.setattr(editorial.shutil, 'which', lambda _: '/bin/codex')
    def run(command, **kwargs):
        schema = json.loads(editorial.Path(command[command.index('--output-schema') + 1]).read_text())
        assert schema['$defs']['Decision']['properties']['id']['enum'] == [packet()['id']]
        for name in ('Decision', 'NoteSection'):
            assert schema['$defs'][name]['properties']['evidence']['items']['enum'] == ['p1']
        calls.append(kwargs['input'])
        item = decision(evidence=['one:p1']) if len(calls) == 1 else decision()
        editorial.Path(command[command.index('-o') + 1]).write_text(SportsReview(decisions=[item]).model_dump_json())
        return SimpleNamespace(returncode=0, stderr='')
    monkeypatch.setattr(editorial.subprocess, 'run', run)
    prompt = tmp_path / 'sports.md'
    prompt.write_text('Sports review')
    assert editorial.codex_review({'packets': [packet()]}, prompt, tmp_path, SportsReview).decisions
    assert len(calls) == 2
    assert "use only individual chunk IDs: ['p1']" in calls[1]


def test_research_retry_receives_rejected_checklist_and_all_source_diagnostics(tmp_path, monkeypatch):
    from news_collector.pipeline.edition_audit import IndependentChecklist
    calls = []
    payload = {'checkedAt': datetime.now(timezone.utc).isoformat(),
        'method': 'independent_web_research', 'researcher': 'Independent desk',
        'scope': ['World'], 'queries': ['energy ceasefire'], 'events': [
            {'id': 'first-event', 'event': 'First consequential event', 'sector': 'World', 'mustCover': True,
             'sources': [{'url': 'https://blocked.example.org/first', 'publishedAt': '2026-10-12T05:00:00Z',
                          'finding': 'First source describes the claimed new development.'}]},
            {'id': 'second-event', 'event': 'Second consequential event', 'sector': 'World', 'mustCover': True,
             'sources': [{'url': 'https://blocked.example.org/second', 'publishedAt': '2026-10-12T06:00:00Z',
                          'finding': 'Second source describes the claimed new development.'}]}]}
    monkeypatch.setattr(editorial.shutil, 'which', lambda _: '/bin/codex')
    def run(command, **kwargs):
        calls.append(kwargs['input'])
        editorial.Path(command[command.index('-o') + 1]).write_text(json.dumps(payload))
        return SimpleNamespace(returncode=0, stderr='')
    monkeypatch.setattr(editorial.subprocess, 'run', run)
    def validate(result):
        if len(calls) == 1:
            raise ValueError('first-event bad publication date; ' + 'source diagnostics ' * 40
                             + '; second-event blocked URL https://blocked.example.org/second')
    prompt = tmp_path / 'research.md';prompt.write_text('Research sources')
    result = editorial.codex_review({'cutoff': '2026-10-12T14:11:05Z'}, prompt, tmp_path,
                                   IndependentChecklist, validate_result=validate)
    assert len(calls) == 2 and len(result.events) == 2
    assert 'UNTRUSTED REJECTED CHECKLIST' in calls[1]
    assert 'https://blocked.example.org/first' in calls[1]
    assert 'second-event blocked URL' in calls[1]
    assert 'SAME event IDs' in calls[1]
