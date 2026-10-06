from datetime import datetime, timezone
from types import SimpleNamespace

from news_collector.pipeline.editor_availability import active_quota_block, record_quota_error
from news_collector.pipeline import editorial
import pytest


def test_hard_quota_is_distinct_from_capacity_and_expires(tmp_path):
    path = tmp_path / 'quota.json'
    now = datetime(2026, 10, 5, tzinfo=timezone.utc)
    assert not record_quota_error('ERROR: Selected model is at capacity.', path, now)
    assert not path.exists()
    error = 'ERROR: You’ve hit your usage limit. Try again at Oct 9th, 2026 10:42 PM.'
    assert record_quota_error(error, path, now)
    assert active_quota_block(path, now)['reason'] == 'editor_usage_limit'
    assert active_quota_block(path, datetime(2026, 10, 11, tzinfo=timezone.utc)) is None


def test_quota_without_reset_requires_explicit_resume(tmp_path):
    path = tmp_path / 'quota.json'
    assert record_quota_error('ERROR: insufficient_quota', path)
    assert active_quota_block(path)['retryAfter'] is None


def test_repeated_editor_calls_do_not_hit_an_exhausted_account(tmp_path, monkeypatch):
    monkeypatch.setenv('NEWS_EDITOR_QUOTA_FILE', str(tmp_path / 'quota.json'))
    monkeypatch.setattr(editorial.shutil, 'which', lambda _: '/bin/codex')
    calls = []
    def run(*a, **kw):
        calls.append(1)
        return SimpleNamespace(returncode=1, stderr='ERROR: You’ve hit your usage limit.')
    monkeypatch.setattr(editorial.subprocess, 'run', run)
    prompt = tmp_path / 'prompt.md'
    prompt.write_text('Review')
    with pytest.raises(RuntimeError, match='review failed'):
        editorial.codex_review([], prompt, tmp_path)
    with pytest.raises(RuntimeError, match='usage is exhausted'):
        editorial.codex_review([], prompt, tmp_path)
    assert len(calls) == 1
