from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import json

import pytest

from news_collector.pipeline import coverage_intake as intake
from news_collector.storage.db import Database
from news_collector.storage.repository import Repository
from news_collector.jobs import editorial as job

NOW = datetime.now(timezone.utc).replace(microsecond=0)
URL = "https://example.org/missed-major-event"


def checklist():
    return {"events": [{"id": "must", "mustCover": True, "sources": [
        {"url": URL, "publishedAt": NOW.isoformat()}]},
        {"id": "optional", "mustCover": False, "sources": [
            {"url": "https://example.org/optional", "publishedAt": NOW.isoformat()}]}]}


def setup_page(tmp_path, monkeypatch, date=NOW, words=150):
    repository = Repository(Database(tmp_path / "news.db"))
    html = (f'<meta property="article:published_time" content="{date.isoformat()}">'
            '<meta property="og:title" content="Publisher headline"><article>Evidence</article>')
    calls = []
    def download(*args):
        calls.append(args[1])
        return html.encode(), URL
    monkeypatch.setattr(intake, "download", download)
    monkeypatch.setattr(intake, "extract_text_from_html", lambda *_: "publisher evidence " * (words // 2))
    monkeypatch.setattr(intake, "prepare_images", lambda *_: None)
    return repository, calls


def test_verified_discovery_enters_database_for_normal_desk_and_is_idempotent(tmp_path, monkeypatch):
    repository, calls = setup_page(tmp_path, monkeypatch)
    required = intake.collect_required_sources(checklist(), NOW, repository, "test")
    rows = repository.fetch_recent_items()
    assert required == {URL}
    assert calls == [URL]  # optional research is not a new unbounded feed
    assert len(rows) == 1
    assert rows[0]["source"] == "coverage_research"
    assert rows[0]["title"] == "Publisher headline"
    assert rows[0]["published_at"] == NOW.isoformat()
    assert rows[0]["text"].startswith("publisher evidence")
    assert intake.collect_required_sources(checklist(), NOW, repository, "test") == required
    assert len(repository.fetch_recent_items()) == 1
    assert calls == [URL]


@pytest.mark.parametrize("date,words", [(NOW - timedelta(days=3), 150),
                                       (NOW + timedelta(hours=1), 150), (NOW, 20)])
def test_stale_future_or_paywall_content_never_becomes_a_story(tmp_path, monkeypatch, date, words):
    repository, _ = setup_page(tmp_path, monkeypatch, date, words)
    original = checklist()
    assert intake.collect_required_sources(original, NOW, repository, "test") == set()
    assert repository.fetch_recent_items() == []
    assert original["events"][0]["mustCover"] is True


def test_intake_is_bounded_before_network_access(tmp_path, monkeypatch):
    repository, calls = setup_page(tmp_path, monkeypatch)
    research = checklist()
    research["events"][0]["sources"] = [
        {"url": f"https://example.org/{i}", "publishedAt": NOW.isoformat()} for i in range(31)]
    with pytest.raises(ValueError, match="limited to 30"):
        intake.collect_required_sources(research, NOW, repository, "test")
    assert calls == []


def test_new_mandatory_source_invalidates_same_run_draft_reuse(tmp_path, monkeypatch):
    output = tmp_path / "data/editorial"
    output.mkdir(parents=True)
    (output / "publisher-draft.json").write_text(json.dumps({"key": "same", "review": {"packets": [], "excluded": []}}))
    monkeypatch.setenv("NEWS_EDITORIAL_RUN_KEY", "same")
    monkeypatch.setattr(job, "run_editorial", lambda *_args, **_kw: {"fresh": True})
    args = SimpleNamespace(prepare_review=False, review_file=None)
    settings = SimpleNamespace(project_root=tmp_path / "scripts/news_collector")
    assert job.prepare_editorial(None, settings, {}, args, {URL}) == {"fresh": True}
