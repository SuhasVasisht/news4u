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
    assert quality.run_batched_audit(request, prompt, tmp_path, []).coverage
    assert calls.count('coverage_reconciliation') == 2  # one invalid, one cached valid
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


@pytest.mark.parametrize('changed', [None, 'source', 'policy', 'history', 'audit', 'expired', 'unselected-source'])
def test_approved_snapshot_survives_other_stage_fixes_only_when_all_bindings_hold(tmp_path, monkeypatch, changed):
    import hashlib
    import json
    from datetime import timedelta
    from test_editorial import packet, decision, row
    from news_collector.pipeline import editorial
    from news_collector.pipeline import publication_history
    settings = SimpleNamespace(project_root=tmp_path / 'scripts/news_collector')
    prompt = settings.project_root / 'config/editorial-prompt.md'
    prompt.parent.mkdir(parents=True)
    prompt.write_text('Policy')
    profile = editorial.reader_profile()
    policy = hashlib.sha256((editorial.POLICY_VERSION + 'Policy' + json.dumps(profile, sort_keys=True)
        + 'default' + 'default').encode()).hexdigest()
    monkeypatch.delenv('NEWS_EDITOR_MODEL', raising=False)
    monkeypatch.delenv('NEWS_EDITOR_REASONING_EFFORT', raising=False)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(job, 'datetime', Clock)
    monkeypatch.setenv('NEWS_EDITORIAL_RUN_KEY', 'new-code-run')
    source = row()
    p = {**packet(), 'inputHash': editorial.source_hash(source)}
    approved = dict(policy=policy, cutoff=NOW.isoformat(), generatedAt=NOW.isoformat(),
                    historyHash=publication_history.history_hash([]), packets=[p],
                    decisions={'one': decision().model_dump()}, selection={'selected_ids': ['one']}, finalAudit={'approved': True})
    if changed == 'policy': approved['policy'] = 'old-policy'
    if changed == 'history': approved['historyHash'] = 'different-history'
    if changed == 'expired': approved['cutoff'] = (NOW - timedelta(hours=7)).isoformat()
    if changed == 'source': source['title'] = 'Changed report'
    latest = tmp_path / 'data/editorial/latest.json'
    latest.parent.mkdir(parents=True)
    latest.write_text(json.dumps(approved))
    rows = [source]
    if changed == 'unselected-source':
        old = row(id=2, canonical_url='https://example.com/other', title='Older optional candidate')
        approved['packets'].append({**packet(), 'id': 'two', 'url': old['canonical_url'], 'inputHash': editorial.source_hash(old)})
        approved['decisions']['two'] = decision(id='two', decision='hold').model_dump()
        rows.append({**old, 'title': 'Changed optional candidate'})
        latest.write_text(json.dumps(approved))
    # A duplicate historical record must not displace the newest selected source.
    rows.append({**source, 'title': 'Old historical version'})
    repository = SimpleNamespace(fetch_recent_items=lambda **kw: rows)
    monkeypatch.setattr(publication_history, 'load_history', lambda *a: [])
    verified = []
    def verify(review, history, now):
        verified.append(review)
        if changed == 'audit': raise ValueError('Blocked audit')
    monkeypatch.setattr(quality, 'verify_final_audit', verify)
    monkeypatch.setattr(job, 'run_editorial', lambda *a, **kw: {'fresh': True})
    result = job.prepare_editorial(repository, settings, {'collectors': [{'name': p['source']}]},
                                   SimpleNamespace(prepare_review=False, review_file=None))
    assert result == (approved if changed in (None, 'unselected-source') else {'fresh': True})
    assert bool(verified) == (changed in (None, 'audit', 'unselected-source'))
