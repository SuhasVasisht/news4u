from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from news_collector.pipeline.editorial import (
    Decision, NoteSection, ReviewBatch, audio_url, clean_text, exclusion, source_hash, validate_decisions,
)
from news_collector.jobs.export_edition import assemble_reviewed
from news_collector.pipeline.dedupe import cluster_items
from news_collector.pipeline import editorial


NOW = datetime(2026, 9, 8, 14, tzinfo=timezone.utc)


def row(**changes):
    item = {"id": 1, "canonical_url": "https://example.com/report", "url": "https://example.com/report",
            "source": "ars_technica", "title": "A substantive report", "published_at": NOW.isoformat(),
            "image_url": None, "category": "tech", "importance_score": .8, "summary": "Evidence",
            "entities_json": "[]", "symbols_json": "[]"}
    return {**item, **changes}


def packet():
    return {"id": "one", "url": "https://example.com/report", "source": "ars_technica",
            "title": "A substantive report", "publishedAt": NOW.isoformat(), "kind": "reporting",
            "basis": "Publisher article", "audio": None, "duration": None, "truncated": False,
            "chunks": [{"id": "p1", "text": "Evidence"}], "wordCount": 500, "category": "tech"}


def decision(**changes):
    values = {"id": "one", "decision": "admit", "quality": 80, "importance": 70,
              "kind": "reporting", "reason": "Useful original evidence", "headline": "A substantive report",
              "summary": "A supported summary.", "points": ["Supported point"], "sections": [],
              "caveats": [], "evidence": ["p1"], "duplicate_of": None}
    return Decision(**{**values, **changes})


def test_product_hunt_and_routine_alerts_never_enter_editorial_review():
    assert exclusion(row(source="producthunt"), NOW)
    assert exclusion(row(title="Fund takes a large position in shares"), NOW)
    assert exclusion(row(canonical_url="https://marketbeat.com/filing"), NOW)
    assert exclusion(row(), NOW) is None


def test_longform_has_30_day_window_but_news_does_not():
    older = (NOW - timedelta(days=12)).isoformat()
    assert exclusion(row(published_at=older), NOW)
    assert exclusion(row(source="dwarkesh", published_at=older), NOW) is None
    assert exclusion(row(source="dwarkesh", published_at=(NOW - timedelta(days=31)).isoformat()), NOW)


def test_government_releases_have_a_week_to_be_considered_without_redating():
    older = (NOW - timedelta(days=5)).isoformat()
    assert exclusion(row(source="sec_press", published_at=older), NOW) is None
    assert exclusion(row(source="doj_antitrust", published_at=older), NOW) is None
    assert exclusion(row(source="sec_press", published_at=(NOW - timedelta(days=8)).isoformat()), NOW)


def test_podcast_budget_does_not_expand_when_categories_change(tmp_path, monkeypatch):
    current = datetime.now(timezone.utc).isoformat()
    rows = [row(source="lenny", category=category, canonical_url=f"https://example.com/{i}", published_at=current,
                raw_json=json.dumps({"links": [{"type": "audio/mpeg", "href": f"https://example.com/{i}.mp3"}]}))
            for i, category in enumerate(["tech", "other", "finance"])]
    repository = SimpleNamespace(fetch_recent_items=lambda **kwargs: rows)
    settings = SimpleNamespace(project_root=tmp_path / "scripts/news_collector", user_agent="Test")
    monkeypatch.setattr(editorial, "content_packet", lambda r, *_: {**packet(), "url": r["canonical_url"]})
    prepared = editorial.run_editorial(repository, settings, {"collectors": [{"name": "lenny"}]}, prepare_only=True)
    assert prepared["pending"] == 1


