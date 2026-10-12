from news_collector.jobs.export_edition import assemble_reviewed
from test_editorial import NOW, row, packet, decision


def test_audited_event_selection_is_not_merged_by_title_similarity():
    titles = ["Senate opens inquiry into AI incident", "Senate closes inquiry into AI incident"]
    packets = [{**packet(), "id": str(i), "url": f"https://example.com/{i}", "title": title}
               for i, title in enumerate(titles)]
    review = {"generatedAt": NOW.isoformat(), "cutoff": NOW.isoformat(), "packets": packets,
              "decisions": {p["id"]: decision(id=p["id"], headline=p["title"]).model_dump() for p in packets},
              "selection": {"selected_ids": ["0", "1"], "excluded": []}, "excluded": [], "policy": "test"}
    rows = [row(canonical_url=p["url"], title=p["title"]) for p in packets]
    snapshot, _ = assemble_reviewed(rows, review, NOW, "America/Los_Angeles", audited_selection=True)
    assert [s["id"] for s in snapshot["stories"]] == ["0", "1"]


def test_changed_excluded_candidate_does_not_invalidate_selected_edition():
    from news_collector.pipeline.editorial import source_hash
    first = row()
    other = row(id=2, canonical_url='https://example.com/excluded', title='Excluded candidate')
    packets = [{**packet(), 'inputHash': source_hash(first)},
               {**packet(), 'id': 'two', 'url': other['canonical_url'], 'inputHash': source_hash(other)}]
    review = {'generatedAt': NOW.isoformat(), 'cutoff': NOW.isoformat(), 'packets': packets,
              'decisions': {'one': decision().model_dump(), 'two': decision(id='two').model_dump()},
              'selection': {'selected_ids': ['one'], 'excluded': [{'id': 'two', 'reason': 'Lower priority'}]},
              'excluded': [], 'policy': 'test'}
    edition, _ = assemble_reviewed([first, {**other, 'summary': 'Updated optional candidate'}], review,
                                  NOW, 'America/Los_Angeles', audited_selection=True)
    assert [story['id'] for story in edition['stories']] == ['one']


def test_missing_selected_source_cannot_be_silently_dropped_or_substituted():
    import pytest
    review = {'generatedAt': NOW.isoformat(), 'cutoff': NOW.isoformat(), 'packets': [packet()],
              'decisions': {'one': decision().model_dump()},
              'selection': {'selected_ids': ['one'], 'excluded': []}, 'excluded': [], 'policy': 'test'}
    for rows in ([], [row(source='other-feed')]):
        with pytest.raises(RuntimeError, match='Source changed'):
            assemble_reviewed(rows, review, NOW, 'America/Los_Angeles', audited_selection=True)


def test_publisher_cap_groups_bbc_feeds_and_preserves_priority_without_replacements():
    from news_collector.pipeline.publishers import limit_publishers
    packets = [{'id': str(i), 'url': f'https://{host}/news/{i}', 'source': f'feed-{i}'}
               for i, host in enumerate(['bbc.com', 'bbc.co.uk', 'bbc.com', 'bbc.co.uk', 'bbc.com', 'theguardian.com'])]
    selection = {'selected_ids': [str(i) for i in range(6)], 'excluded': []}
    capped = limit_publishers(selection, packets)
    assert capped['selected_ids'] == ['0', '1', '2', '3', '5']
    assert [item['id'] for item in capped['excluded']] == ['4']
    assert limit_publishers(capped, packets) == capped
    assert selection['selected_ids'] == [str(i) for i in range(6)]


import pytest
from datetime import datetime, timedelta, timezone


def reviewed_fixture(cutoff, published, source='ars_technica', kind='reporting'):
    source_row = row(source=source, published_at=published.isoformat())
    source_packet = {**packet(), 'source': source, 'publishedAt': published.isoformat()}
    review = {'generatedAt': cutoff.isoformat(), 'cutoff': cutoff.isoformat(),
              'packets': [source_packet], 'decisions': {'one': decision(kind=kind).model_dump()},
              'selection': {'selected_ids': ['one'], 'excluded': []}, 'excluded': [], 'policy': 'test'}
    return source_row, review


@pytest.mark.parametrize('source,window', [('ars_technica', timedelta(hours=48)),
                                         ('sec_press', timedelta(days=7)),
                                         ('bytebytego', timedelta(days=30))])
@pytest.mark.parametrize('delay', [timedelta(minutes=20), timedelta(hours=5)])
def test_audited_admission_window_does_not_move_during_review_or_retry(source, window, delay):
    cutoff = datetime(2026, 10, 11, 14, 9, 15, tzinfo=timezone.utc)
    published = cutoff - window + timedelta(minutes=6)
    source_row, review = reviewed_fixture(cutoff, published, source)
    edition, _ = assemble_reviewed([source_row], review, cutoff + delay, 'America/Los_Angeles',
                                  audited_selection=True)
    assert [s['id'] for s in edition['stories']] == ['one']
    assert edition['stories'][0]['publishedAt'] == published.isoformat()
    assert edition['generatedAt'] == (cutoff + delay).isoformat()


def test_exact_oct11_failure_survives_export_without_redating():
    cutoff = datetime.fromisoformat('2026-10-11T14:09:15.809999+00:00')
    published = datetime.fromisoformat('2026-10-09T14:15:32+00:00')
    source_row, review = reviewed_fixture(cutoff, published, 'newsapi')
    edition, _ = assemble_reviewed([source_row], review,
        datetime.fromisoformat('2026-10-11T14:28:04+00:00'), 'America/Los_Angeles', audited_selection=True)
    assert len(edition['stories']) == 1
    assert edition['stories'][0]['publishedAt'] == published.isoformat()


@pytest.mark.parametrize('bad_cutoff', [None, 'invalid', '2026-09-08T14:00:00',
    (NOW - timedelta(hours=25)).isoformat(), (NOW + timedelta(minutes=1)).isoformat(),
    (NOW - timedelta(hours=8)).isoformat()])
def test_frozen_window_cannot_revive_invalid_stale_future_or_other_day_review(bad_cutoff):
    source_row, review = reviewed_fixture(NOW, NOW)
    review['cutoff'] = bad_cutoff
    with pytest.raises(RuntimeError, match='cutoff'):
        assemble_reviewed([source_row], review, NOW, 'America/Los_Angeles', audited_selection=True)


@pytest.mark.parametrize('offset', [timedelta(hours=-48, seconds=-1), timedelta(minutes=6)])
def test_audited_story_ineligible_at_original_cutoff_still_blocks_export(offset):
    source_row, review = reviewed_fixture(NOW, NOW + offset)
    with pytest.raises(RuntimeError, match='one.*ineligible.*outside_editorial_window'):
        assemble_reviewed([source_row], review, NOW + timedelta(minutes=20), 'America/Los_Angeles',
                          audited_selection=True)


def test_analysis_sector_is_stable_across_forty_eight_hour_boundary():
    source_row, review = reviewed_fixture(NOW, NOW - timedelta(hours=48) + timedelta(minutes=5),
                                         'bytebytego', 'analysis')
    early, _ = assemble_reviewed([source_row], review, NOW, 'America/Los_Angeles', audited_selection=True)
    late, _ = assemble_reviewed([source_row], review, NOW + timedelta(minutes=20), 'America/Los_Angeles',
                               audited_selection=True)
    assert early['stories'][0]['sector'] == late['stories'][0]['sector'] == 'Technology'
