from news_collector.jobs.export_edition import assemble_reviewed
from test_editorial import NOW, row, packet, decision


def test_audited_event_selection_is_not_merged_by_title_similarity():
    titles = ["Senate opens inquiry into AI incident", "Senate closes inquiry into AI incident"]
    packets = [{**packet(), "id": str(i), "url": f"https://example.com/{i}", "title": title}
               for i, title in enumerate(titles)]
    review = {"generatedAt": NOW.isoformat(), "packets": packets,
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
    review = {'generatedAt': NOW.isoformat(), 'packets': packets,
              'decisions': {'one': decision().model_dump(), 'two': decision(id='two').model_dump()},
              'selection': {'selected_ids': ['one'], 'excluded': [{'id': 'two', 'reason': 'Lower priority'}]},
              'excluded': [], 'policy': 'test'}
    edition, _ = assemble_reviewed([first, {**other, 'summary': 'Updated optional candidate'}], review,
                                  NOW, 'America/Los_Angeles', audited_selection=True)
    assert [story['id'] for story in edition['stories']] == ['one']


def test_missing_selected_source_cannot_be_silently_dropped_or_substituted():
    import pytest
    review = {'generatedAt': NOW.isoformat(), 'packets': [packet()],
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