def test_new_required_article_cannot_be_crowded_out_by_older_research_rows(tmp_path, monkeypatch):
    current = datetime.now(timezone.utc).isoformat()
    required = 'https://example.com/new-mandatory-event'
    rows = [row(source='coverage_research', category='world', importance_score=1,
                canonical_url=f'https://example.com/old-{i}', published_at=current) for i in range(30)]
    rows.append(row(source='coverage_research', category='world', importance_score=0,
                    canonical_url=required, published_at=current))
    repository = SimpleNamespace(fetch_recent_items=lambda **_kwargs: rows)
    settings = SimpleNamespace(project_root=tmp_path / 'scripts/news_collector', user_agent='Test')
    monkeypatch.setattr(editorial, 'content_packet', lambda r, *_: {
        **packet(), 'id': r['canonical_url'].rsplit('/', 1)[-1], 'url': r['canonical_url'], 'source': r['source']})
    editorial.run_editorial(repository, settings,
        {'collectors': [{'name': 'coverage_research', 'editorial_limit': 30}]},
        prepare_only=True, required_urls={required})
    request = json.loads((tmp_path / 'data/editorial/review-request.json').read_text())
    assert len(request['packets']) == 30
    assert required in {p['url'] for p in request['packets']}


def test_already_published_latest_podcast_does_not_backfill_an_older_episode(tmp_path, monkeypatch):
    current = datetime.now(timezone.utc).isoformat()
    rows = [row(source="lenny", canonical_url=f"https://example.com/{i}", published_at=current,
                raw_json=json.dumps({"links": [{"type": "audio/mpeg", "href": f"https://example.com/{i}.mp3"}]})) for i in range(2)]
    repository = SimpleNamespace(fetch_recent_items=lambda **kwargs: rows)
    settings = SimpleNamespace(project_root=tmp_path / "scripts/news_collector", user_agent="Test")
    monkeypatch.setattr(editorial, "prior_match", lambda url, *_: {"date": "2026-09-08"} if url.endswith("/0") else None)
    def should_not_extract(*args):
        raise AssertionError("Neither the published episode nor the older backlog should be transcribed")
    monkeypatch.setattr(editorial, "content_packet", should_not_extract)
    prepared = editorial.run_editorial(repository, settings, {"collectors": [{"name": "lenny"}]}, prepare_only=True)
    assert prepared["pending"] == 0


def test_audio_survives_serialized_feedparser_links():
    assert audio_url({"links": [{"rel": "enclosure", "type": "audio/mpeg", "href": "https://example.com/audio.mp3"}]}) == "https://example.com/audio.mp3"
    assert audio_url({"links": [{"rel": "enclosure", "type": "image/jpeg", "href": "photo.jpg"}]}) is None


def test_review_rejects_missing_duplicate_ids_and_fabricated_evidence():
    validate_decisions(ReviewBatch(decisions=[decision()]), [packet()])
    for decisions in [[], [decision(), decision()], [decision(id="wrong")],
                      [decision(evidence=["p99"])], [decision(quality=64)]]:
        with pytest.raises(ValueError):
            validate_decisions(ReviewBatch(decisions=decisions), [packet()])


def test_show_notes_cannot_be_admitted_as_full_podcast():
    p = {**packet(), "kind": "podcast"}
    with pytest.raises(ValueError, match="Podcast"):
        validate_decisions(ReviewBatch(decisions=[decision(kind="podcast")]), [p])
    with pytest.raises(ValueError, match="completeness"):
        validate_decisions(ReviewBatch(decisions=[decision()]), [{**packet(), "truncated": True}])


def test_export_only_assembles_admitted_content_and_requires_fresh_review():
    review = {"generatedAt": NOW.isoformat(), "packets": [packet()],
              "decisions": {"one": decision().model_dump()}, "excluded": [], "policy": "test"}
    edition, audit = assemble_reviewed([row()], review, NOW, "America/Los_Angeles")
    assert edition["stories"][0]["summary"] == "A supported summary."
    assert edition["stories"][0]["quality"] == 80
    assert audit["reviewed_candidates"] == 1
    with pytest.raises(RuntimeError, match="review"):
        assemble_reviewed([row()], review, NOW + timedelta(days=2), "America/Los_Angeles")
    review["decisions"]["one"]["decision"] = "hold"
    with pytest.raises(RuntimeError, match="no stories"):
        assemble_reviewed([row()], review, NOW, "America/Los_Angeles")


