"""A held companion must not strand an independently usable mandatory account."""
from copy import deepcopy
from datetime import datetime

import pytest

from news_collector.pipeline import quality_review
from news_collector.pipeline.edition_audit import CoverageAuditReview, validate_audit
from test_edition_audit import fixture, NOW
from test_quality_review import reviewed_fixture


@pytest.mark.parametrize('remaining_covers_event', [True, False])
def test_failed_companion_requires_new_coverage_check_not_a_new_factual_verdict(tmp_path, monkeypatch, remaining_covers_event):
    original, envelope = fixture()
    review = reviewed_fixture()
    review.pop('finalAudit')
    first = review['packets'][0]
    review['packets'].append({**deepcopy(first), 'id': 'b', 'url': 'https://example.org/companion'})
    review['decisions']['b'] = {**deepcopy(review['decisions']['a']), 'id': 'b',
                              'headline': 'Bank explains its rate decision'}
    review['selection'] = {'selected_ids': ['a', 'b'], 'excluded': []}
    companion = deepcopy(envelope['review']['stories'][0])
    companion.update(id='b', event_key='bank-decision-explanation', verdict='hold',
                     reason='Attribution for the companion account remains incomplete.')
    companion['claims'][0]['passage'] = review['decisions']['b']['headline']
    envelope['review']['stories'].append(companion)
    envelope['review']['coverage'][0]['story_ids'] = ['a', 'b']
    checklist = original['checklist']
    request = quality_review.audit_request(review, [], checklist)
    envelope['requestHash'] = request['requestHash']
    report = validate_audit(envelope, request, NOW)
    assert report.status == 'blocked'
    clock = type('Clock', (datetime,), {'now': classmethod(lambda cls, tz=None: NOW)})
    monkeypatch.setattr(quality_review, 'datetime', clock)
    monkeypatch.setattr('news_collector.pipeline.edition_audit.datetime', clock)
    calls = []
    def reconcile(payload, prompt, output, result_type, **kwargs):
        calls.append(payload)
        assert result_type is CoverageAuditReview
        assert [story['id'] for story in payload['storyAuditFindings']] == ['a']
        item = deepcopy(envelope['review']['coverage'][0])
        item.update(story_ids=['a'] if remaining_covers_event else [],
                    status='covered' if remaining_covers_event else 'missing',
                    cause='covered' if remaining_covers_event else 'selection',
                    reason='The retained account covers the event.' if remaining_covers_event
                           else 'The retained account omits the mandatory development.')
        return CoverageAuditReview(coverage=[item])
    monkeypatch.setattr(quality_review, 'codex_review', reconcile)
    output = tmp_path / 'data/editorial'
    result = quality_review.prune_optional_audit_failures(tmp_path, review, [], checklist,
        request, report, output, '2026-09-10')
    assert result is not None
    assert review['selection']['selected_ids'] == ['a']
    assert result.status == ('passed' if remaining_covers_event else 'blocked')
    assert checklist['events'][0]['mustCover'] is True
    assert len(calls) == 1
    if remaining_covers_event:
        assert quality_review.verify_final_audit(review, [], NOW).status == 'passed'
    else:
        assert 'finalAudit' not in review
        assert any('Must-cover event unresolved' in issue for issue in result.blockers)


def test_coverage_subset_transport_failure_resumes_without_retrying_held_facts(tmp_path, monkeypatch):
    from news_collector.pipeline.editorial import EditionSelection
    from news_collector.pipeline.edition_audit import StoryAuditReview
    original, envelope = fixture()
    review = reviewed_fixture()
    review.pop('finalAudit')
    first = review['packets'][0]
    first['kind'] = 'reporting'
    review['packets'].append({**deepcopy(first), 'id': 'b', 'url': 'https://example.org/companion'})
    review['decisions']['b'] = {**deepcopy(review['decisions']['a']), 'id': 'b',
                              'headline': 'Bank explains its rate decision'}
    review['selection'] = {'selected_ids': ['a', 'b'], 'excluded': []}
    companion = deepcopy(envelope['review']['stories'][0])
    companion.update(id='b', event_key='bank-decision-explanation', verdict='hold',
                     reason='Attribution for the companion account remains incomplete.')
    companion['claims'][0]['passage'] = review['decisions']['b']['headline']
    envelope['review']['stories'].append(companion)
    envelope['review']['coverage'][0]['story_ids'] = ['a', 'b']
    clock = type('Clock', (datetime,), {'now': classmethod(lambda cls, tz=None: NOW)})
    monkeypatch.setattr(quality_review, 'datetime', clock)
    monkeypatch.setattr('news_collector.pipeline.edition_audit.datetime', clock)
    monkeypatch.setattr(quality_review, 'load_history', lambda *_: [])
    monkeypatch.setattr(quality_review, 'discover_coverage', lambda *_: original['checklist'])
    factual_calls, subset_calls = [], []
    def desk(payload, prompt, output, result_type, **kwargs):
        if result_type is EditionSelection:
            return EditionSelection(selected_ids=['a', 'b'], excluded=[])
        if result_type is StoryAuditReview:
            factual_calls.append(payload['auditStoryIds'])
            return StoryAuditReview(stories=envelope['review']['stories'])
        assert result_type is CoverageAuditReview
        item = deepcopy(envelope['review']['coverage'][0])
        if payload['selection']['selected_ids'] == ['a']:
            subset_calls.append(payload)
            if len(subset_calls) == 1:
                raise RuntimeError('temporary coverage transport failure')
            item['story_ids'] = ['a']
        return CoverageAuditReview(coverage=[item])
    monkeypatch.setattr(quality_review, 'codex_review', desk)
    with pytest.raises(RuntimeError, match='temporary coverage transport'):
        quality_review.run_quality_review(tmp_path, review)
    # Resume the on-disk snapshot the publisher job actually retains.
    import json
    resumed = json.loads((tmp_path / 'data/editorial/latest.json').read_text())
    assert resumed['selection']['selected_ids'] == ['a', 'b']
    assert 'finalAudit' not in resumed
    result = quality_review.run_quality_review(tmp_path, resumed)
    assert result.status == 'passed'
    assert factual_calls == [['a', 'b']]
    assert len(subset_calls) == 2
    assert resumed['selection']['selected_ids'] == ['a']
    assert quality_review.verify_final_audit(resumed, [], NOW).status == 'passed'
