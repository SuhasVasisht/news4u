"""A next-day mandatory discovery must not force yesterday's held duplicate."""
from copy import deepcopy
from datetime import datetime

import pytest

from news_collector.pipeline import quality_review
from news_collector.pipeline.edition_audit import CoverageAuditReview, validate_audit
from news_collector.pipeline.publication_history import history_hash
from test_edition_audit import fixture, NOW
from test_quality_review import reviewed_fixture


@pytest.mark.parametrize('coverage_status', ['already_published', 'new_development', 'invalid_fresh_mapping'])
def test_mandatory_repeat_recovery_requires_independent_historical_coverage(tmp_path, monkeypatch, coverage_status):
    original, envelope = fixture()
    review = reviewed_fixture()
    review.pop('finalAudit')
    first = review['packets'][0]
    review['packets'].append({**deepcopy(first), 'id': 'b', 'url': 'https://example.org/other'})
    review['decisions']['b'] = {**deepcopy(review['decisions']['a']), 'id': 'b', 'headline': 'Other bank cuts rates'}
    review['selection'] = {'selected_ids': ['a', 'b'], 'excluded': []}
    history = [{'id': 'yesterday', 'eventKey': 'bank-rate-decision', 'date': '2026-09-09',
                'url': first['url'], 'title': 'Earlier bank decision', 'summary': 'The bank cut rates.',
                'coverage': []}]
    review['historyHash'] = history_hash(history)
    checklist = original['checklist']
    request = quality_review.audit_request(review, history, checklist)
    repeat = deepcopy(envelope['review']['stories'][0])
    repeat.update(verdict='hold', priorStoryIds=['yesterday'],
                  reason='Same event as yesterday, with no evidence-backed material development.')
    fresh = deepcopy(envelope['review']['stories'][0])
    fresh.update(id='b', event_key='different-bank-rate-decision')
    fresh['claims'][0]['passage'] = review['decisions']['b']['headline']
    stories = quality_review.StoryAuditReview(stories=[repeat, fresh]).stories
    clock = type('Clock', (datetime,), {'now': classmethod(lambda cls, tz=None: NOW)})
    monkeypatch.setattr(quality_review, 'datetime', clock)
    monkeypatch.setattr('news_collector.pipeline.edition_audit.datetime', clock)
    calls = []
    def reconcile(payload, prompt, output, result_type, **kwargs):
        calls.append(payload)
        assert result_type is CoverageAuditReview  # No new attempt to approve the held story.
        held = next(item for item in payload['storyAuditFindings'] if item['id'] == 'a')
        assert held['verdict'] == 'hold' and held['priorStoryIds'] == ['yesterday']
        assert held['materialUpdate'] is None and held['materialUpdateEvidence'] == []
        item = deepcopy(envelope['review']['coverage'][0])
        if coverage_status == 'already_published':
            item.update(story_ids=[], prior_story_ids=['yesterday'], status='not_applicable',
                        cause='previously_published', reason='The historical account covers this same event, with no material development.')
        elif coverage_status == 'new_development':
            item.update(story_ids=[], status='missing', cause='selection',
                        reason='The checklist describes a new development absent from the selected copy.')
        return CoverageAuditReview(coverage=[item])
    monkeypatch.setattr(quality_review, 'codex_review', reconcile)
    prompt = tmp_path / 'edition-audit-prompt.md'
    prompt.write_text('Factual desk')
    prompt.with_name('coverage-audit-prompt.md').write_text('Independent coverage desk')
    if coverage_status == 'invalid_fresh_mapping':
        with pytest.raises(ValueError, match='cannot count a repeat'):
            quality_review.run_batched_audit(request, prompt, tmp_path, stories)
        assert not list((tmp_path / 'audit-calls').glob('*.json'))
        return
    result = quality_review.run_batched_audit(request, prompt, tmp_path, stories)
    report = validate_audit({'requestHash': request['requestHash'], 'reviewer': 'independent final desk',
                             'reviewedAt': NOW.isoformat(), 'review': result.model_dump(mode='json')}, request, NOW)
    assert report.status == 'blocked'  # The duplicate cannot itself be published.
    pruned = quality_review.prune_optional_audit_failures(tmp_path, review, history, checklist,
             request, report, tmp_path / 'data/editorial', '2026-09-10')
    assert review['selection']['selected_ids'] == ['b']
    assert checklist['events'][0]['mustCover'] is True
    if coverage_status == 'already_published':
        assert pruned.status == 'passed'
        assert quality_review.verify_final_audit(review, history, NOW).status == 'passed'
        assert pruned.review.coverage[0].prior_story_ids == ['yesterday']
    else:
        assert pruned.status == 'blocked'
        assert any('Must-cover event unresolved' in issue for issue in pruned.blockers)
        assert 'finalAudit' not in review
    assert len(calls) == 1