def test_rediscovered_article_is_not_independent_confirmation():
    clustered = cluster_items([row(), row(id=2, source="techmeme")])
    assert clustered[0].confirmation_count == 1


def test_export_retains_discovery_credit_without_duplicating_story():
    review = {"generatedAt": NOW.isoformat(), "packets": [packet()],
              "decisions": {"one": decision().model_dump()}, "excluded": [], "policy": "test"}
    edition, _ = assemble_reviewed([row()], review, NOW, "America/Los_Angeles",
                                  discoveries=[row(source="tldr_tech"), row(source="hackernews")])
    assert len(edition["stories"]) == 1
    assert edition["stories"][0]["collectors"] == ["ars_technica", "hackernews", "tldr_tech"]


def test_export_validates_duplicate_references_across_the_complete_review():
    other = {**packet(), "id": "two", "url": "https://example.com/duplicate"}
    review = {"generatedAt": NOW.isoformat(), "packets": [packet(), other],
              "decisions": {"one": decision().model_dump(),
                            "two": decision(id="two", decision="hold", duplicate_of="one").model_dump()},
              "excluded": [], "policy": "test"}
    edition, _ = assemble_reviewed([row()], review, NOW, "America/Los_Angeles")
    assert [story["id"] for story in edition["stories"]] == ["one"]
    review["decisions"]["two"]["duplicate_of"] = "unknown"
    with pytest.raises(ValueError, match="Unknown duplicate"):
        assemble_reviewed([row()], review, NOW, "America/Los_Angeles")


def test_external_review_runs_without_calling_cli(tmp_path, monkeypatch):
    current = datetime.now(timezone.utc)
    settings = SimpleNamespace(project_root=tmp_path / "scripts/news_collector", user_agent="Test")
    repository = SimpleNamespace(fetch_recent_items=lambda **kwargs: [row(published_at=current.isoformat())])
    monkeypatch.setattr(editorial, "content_packet", lambda *_: packet())
    def unavailable(*args, **kwargs):
        raise AssertionError("Review-file mode must not call Codex CLI")
    monkeypatch.setattr(editorial, "codex_review", unavailable)
    config = {"collectors": [{"name": "ars_technica"}]}
    prepared = editorial.run_editorial(repository, settings, config, prepare_only=True)
    from pathlib import Path
    request = json.loads(Path(prepared["request"]).read_text())
    path = tmp_path / "desk.json"
    path.write_text(json.dumps({"requestHash": request["requestHash"], "reviewer": "Test desk",
                              "reviewedAt": current.isoformat(), "decisions": [decision().model_dump()],
                              "selection": {"selected_ids": ["one"], "excluded": []}}))
    monkeypatch.setattr(editorial, "content_packet", unavailable)
    result = editorial.run_editorial(repository, settings, config, review_file=path)
    assert result["selection"]["selected_ids"] == ["one"]
    assert result["reviewProvenance"]["mode"] == "review-file"


