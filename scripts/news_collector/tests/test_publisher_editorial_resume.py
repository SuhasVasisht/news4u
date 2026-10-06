from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest

from news_collector.jobs import editorial as job
from news_collector.pipeline import quality_review as quality
from news_collector.pipeline.edition_audit import StoryAuditReview, CoverageAuditReview
from test_edition_audit import fixture, NOW


def test_publisher_reuses_draft_only_for_same_run(tmp_path, monkeypatch):
    settings = SimpleNamespace(project_root=tmp_path / 'scripts/news_collector')
    args = SimpleNamespace(prepare_review=False, review_file=None)
    calls = []
    def prepare(*a, **kw):
        calls.append(1)
        return {'snapshot': len(calls)}
    monkeypatch.setattr(job, 'run_editorial', prepare)
    monkeypatch.setenv('NEWS_EDITORIAL_RUN_KEY', 'first')
    assert job.prepare_editorial(None, settings, {}, args) == {'snapshot': 1}
    assert job.prepare_editorial(None, settings, {}, args) == {'snapshot': 1}
    monkeypatch.setenv('NEWS_EDITORIAL_RUN_KEY', 'new-day-or-evidence')
    assert job.prepare_editorial(None, settings, {}, args) == {'snapshot': 2}
    monkeypatch.delenv('NEWS_EDITORIAL_RUN_KEY')
    assert job.prepare_editorial(None, settings, {}, args) == {'snapshot': 3}


def test_coverage_failure_preserves_story_checks_but_changed_evidence_invalidates_them(tmp_path, monkeypatch):
    request, envelope = fixture()
    request['candidate_index'] = []
    # Rebuild digest after adding candidate metadata.
    from news_collector.pipeline.edition_audit import build_audit_request
    request = build_audit_request(request['packets'], request['decisions'], request['selection'], request['history'], request['checklist'], NOW, [])
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(quality, 'datetime', Clock)
    monkeypatch.setattr('news_collector.pipeline.edition_audit.datetime', Clock)
    prompt = tmp_path / 'prompt.md'
    prompt.write_text('Audit all evidence')
    calls = []
    def review(payload, prompt, output, result_type, **kwargs):
        calls.append(payload['auditMode'])
        if result_type is StoryAuditReview:
            return StoryAuditReview.model_validate({'stories': envelope['review']['stories']})
        result = CoverageAuditReview.model_validate({'coverage': envelope['review']['coverage']})
        if calls.count('coverage_reconciliation') == 1:
            result.coverage[0].story_ids = []
        kwargs['validate_result'](result)
        return result
    monkeypatch.setattr(quality, 'codex_review', review)
    with pytest.raises(ValueError, match='Covered event requires'):
        quality.run_batched_audit(request, prompt, tmp_path, [])
    assert quality.run_batched_audit(request, prompt, tmp_path, []).coverage
    assert calls.count('story_claims') == 1
    changed = deepcopy(request)
    changed['packets'][0]['chunks'][0]['text'] += ' Additional evidence.'
    changed = build_audit_request(changed['packets'], changed['decisions'], changed['selection'], changed['history'], changed['checklist'], NOW, [])
    quality.run_batched_audit(changed, prompt, tmp_path, [])
    assert calls.count('story_claims') == 2


def test_publisher_resumes_repaired_draft_without_reverting_to_original(tmp_path, monkeypatch):
    import json
    settings = SimpleNamespace(project_root=tmp_path / 'scripts/news_collector')
    args = SimpleNamespace(prepare_review=False, review_file=None)
    original = {'generatedAt': NOW.isoformat(), 'historyHash': 'same-history', 'summary': 'original'}
    monkeypatch.setattr(job, 'run_editorial', lambda *a, **kw: original)
    monkeypatch.setenv('NEWS_EDITORIAL_RUN_KEY', 'same-run')
    job.prepare_editorial(None, settings, {}, args)
    latest = tmp_path / 'data/editorial/latest.json'
    repaired = {**original, 'summary': 'repaired'}
    latest.write_text(json.dumps(repaired))
    assert job.prepare_editorial(None, settings, {}, args) == repaired
    latest.write_text(json.dumps({**repaired, 'historyHash': 'different-history'}))
    assert job.prepare_editorial(None, settings, {}, args) == original
