"""Inject external failures into persisted daily review, without live model calls."""
from copy import deepcopy
from datetime import datetime, timedelta
import json

import pytest

from news_collector.pipeline import quality_review
from news_collector.pipeline.edition_audit import CoverageAuditReview, StoryAuditReview
from news_collector.pipeline.editorial import EditionSelection
from test_edition_audit import fixture, NOW
from test_quality_review import reviewed_fixture


def setup_run(monkeypatch):
    clock_now = [NOW]
    clock = type('Clock', (datetime,), {'now': classmethod(lambda cls, tz=None: clock_now[0])})
    monkeypatch.setattr(quality_review, 'datetime', clock)
    monkeypatch.setattr('news_collector.pipeline.edition_audit.datetime', clock)
    request, envelope = fixture()
    monkeypatch.setattr(quality_review, 'load_history', lambda *_: [])
    monkeypatch.setattr(quality_review, 'discover_coverage', lambda *_: request['checklist'])
    review = reviewed_fixture()
    review.pop('finalAudit')
    review['packets'][0]['kind'] = 'reporting'
    return review, envelope, clock_now


@pytest.mark.parametrize('failure_at', ['coverage', 'later_story_batch'])
@pytest.mark.parametrize('outage', [timedelta(minutes=20), timedelta(hours=8)])
def test_hold_survives_external_failure_and_refreshed_collection_cutoff(tmp_path, monkeypatch, failure_at, outage):
    review, envelope, clock_now = setup_run(monkeypatch)
    if failure_at == 'later_story_batch':
        # Production batches contain five stories; fail after batch one is saved.
        for index in range(1, 6):
            key = f'b{index}'
            review['packets'].append({**deepcopy(review['packets'][0]), 'id': key,
                                     'url': f'https://publisher-{index}.test/report'})
            review['decisions'][key] = {**deepcopy(review['decisions']['a']), 'id': key}
    held_calls, failed = [], [False]
    def desk(payload, prompt, output, result_type, **kwargs):
        if result_type is EditionSelection:
            return EditionSelection(selected_ids=[item['id'] for item in payload['shortlist']], excluded=[])
        if result_type is StoryAuditReview:
            ids = payload['auditStoryIds']
            if 'a' in ids:
                held_calls.append(ids)
            if failure_at == 'later_story_batch' and 'a' not in ids and not failed[0]:
                failed[0] = True
                raise RuntimeError('injected later factual batch outage')
            stories = []
            for key in ids:
                story = deepcopy(envelope['review']['stories'][0])
                story.update(id=key, event_key='event-' + key)
                if key == 'a':
                    # A second fresh review would accidentally approve this.
                    story.update(verdict='hold' if len(held_calls) == 1 else 'pass',
                                 reason='The unchanged source has unresolved attribution.')
                stories.append(story)
            return StoryAuditReview(stories=stories)
        assert result_type is CoverageAuditReview
        if failure_at == 'coverage' and not failed[0]:
            failed[0] = True
            raise RuntimeError('injected coverage service outage')
        return CoverageAuditReview(coverage=envelope['review']['coverage'])
    monkeypatch.setattr(quality_review, 'codex_review', desk)
    with pytest.raises(RuntimeError, match='injected'):
        quality_review.run_quality_review(tmp_path, review)
    output = tmp_path / 'data/editorial'
    assert not (output / 'quality-review-response.json').exists()
    resumed = json.loads((output / 'latest.json').read_text())
    clock_now[0] += outage
    resumed.update(cutoff=clock_now[0].isoformat(), generatedAt=clock_now[0].isoformat())
    with pytest.raises(ValueError, match='blocked publication'):
        quality_review.run_quality_review(tmp_path, resumed)
    assert list(output.glob('audit-record-stories-*.json'))
    assert len(held_calls) == 1
    assert 'finalAudit' not in resumed
    report = json.loads((output / 'quality-audit.json').read_text())
    assert report['status'] == 'blocked'
    assert next(story for story in report['review']['stories'] if story['id'] == 'a')['verdict'] == 'hold'