@pytest.mark.parametrize("damage", ["candidate_evidence", "candidate_json", "selection_id"])
def test_invalid_news_cache_regenerates_only_failed_work(tmp_path, monkeypatch, damage):
    current = datetime.now(timezone.utc)
    settings = SimpleNamespace(project_root=tmp_path / "scripts/news_collector", user_agent="Test")
    repository = SimpleNamespace(fetch_recent_items=lambda **kwargs: [row(published_at=current.isoformat())])
    monkeypatch.setattr(editorial, "content_packet", lambda *_: packet())
    calls = []
    def review(payload, *args):
        if args[-1] is editorial.EditionSelection:
            calls.append("selection")
            return editorial.EditionSelection(selected_ids=["one"], excluded=[])
        calls.append("candidate")
        return ReviewBatch(decisions=[decision()])
    monkeypatch.setattr(editorial, "codex_review", review)
    config = {"collectors": [{"name": "ars_technica"}]}
    editorial.run_editorial(repository, settings, config)
    output = tmp_path / "data/editorial"
    if damage.startswith("candidate"):
        cache = next(path for path in output.glob("review-*.json")
                     if len(path.stem.removeprefix("review-")) == 64)
        cache.write_text("{" if damage == "candidate_json" else ReviewBatch(
            decisions=[decision(evidence=["unknown-source-chunk"])]).model_dump_json())
    else:
        cache = next(output.glob("selection-*.json"))
        cache.write_text(editorial.EditionSelection(selected_ids=["not-in-shortlist"], excluded=[]).model_dump_json())
    calls.clear()
    result = editorial.run_editorial(repository, settings, config)
    assert result["selection"]["selected_ids"] == ["one"]
    assert calls == ["selection" if damage == "selection_id" else "candidate"]
    calls.clear()
    editorial.run_editorial(repository, settings, config)
    assert calls == []


def test_untrusted_html_is_only_text():
    assert "script" not in clean_text("<script>attack()</script><p>Evidence</p>")
    assert clean_text("<p>Evidence</p>") == "Evidence"


def test_export_rejects_source_changes_after_review():
    p = {**packet(), "inputHash": source_hash(row())}
    review = {"generatedAt": NOW.isoformat(), "packets": [p],
              "decisions": {"one": decision().model_dump()}, "excluded": [], "policy": "test"}
    with pytest.raises(RuntimeError, match="Source changed"):
        assemble_reviewed([row(summary="New facts")], review, NOW, "America/Los_Angeles")


def test_podcast_notes_must_reach_the_end_of_the_interview():
    p = {**packet(), "kind": "podcast", "wordCount": 10000,
         "chunks": [{"id": f"p{i}", "text": "Transcript"} for i in range(1, 31)]}
    sections = [NoteSection(heading=f"Theme {i}", body="Supported notes", evidence=[f"p{i}"])
                for i in range(1, 7)]
    with pytest.raises(ValueError, match="final part"):
        validate_decisions(ReviewBatch(decisions=[decision(kind="podcast", sections=sections)]), [p])
    sections[-1].evidence = ["p30"]
    validate_decisions(ReviewBatch(decisions=[decision(kind="podcast", sections=sections)]), [p])


def test_configured_candidate_budget_is_not_bypassed_by_previous_snapshot(tmp_path, monkeypatch):
    current = datetime.now(timezone.utc)
    rows = [row(id=i, canonical_url=f"https://example.com/{i}", url=f"https://example.com/{i}",
                published_at=(current - timedelta(minutes=i)).isoformat(), raw_json="{}") for i in range(5)]
    (tmp_path / "data").mkdir()
    (tmp_path / "data/edition.json").write_text(json.dumps({"stories": [{"url": rows[-1]["url"]}]}))
    settings = SimpleNamespace(project_root=tmp_path / "scripts/news_collector", user_agent="Test")
    repository = SimpleNamespace(fetch_recent_items=lambda **kwargs: rows)
    monkeypatch.setattr(editorial, "content_packet", lambda r, *_: {**packet(), "id": str(r["id"]), "url": r["url"]})

    def review(packets, *args):
        if args[-1] is editorial.EditionSelection:
            return editorial.EditionSelection(selected_ids=[p["id"] for p in packets["shortlist"]], excluded=[])
        return ReviewBatch(decisions=[decision(id=p["id"]) for p in packets])

    monkeypatch.setattr(editorial, "codex_review", review)
    result = editorial.run_editorial(repository, settings, {"collectors": [{"name": "ars_technica", "editorial_limit": 3}]})
    assert set(result["decisions"]) == {"0", "1", "2"}


