from copy import deepcopy
from datetime import datetime, timezone
import json
from news_collector.pipeline.context_budget import bounded_history, bound_context
from news_collector.pipeline.quality_review import coverage_context


def test_coverage_discards_irrelevant_backlog_but_retains_exact_sources_and_prior_summaries():
    history = [{'id': str(i), 'date': '2026-10-10', 'title': 'Prior report', 'url': f'https://old.org/{i}',
                'summary': 'The original contract is already published.', 'points': ['One-year maintenance.'],
                'sections': [{'heading': 'Notes', 'body': 'Long notes ' * 300}],
                'caveats': ['Old caveat']} for i in range(360)]
    candidate_index = [{'url': f'https://old.org/excluded/{i}', 'decision': 'excluded_before_review',
                        'reason': 'outside_editorial_window'} for i in range(3656)]
    candidate_index += [{'id': 'new', 'url': 'https://new.org/report', 'decision': 'admit'},
                        {'url': 'https://new.org/budget', 'decision': 'excluded_before_review', 'reason': 'candidate_budget'}]
    request = {'history': history, 'candidate_index': candidate_index,
               'checklist': {'events': [{'sources': [{'url': 'https://old.org/excluded/1'}]}]}}
    original = deepcopy(request)
    brief, candidates, counts = coverage_context(request)
    assert len(json.dumps(request)) > 1_048_576
    assert len(json.dumps([brief, candidates, counts])) < 500_000
    assert [item['id'] for item in brief] == [item['id'] for item in history]
    assert all(item['summary'] and item['points'] for item in brief)
    assert {item['url'] for item in candidates} == {
        'https://old.org/excluded/1', 'https://new.org/report', 'https://new.org/budget'}
    assert counts['outside_editorial_window'] == 3655
    assert request == original  # Complete hash-bound audit evidence is not edited.


def test_large_archive_retrieval_keeps_old_topical_prose_and_recent_context_in_budget():
    cutoff = datetime(2026, 10, 12, tzinfo=timezone.utc)
    history = [{'id': str(i), 'date': '2026-01-01', 'title': 'Unrelated football match',
                'summary': 'Football results.', 'sections': [{'body': 'Football season ' * 1000}]}
               for i in range(1000)]
    history += [{'id': 'old-deno', 'date': '2026-01-01', 'title': 'Cloudflare acquires Deno',
                 'summary': 'One-year maintenance followed by shutdown.',
                 'sections': [{'body': 'Runtime development ends after one year.'}]},
                {'id': 'recent', 'date': '2026-10-11', 'title': 'New event', 'summary': 'Recent context.'}]
    original = deepcopy(history)
    found = bounded_history(history, 'Cloudflare Deno runtime maintenance', cutoff)
    assert len(json.dumps(found, ensure_ascii=False)) < 350_000
    assert {'old-deno', 'recent'} <= {entry['id'] for entry in found}
    assert next(entry for entry in found if entry['id'] == 'old-deno')['sections']
    payload = {'cutoff': cutoff.isoformat(), 'history': history,
               'decisions': [{'headline': 'Cloudflare plans Deno maintenance'}]}
    result = bound_context(payload)
    assert result['history_context_scope']['history']['archiveEntries'] == 1002
    assert result['history_context_scope']['history']['retrievedEntries'] < 1002
    assert history == original
