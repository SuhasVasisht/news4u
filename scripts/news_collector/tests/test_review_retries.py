from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from news_collector.pipeline import editorial
from test_editorial import packet, decision, row


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