def test_candidate_budget_keeps_highest_importance_items_before_newest(tmp_path, monkeypatch):
    current = datetime.now(timezone.utc)
    rows = [row(id=i, canonical_url=f"https://example.com/ranked/{i}",
                url=f"https://example.com/ranked/{i}", importance_score=score,
                published_at=(current - timedelta(minutes=i)).isoformat(), raw_json="{}")
            for i, score in enumerate([0.1, 0.9, 0.8, 0.7, 0.6])]
    settings = SimpleNamespace(project_root=tmp_path / "scripts/news_collector", user_agent="Test")
    repository = SimpleNamespace(fetch_recent_items=lambda **kwargs: rows)
    monkeypatch.setattr(editorial, "content_packet", lambda r, *_: {**packet(), "id": str(r["id"]), "url": r["url"]})

    def review(packets, *args):
        if args[-1] is editorial.EditionSelection:
            return editorial.EditionSelection(selected_ids=[p["id"] for p in packets["shortlist"]], excluded=[])
        return ReviewBatch(decisions=[decision(id=p["id"]) for p in packets])

    monkeypatch.setattr(editorial, "codex_review", review)
    result = editorial.run_editorial(repository, settings, {"collectors": [{"name": "ars_technica", "editorial_limit": 3}]})
    assert set(result["decisions"]) == {"1", "2", "3"}


def test_prior_publication_is_rejected_again_at_export():
    from news_collector.pipeline.publication_history import history_hash
    history = [{"date": "2026-09-07", "id": "old", "title": "Original report", "url": packet()["url"], "coverage": []}]
    review = {"generatedAt": NOW.isoformat(), "packets": [packet()], "decisions": {"one": decision().model_dump()},
              "excluded": [], "policy": "test", "historyHash": history_hash(history)}
    with pytest.raises(RuntimeError, match="Previously published"):
        assemble_reviewed([row()], review, NOW, "America/Los_Angeles", history)
    review["historyHash"] = "stale"
    with pytest.raises(RuntimeError, match="history changed"):
        assemble_reviewed([row()], review, NOW, "America/Los_Angeles", history)