@pytest.mark.parametrize('cause', ['discovery', 'extraction', 'deduplication', 'selection'])
def test_real_missing_mandatory_coverage_remains_blocked_until_new_evidence_arrives(tmp_path, monkeypatch, cause):
    review, envelope, clock_now = setup_run(monkeypatch)
    factual_calls, coverage_calls = [], []
    def desk(payload, prompt, output, result_type, **kwargs):
        if result_type is EditionSelection:
            return EditionSelection(selected_ids=[item['id'] for item in payload['shortlist']], excluded=[])
        if result_type is StoryAuditReview:
            factual_calls.append(payload['auditStoryIds'])
            return StoryAuditReview(stories=[{**deepcopy(envelope['review']['stories'][0]),
                'id': key, 'event_key': 'bank-development-' + key} for key in payload['auditStoryIds']])
        assert result_type is CoverageAuditReview
        coverage_calls.append(payload['selection']['selected_ids'])
        item = deepcopy(envelope['review']['coverage'][0])
        if 'b' not in payload['selection']['selected_ids']:
            item.update(story_ids=[], status='missing', cause=cause,
                        reason='The genuinely new mandatory development is not in the supplied evidence.')
        else:
            item.update(story_ids=['b'], reason='The newly arrived primary report covers the mandatory development.')
        return CoverageAuditReview(coverage=[item])
    monkeypatch.setattr(quality_review, 'codex_review', desk)
    for attempt in range(2):
        if attempt:
            review = json.loads((tmp_path / 'data/editorial/latest.json').read_text())
            clock_now[0] += timedelta(minutes=10)
            review.update(cutoff=clock_now[0].isoformat(), generatedAt=clock_now[0].isoformat())
        with pytest.raises(ValueError, match='Must-cover event unresolved'):
            quality_review.run_quality_review(tmp_path, review)
        assert 'finalAudit' not in review
        report = json.loads((tmp_path / 'data/editorial/quality-audit.json').read_text())
        assert report['status'] == 'blocked'
        assert report['review']['coverage'][0]['cause'] == cause
    # A source recovers and collection now supplies an actual new packet, rather
    # than a new clock or a permissive re-review of identical inputs.
    review = json.loads((tmp_path / 'data/editorial/latest.json').read_text())
    clock_now[0] += timedelta(minutes=10)
    review.update(cutoff=clock_now[0].isoformat(), generatedAt=clock_now[0].isoformat())
    review['packets'].append({**deepcopy(review['packets'][0]), 'id': 'b',
                             'url': 'https://example.org/new-primary-development',
                             'publishedAt': clock_now[0].isoformat()})
    review['decisions']['b'] = {**deepcopy(review['decisions']['a']), 'id': 'b'}
    result = quality_review.run_quality_review(tmp_path, review)
    assert result.status == 'passed'
    assert factual_calls == [['a'], ['b']]
    assert result.metrics['mustCoverEvents'] == 1
    assert result.review.coverage[0].story_ids == ['b']
    assert quality_review.verify_final_audit(review, [], clock_now[0]).status == 'passed'


def test_previous_day_partial_hold_requires_new_factual_review(tmp_path, monkeypatch):
    review, envelope, clock_now = setup_run(monkeypatch)
    calls, outage = [], [True]
    def desk(payload, prompt, output, result_type, **kwargs):
        if result_type is EditionSelection:
            return EditionSelection(selected_ids=['a'], excluded=[])
        if result_type is StoryAuditReview:
            calls.append(payload['cutoff'])
            story = deepcopy(envelope['review']['stories'][0])
            story.update(verdict='hold', reason='The source still has unresolved attribution.')
            return StoryAuditReview(stories=[story])
        if outage[0]:
            outage[0] = False
            raise RuntimeError('injected coverage outage')
        return CoverageAuditReview(coverage=envelope['review']['coverage'])
    monkeypatch.setattr(quality_review, 'codex_review', desk)
    with pytest.raises(RuntimeError, match='injected coverage outage'):
        quality_review.run_quality_review(tmp_path, review)
    resumed = json.loads((tmp_path / 'data/editorial/latest.json').read_text())
    clock_now[0] += timedelta(hours=12)  # Cross local midnight, with archive still <24h old.
    resumed.update(cutoff=clock_now[0].isoformat(), generatedAt=clock_now[0].isoformat())
    with pytest.raises(ValueError, match='blocked publication'):
        quality_review.run_quality_review(tmp_path, resumed)
    assert len(calls) == 2
    assert 'finalAudit' not in resumed
