from datetime import datetime, timezone
from copy import deepcopy
import pytest
from news_collector.pipeline import coverage_discovery as discovery
from news_collector.pipeline import images, extract

NOW = datetime(2026, 10, 7, 14, tzinfo=timezone.utc)


def event(url='https://www.who.int/news/direct-article', date='2026-10-07T12:00:00Z'):
    return {'events': [{'id': 'outbreak-update', 'mustCover': True, 'sources': [{'url': url, 'publishedAt': date}]}]}


@pytest.mark.parametrize('problem', ['unavailable', 'no_date', 'background', 'wrong_date', 'short_page'])
def test_unverified_research_cannot_create_a_blocking_requirement(monkeypatch, problem):
    def download(*_):
        if problem == 'unavailable':
            raise ValueError('404')
        date = '2026-10-01T12:00:00Z' if problem in {'background', 'wrong_date'} else '2026-10-07T12:00:00Z'
        return (('' if problem == 'no_date' else f'<meta property="article:published_time" content="{date}">').encode(),
                'https://www.who.int/news/direct-article')
    monkeypatch.setattr(images, 'download', download)
    monkeypatch.setattr(extract, 'extract_text_from_html', lambda *_: 'verified article ' * (5 if problem == 'short_page' else 100))
    payload = event(date='2026-10-01T12:00:00Z') if problem == 'background' else event()
    with pytest.raises(ValueError, match='lacks accessible publisher-dated evidence'):
        discovery.verify_must_cover_sources(payload, NOW)
    assert payload['events'][0]['mustCover'] is True  # Never silently waive a requirement.


def test_verified_primary_source_passes_and_network_results_are_cached(monkeypatch):
    calls = []
    def download(*args):
        calls.append(args[1])
        return b'<meta property="article:published_time" content="2026-10-07T12:00:00Z">', args[1]
    monkeypatch.setattr(images, 'download', download)
    monkeypatch.setattr(extract, 'extract_text_from_html', lambda *_: 'verified article ' * 100)
    cache = {}
    discovery.verify_must_cover_sources(event(), NOW, cache)
    discovery.verify_must_cover_sources(event(), NOW, cache)
    assert len(calls) == 1


def test_corrobation_requires_independent_domains_and_one_fresh_article(monkeypatch):
    monkeypatch.setattr(images, 'download', lambda _, url, __: (
        b'<meta property="article:published_time" content="2026-10-07T12:00:00Z">', url))
    monkeypatch.setattr(extract, 'extract_text_from_html', lambda *_: 'verified article ' * 100)
    payload = event('https://publisher.org/article')
    payload['events'][0]['sources'].append({**payload['events'][0]['sources'][0], 'url': 'https://www.publisher.org/second'})
    with pytest.raises(ValueError):
        discovery.verify_must_cover_sources(payload, NOW)
    payload['events'][0]['sources'][1]['url'] = 'https://independent.org/article'
    discovery.verify_must_cover_sources(payload, NOW)


def test_automatic_discovery_enforces_verification_before_replacing_a_checklist(tmp_path, monkeypatch):
    from news_collector.pipeline import editorial
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(discovery, 'datetime', Clock)
    payload = {'checkedAt': NOW.isoformat(), 'method': 'independent_web_research', 'researcher': 'Independent desk',
               'scope': ['Health'], 'queries': ['October 7 outbreak update'],
               'events': [{**event()['events'][0], 'event': 'Important new outbreak development', 'sector': 'Science & health'}]}
    payload['events'][0]['sources'][0]['finding'] = 'Primary report describes the new outbreak development.'
    original = tmp_path / 'checklist.json'
    original.write_text('{"prior": true}')
    def unavailable(*_):
        raise ValueError('unavailable publisher article')
    monkeypatch.setattr(images, 'download', unavailable)
    def research(*args, **kwargs):
        result = discovery.IndependentChecklist.model_validate(payload)
        kwargs['validate_result'](result)
        return result
    monkeypatch.setattr(editorial, 'codex_review', research)
    with pytest.raises(ValueError, match='lacks accessible publisher-dated evidence'):
        discovery.discover_coverage(original, NOW, {})
    assert original.read_text() == '{"prior": true}'
    payload['events'][0]['mustCover'] = False  # A researcher can correct an unverified requirement.
    result = discovery.discover_coverage(original, NOW, {})
    assert result['events'][0]['mustCover'] is False