def test_expired_article_cache_is_not_silently_reused(tmp_path, monkeypatch):
    cached = {"status": "editorial-full", "content_text": "Evidence " * 500,
              "checked_at": datetime.now(timezone.utc).isoformat()}
    repository = SimpleNamespace(get_cached_content=lambda _: cached)
    item = row(text="Brief source excerpt", raw_json="{}")
    assert editorial.content_packet(item, repository, "Test")["wordCount"] == 500
    cached["checked_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    def unavailable(*args):
        raise RuntimeError("Publisher unavailable")
    monkeypatch.setattr(editorial, "download", unavailable)
    assert editorial.content_packet(item, repository, "Test")["wordCount"] == 3


@pytest.mark.parametrize("metadata", [{"_content_basis": "publisher_article"},
                                      {"_coverage_discovery_url": "https://example.com/report"}])
def test_controlled_short_article_provenance_survives_legacy_metadata(metadata, monkeypatch):
    item = row(source="coverage_research", text="evidence " * 393, raw_json=json.dumps(metadata))
    calls = []
    repository = SimpleNamespace(get_cached_content=lambda *_: calls.append(True))
    result = editorial.content_packet(item, repository, "Test")
    assert result["basis"] == "Publisher article"
    assert result["wordCount"] == 393
    assert calls == []
    assert source_hash(item) != source_hash({**item, "raw_json": "{}"})


def test_equally_long_feed_excerpt_is_not_relabelled_when_article_fetch_fails(monkeypatch):
    item = row(text="feed evidence " * 150, raw_json=json.dumps({"_content_basis": "publisher_article"}))
    repository = SimpleNamespace(get_cached_content=lambda *_: None)
    monkeypatch.setattr(editorial, "download", lambda *_: (_ for _ in ()).throw(RuntimeError("Unavailable")))
    result = editorial.content_packet(item, repository, "Test")
    assert result["wordCount"] == 300
    assert result["basis"] == "Feed excerpt"


@pytest.mark.parametrize("acquisition", ["fresh_fetch", "fresh_cache"])
def test_acquired_short_article_has_publisher_basis_independent_of_length(monkeypatch, acquisition):
    text = "publisher evidence " * 150
    cached = ({"content_text": text, "status": "editorial-full",
               "checked_at": datetime.now(timezone.utc).isoformat()} if acquisition == "fresh_cache" else None)
    writes, downloads = [], []
    repository = SimpleNamespace(get_cached_content=lambda *_: cached, set_cached_content=lambda *args, **kwargs: writes.append(args))
    monkeypatch.setattr(editorial, "download", lambda *_: downloads.append(True) or (b"<article>Evidence</article>", "https://example.com/report"))
    monkeypatch.setattr(editorial, "extract_text_from_html", lambda *_: text)
    result = editorial.content_packet(row(text="feed evidence " * 150, raw_json="{}"), repository, "Test")
    assert result["basis"] == "Publisher article"
    assert result["wordCount"] == 300
    assert len(downloads) == (acquisition == "fresh_fetch")
    assert len(writes) == (acquisition == "fresh_fetch")


@pytest.mark.parametrize("damage", ["thin", "quality", "truncated", "unknown_evidence"])
def test_explicit_article_provenance_does_not_relax_admission_gates(damage):
    source = row(source="coverage_research", text="evidence " * (79 if damage == "thin" else 100),
                 raw_json=json.dumps({"_content_basis": "publisher_article"}))
    result = editorial.content_packet(source, None, "Test")
    assert result["basis"] == "Publisher article"
    if damage == "truncated":
        result["truncated"] = True
    assessed = decision(id=result["id"], quality=64 if damage == "quality" else 80,
                        evidence=["unknown"] if damage == "unknown_evidence" else ["p1"])
    with pytest.raises(ValueError):
        validate_decisions(ReviewBatch(decisions=[assessed]), [result])


def test_external_review_is_bound_to_sources_time_and_existing_quality_gates():
    payload = {"requestHash": "request-hash", "reviewer": "Explicit editorial desk",
               "reviewedAt": NOW.isoformat(), "decisions": [decision().model_dump()],
               "selection": {"selected_ids": ["one"], "excluded": []}}
    assert editorial.validate_external_review(payload, "request-hash", [packet()], NOW).reviewer
    with pytest.raises(ValueError, match="source packets"):
        editorial.validate_external_review(payload, "changed-source-hash", [packet()], NOW)
    with pytest.raises(ValueError, match="timestamp"):
        editorial.validate_external_review(payload, "request-hash", [packet()], NOW + timedelta(days=2))
    payload["decisions"] = []
    with pytest.raises(ValueError, match="every candidate"):
        editorial.validate_external_review(payload, "request-hash", [packet()], NOW)
    payload["decisions"] = [decision(quality=20).model_dump()]
    with pytest.raises(ValueError, match="quality"):
        editorial.validate_external_review(payload, "request-hash", [packet()], NOW)


def test_prepared_review_rejects_changed_source_records(tmp_path, monkeypatch):
    from pathlib import Path
    current = datetime.now(timezone.utc)
    rows = [row(published_at=current.isoformat())]
    settings = SimpleNamespace(project_root=tmp_path / "scripts/news_collector", user_agent="Test")
    repository = SimpleNamespace(fetch_recent_items=lambda **kwargs: rows)
    monkeypatch.setattr(editorial, "content_packet", lambda r, *_: {**packet(), "inputHash": source_hash(r)})
    config = {"collectors": [{"name": "ars_technica"}]}
    prepared = editorial.run_editorial(repository, settings, config, prepare_only=True)
    request = json.loads(Path(prepared["request"]).read_text())
    path = tmp_path / "desk.json"
    path.write_text(json.dumps({"requestHash": request["requestHash"], "reviewer": "Test desk",
        "reviewedAt": current.isoformat(), "decisions": [decision().model_dump()],
        "selection": {"selected_ids": ["one"], "excluded": []}}))
    rows[0]["summary"] = "Materially changed evidence"
    with pytest.raises(ValueError, match="Source changed"):
        editorial.run_editorial(repository, settings, config, review_file=path)
