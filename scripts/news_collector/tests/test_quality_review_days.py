"""Exercise persistent audit files across publication days, rather than isolated predicates."""
from copy import deepcopy
from datetime import datetime, timedelta
import json

import pytest

from news_collector.pipeline import quality_review
from news_collector.pipeline.edition_audit import CoverageAuditReview, StoryAuditReview
from news_collector.pipeline.editorial import EditionSelection
from news_collector.pipeline.publication_history import load_history, history_hash
from test_edition_audit import fixture, NOW
from test_quality_review import reviewed_fixture


@pytest.mark.parametrize('damaged_file,damage', [
    ('quality-review-response.json', '{"requestHash":'),
    ('quality-review-response.json', '[]'),
    ('quality-review-request.json', '{"cutoff":'),
    ('quality-review-request.json', 'null'),
])
def test_second_publication_day_recovers_from_unusable_saved_audit(tmp_path, monkeypatch, damaged_file, damage):
    clock_now = [NOW]
    clock = type('Clock', (datetime,), {'now': classmethod(lambda cls, tz=None: clock_now[0])})
    monkeypatch.setattr(quality_review, 'datetime', clock)
    monkeypatch.setattr('news_collector.pipeline.edition_audit.datetime', clock)
    original, envelope = fixture()
    current_checklist = [deepcopy(original['checklist'])]
    monkeypatch.setattr(quality_review, 'discover_coverage', lambda *_: current_checklist[0])
    calls = []
    def desk(payload, prompt, output, result_type, **kwargs):
        if result_type is EditionSelection:
            return EditionSelection(selected_ids=[item['id'] for item in payload['shortlist']], excluded=[])
        if result_type is StoryAuditReview:
            calls.append(payload)
            story = deepcopy(envelope['review']['stories'][0])
            story.update(id=payload['auditStoryIds'][0], event_key='bank-rate-day-' + payload['auditStoryIds'][0])
            return StoryAuditReview(stories=[story])
        assert result_type is CoverageAuditReview
        item = deepcopy(envelope['review']['coverage'][0])
        item['story_ids'] = payload['selection']['selected_ids']
        return CoverageAuditReview(coverage=[item])
    monkeypatch.setattr(quality_review, 'codex_review', desk)
    first = reviewed_fixture()
    first.pop('finalAudit')
    first['packets'][0]['kind'] = 'reporting'
    assert quality_review.run_quality_review(tmp_path, first).status == 'passed'
    # Publish day one's public prose into the same archive the real loader reads.
    published = tmp_path / 'data/cloudflare-published/editions/2026-09-10/edition.json'
    published.parent.mkdir(parents=True)
    published.write_text(json.dumps({'date': '2026-09-10', 'editorialReviewedAt': NOW.isoformat(),
        'stories': [{'id': 'a', 'title': first['decisions']['a']['headline'],
                     'url': first['packets'][0]['url'], 'eventKey': 'bank-rate-day-a',
                     'summary': first['decisions']['a']['summary']}]}))
    (tmp_path / 'data/editorial' / damaged_file).write_text(damage)
    clock_now[0] += timedelta(days=1)
    current_checklist[0]['checkedAt'] = clock_now[0].isoformat()
    current_checklist[0]['events'][0]['sources'][0]['publishedAt'] = clock_now[0].isoformat()
    second = deepcopy(first)
    second.pop('finalAudit')
    second.update(cutoff=clock_now[0].isoformat(), generatedAt=clock_now[0].isoformat(),
                  historyHash=history_hash(load_history(tmp_path, '2026-09-11')))
    second['packets'][0].update(id='b', url='https://example.org/new-decision', publishedAt=clock_now[0].isoformat())
    second['decisions'] = {'b': {**second['decisions']['a'], 'id': 'b'}}
    second['selection'] = {'selected_ids': ['b'], 'excluded': []}
    assert quality_review.run_quality_review(tmp_path, second).status == 'passed'
    assert [payload['auditStoryIds'] for payload in calls] == [['a'], ['b']]
    assert calls[0]['history'] == []
    assert [entry['id'] for entry in calls[1]['history']] == ['a']
    assert quality_review.verify_final_audit(second, load_history(tmp_path, '2026-09-11'), clock_now[0]).status == 'passed'


def test_damaged_latest_response_does_not_erase_same_day_archived_hold(tmp_path, monkeypatch):
    clock = type('Clock', (datetime,), {'now': classmethod(lambda cls, tz=None: NOW)})
    monkeypatch.setattr(quality_review, 'datetime', clock)
    monkeypatch.setattr('news_collector.pipeline.edition_audit.datetime', clock)
    original, envelope = fixture()
    monkeypatch.setattr(quality_review, 'discover_coverage', lambda *_: original['checklist'])
    first = reviewed_fixture()
    first.pop('finalAudit')
    first['packets'][0]['kind'] = 'reporting'
    factual_calls = []
    def desk(payload, prompt, output, result_type, **kwargs):
        if result_type is EditionSelection:
            return EditionSelection(selected_ids=['a'], excluded=[])
        if result_type is StoryAuditReview:
            factual_calls.append(payload)
            story = deepcopy(envelope['review']['stories'][0])
            story.update(verdict='hold', reason='Attribution remains unresolved in this unchanged evidence.')
            return StoryAuditReview(stories=[story])
        return CoverageAuditReview(coverage=envelope['review']['coverage'])
    monkeypatch.setattr(quality_review, 'codex_review', desk)
    with pytest.raises(ValueError, match='blocked publication'):
        quality_review.run_quality_review(tmp_path, first)
    output = tmp_path / 'data/editorial'
    (output / 'quality-review-response.json').write_text('{')
    resumed = json.loads((output / 'latest.json').read_text())
    with pytest.raises(ValueError, match='blocked publication'):
        quality_review.run_quality_review(tmp_path, resumed)
    assert len(factual_calls) == 1
    assert 'finalAudit' not in resumed
    assert json.loads((output / 'quality-audit.json').read_text())['status'] == 'blocked'
