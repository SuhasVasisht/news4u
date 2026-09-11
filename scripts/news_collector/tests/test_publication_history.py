import json
from news_collector.pipeline.publication_history import load_history, prior_match


def test_history_uses_published_prior_days_including_superseded_versions(tmp_path):
    for directory, day in [("2026-09-08", "2026-09-08"), ("2026-09-08-rabcdef123456", "2026-09-08"), ("2026-09-09", "2026-09-09")]:
        root = tmp_path / "data/cloudflare-published/editions" / directory
        root.mkdir(parents=True)
        (root / "edition.json").write_text(json.dumps({"date": day, "editorialReviewedAt": "reviewed", "stories": [
            {"id": directory, "title": "A report", "url": f"https://example.com/{directory}", "coverage": []}]}))
    assert len(load_history(tmp_path, "2026-09-09")) == 2


def test_rediscovery_and_reworded_headlines_do_not_create_new_stories():
    history = [{"date": "2026-09-08", "id": "old", "url": "https://example.com/main", "title": "Company announces acquisition of major cloud security provider",
                "coverage": [{"url": "https://another.com/story", "title": "Original source headline"}]}]
    assert prior_match("https://another.com/story?utm_source=tldr", "New headline", history, "2026-09-09")["match"] == "published_url"
    assert prior_match("https://third.com/new-url", "Company announces acquisition of a major cloud security provider", history, "2026-09-09")["match"] == "published_title"
    assert prior_match("https://third.com/update", "Court blocks company acquisition after competition review", history, "2026-09-09") is None


def test_periodic_reports_with_different_numbers_are_not_fuzzy_duplicates():
    history = [{"date": "2026-09-08", "id": "old", "url": "https://example.com/old", "title": "US weekly unemployment claims rise to 210000 in latest report", "coverage": []}]
    assert prior_match("https://example.com/new", "US weekly unemployment claims rise to 230000 in latest report", history, "2026-09-09") is None


def test_history_retains_audited_event_identity(tmp_path):
    root = tmp_path / "data/cloudflare-published/editions/2026-09-09"
    root.mkdir(parents=True)
    (root / "edition.json").write_text(json.dumps({"date": "2026-09-09", "editorialReviewedAt": "reviewed",
        "stories": [{"id": "story", "title": "Report", "url": "https://example.org/report", "eventKey": "bank-rate-decision"}]}))
    assert load_history(tmp_path, "2026-09-10")[0]["eventKey"] == "bank-rate-decision"
