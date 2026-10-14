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


def test_corroboration_requires_independent_publishers_with_fresh_articles(monkeypatch):
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


def test_two_domains_owned_by_one_publisher_are_not_independent_corrobation(monkeypatch):
    monkeypatch.setattr(images, 'download', lambda _, url, __: (
        b'<meta property="article:published_time" content="2026-10-07T12:00:00Z">', url))
    monkeypatch.setattr(extract, 'extract_text_from_html', lambda *_: 'verified article ' * 100)
    payload = event('https://bbc.co.uk/news/article')
    payload['events'][0]['sources'].append({**payload['events'][0]['sources'][0], 'url': 'https://bbc.com/news/second'})
    with pytest.raises(ValueError, match='lacks accessible publisher-dated evidence'):
        discovery.verify_must_cover_sources(payload, NOW)


def test_all_failed_requirements_and_publisher_dates_are_reported_in_one_retry(monkeypatch):
    def download(_, url, __):
        date = '2026-10-01T12:00:00Z' if 'old' in url else '2026-10-07T12:00:00Z'
        return f'<meta property="article:published_time" content="{date}">'.encode(), url
    monkeypatch.setattr(images, 'download', download)
    monkeypatch.setattr(extract, 'extract_text_from_html', lambda *_: 'article text ' * 100)
    payload = event('https://publisher.org/old')
    payload['events'] += [{**event('https://publisher.org/second')['events'][0], 'id': 'second-event'},
                          {**event()['events'][0], 'id': 'verified-primary'}]
    with pytest.raises(discovery.CoverageVerificationError) as error:
        discovery.verify_must_cover_sources(payload, NOW)
    message = str(error.value)
    assert 'outbreak-update' in message and 'second-event' in message
    assert '2026-10-01T12:00:00+00:00' in message and 'articleWords' in message
    assert error.value.verified_ids == {'verified-primary'}
    assert all(item['mustCover'] for item in payload['events'])


@pytest.mark.parametrize('change', ['new_event', 'new_mandatory', 'waive_verified'])
def test_source_repair_cannot_replace_events_or_waive_verified_requirements(tmp_path, monkeypatch, change):
    from news_collector.pipeline import editorial
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(discovery, 'datetime', Clock)
    payload = {'checkedAt': NOW.isoformat(), 'method': 'independent_web_research', 'researcher': 'Independent desk',
               'scope': ['Health'], 'queries': ['October 7 outbreak update'], 'events': []}
    for id, mandatory in [('verified', True), ('blocked', True), ('optional', False)]:
        item = deepcopy(event()['events'][0]);item.update(id=id, mustCover=mandatory,
            event='Important new outbreak development', sector='Science & health')
        item['sources'][0]['finding'] = 'Primary report describes the new outbreak development.'
        payload['events'].append(item)
    def verify(*_):
        raise discovery.CoverageVerificationError(['blocked lacks accessible publisher-dated evidence'], ['verified'])
    monkeypatch.setattr(discovery, 'verify_must_cover_sources', verify)
    def research(*args, **kwargs):
        result = discovery.IndependentChecklist.model_validate(payload)
        with pytest.raises(discovery.CoverageVerificationError):
            kwargs['validate_result'](result)
        repaired = deepcopy(payload)
        if change == 'new_event': repaired['events'][1]['id'] = 'replacement-event'
        if change == 'new_mandatory': repaired['events'][2]['mustCover'] = True
        if change == 'waive_verified': repaired['events'][0]['mustCover'] = False
        kwargs['validate_result'](discovery.IndependentChecklist.model_validate(repaired))
    monkeypatch.setattr(editorial, 'codex_review', research)
    original = tmp_path / 'checklist.json';original.write_text('{"prior": true}')
    with pytest.raises(ValueError, match='Research repair'):
        discovery.discover_coverage(original, NOW, {})
    assert original.read_text() == '{"prior": true}'


@pytest.mark.parametrize('host', ['gov.uk', 'www.gov.uk', 'europa.eu', 'www.europa.eu', 'agency.gov',
                                  'who.int', 'ecb.europa.eu', 'pib.gov.in', 'agency.gov.au',
                                  'agency.gc.ca', 'agency.gouv.fr', 'agency.go.jp', 'agency.govt.nz',
                                  'gov.in', 'gouv.fr', 'govt.nz', 'agency.gov.cn', 'agency.gob.mx'])
def test_authoritative_root_domains_pass_both_discovery_and_final_audit(monkeypatch, host):
    from news_collector.pipeline.edition_audit import DiscoveryEvent, _must_cover
    monkeypatch.setattr(images, 'download', lambda _, url, __: (
        b'<meta property="article:published_time" content="2026-10-07T12:00:00Z">', url))
    monkeypatch.setattr(extract, 'extract_text_from_html', lambda *_: 'primary report ' * 100)
    payload = event(f'https://{host}/news/report')
    discovery.verify_must_cover_sources(payload, NOW)
    item = {**payload['events'][0], 'event': 'Important primary government announcement', 'sector': 'Policy'}
    item['sources'][0]['finding'] = 'Direct primary evidence confirms the new development.'
    assert _must_cover(DiscoveryEvent.model_validate(item)) is True


@pytest.mark.parametrize('host', ['gov.uk.example.org', 'fakegov.uk', 'europa.eu.example.org', 'fake-europa.eu'])
def test_lookalike_domains_do_not_gain_primary_source_authority(host):
    from news_collector.pipeline.publishers import authoritative_host
    assert authoritative_host(host) is False


@pytest.mark.parametrize('host', ['imf.org', 'www.imf.org', 'mediacenter.imf.org',
                                  'worldbank.org', 'documents.worldbank.org', 'un.org', 'news.un.org', 'oecd.org'])
def test_public_institution_domains_have_one_identity_and_pass_both_gates(monkeypatch, host):
    from news_collector.pipeline.edition_audit import DiscoveryEvent, _must_cover
    from news_collector.pipeline.publishers import publisher
    monkeypatch.setattr(images, 'download', lambda _, url, __: (
        b'<meta property="article:published_time" content="2026-10-07T12:00:00Z">', url))
    monkeypatch.setattr(extract, 'extract_text_from_html', lambda *_: 'primary report ' * 100)
    payload = event(f'https://{host}/report')
    discovery.verify_must_cover_sources(payload, NOW)
    item = {**payload['events'][0], 'event': 'Public institution report', 'sector': 'Economy'}
    item['sources'][0]['finding'] = 'Direct publisher evidence confirms a new report.'
    assert _must_cover(DiscoveryEvent.model_validate(item))
    root = host.removeprefix('www.').split('.')[-2:]
    assert publisher(f'https://{host}/report') == publisher(f'https://{".".join(root)}/report')


@pytest.mark.parametrize('host', ['imf.org.example.com', 'fakeimf.org', 'worldbank.org.fake.org', 'un.org.evil.com', 'unrelated.org'])
def test_org_suffix_and_lookalikes_do_not_establish_public_authority(host):
    from news_collector.pipeline.publishers import authoritative_host
    assert not authoritative_host(host)


def test_every_authority_policy_component_invalidates_verification_cache(monkeypatch):
    from news_collector.pipeline import publishers
    original = publishers.authority_policy_fingerprint()
    monkeypatch.setattr(publishers, 'PUBLIC_ROOTS', publishers.PUBLIC_ROOTS | {'new-root.example'})
    assert publishers.authority_policy_fingerprint() != original


def test_publisher_identity_alias_changes_invalidate_verification_cache(monkeypatch):
    from news_collector.pipeline import publishers
    original = publishers.authority_policy_fingerprint()
    monkeypatch.setattr(publishers, 'PUBLISHER_NAMES', {**publishers.PUBLISHER_NAMES, 'alias.example': 'BBC'})
    assert publishers.authority_policy_fingerprint() != original


def test_verified_source_contract_keeps_final_url_actual_date_and_removes_failed_companion(monkeypatch):
    def download(_, url, __):
        if 'apnews' in url:
            raise ValueError('403')
        return b'<meta property="article:published_time" content="2026-10-07T12:34:56Z">', 'https://mediacenter.imf.org/report'
    monkeypatch.setattr(images, 'download', download)
    monkeypatch.setattr(extract, 'extract_text_from_html', lambda *_: 'primary report ' * 100)
    payload = event('https://imf.org/link', '2026-10-07T00:00:00Z')
    payload['events'][0]['sources'].append({'url': 'https://apnews.com/blocked', 'publishedAt': '2026-10-07T00:00:00Z'})
    discovery.verify_must_cover_sources(payload, NOW)
    assert payload['events'][0]['sources'] == [{'url': 'https://mediacenter.imf.org/report', 'publishedAt': '2026-10-07T12:34:56+00:00'}]
    assert payload['events'][0]['mustCover'] is True


def test_redirect_aliases_cannot_supply_independent_evidence(monkeypatch):
    monkeypatch.setattr(images, 'download', lambda *_: (
        b'<meta property="article:published_time" content="2026-10-07T12:00:00Z">', 'https://bbc.com/news/report'))
    monkeypatch.setattr(extract, 'extract_text_from_html', lambda *_: 'publisher report ' * 100)
    payload = event('https://alias-one.org/report')
    payload['events'][0]['sources'].append({'url': 'https://alias-two.org/report', 'publishedAt': '2026-10-07T12:00:00Z'})
    with pytest.raises(discovery.CoverageVerificationError):
        discovery.verify_must_cover_sources(payload, NOW)


def test_same_pipeline_repair_reuses_bound_verified_snapshot_but_tampering_requires_reverification(tmp_path, monkeypatch):
    from news_collector.pipeline import editorial
    import json
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return NOW
    monkeypatch.setattr(discovery, 'datetime', Clock)
    payload = {'checkedAt': NOW.isoformat(), 'method': 'independent_web_research', 'researcher': 'Independent desk',
               'scope': ['Economy'], 'queries': ['IMF new report'],
               'events': [{**event('https://mediacenter.imf.org/report')['events'][0],
                          'event': 'Major IMF report', 'sector': 'Economy'}]}
    payload['events'][0]['sources'][0]['finding'] = 'Publisher evidence confirms a new economic report.'
    calls = []
    def download(_, url, __):
        calls.append(url)
        return b'<meta property="article:published_time" content="2026-10-07T12:00:00Z">', url
    monkeypatch.setattr(images, 'download', download)
    monkeypatch.setattr(extract, 'extract_text_from_html', lambda *_: 'publisher report ' * 100)
    def research(*args, **kwargs):
        result = discovery.IndependentChecklist.model_validate(payload)
        kwargs['validate_result'](result)
        return result
    monkeypatch.setattr(editorial, 'codex_review', research)
    target = tmp_path / 'checklist.json'
    verified = discovery.discover_coverage(target, NOW, {})
    assert len(calls) == 1
    monkeypatch.setattr(images, 'download', lambda *_: (_ for _ in ()).throw(ValueError('temporary outage')))
    assert discovery.discover_coverage(target, NOW, {}, checklist_file=target) == verified
    changed = json.loads(target.read_text())
    changed['events'][0]['sources'][0]['url'] = 'https://imf.org/unverified-new-report'
    target.write_text(json.dumps(changed))
    with pytest.raises(discovery.CoverageVerificationError):
        discovery.discover_coverage(target, NOW, {}, checklist_file=target)


@pytest.mark.parametrize('companion_date', ['2026-10-01T12:00:00Z', '2026-10-07T12:00:00Z'])
def test_old_independent_background_cannot_corroborate_a_new_mandatory_development(monkeypatch, companion_date):
    def download(_, url, __):
        date = companion_date if 'independent.org' in url else '2026-10-07T12:00:00Z'
        return f'<meta property="article:published_time" content="{date}">'.encode(), url
    monkeypatch.setattr(images, 'download', download)
    monkeypatch.setattr(extract, 'extract_text_from_html', lambda *_: 'verified publisher article ' * 100)
    payload = event('https://publisher.org/new-development')
    payload['events'][0]['sources'].append({'url': 'https://independent.org/background', 'publishedAt': companion_date})
    if companion_date.startswith('2026-10-01'):
        with pytest.raises(discovery.CoverageVerificationError, match='new development'):
            discovery.verify_must_cover_sources(payload, NOW)
        assert payload['events'][0]['mustCover'] is True
    else:
        assert discovery.verify_must_cover_sources(payload, NOW) == {'outbreak-update'}


def test_older_verification_algorithm_proof_requires_fresh_source_verification(tmp_path, monkeypatch):
    import hashlib
    import json
    from news_collector.pipeline import editorial
    clock = type('Clock', (datetime,), {'now': classmethod(lambda cls, tz=None: NOW)})
    monkeypatch.setattr(discovery, 'datetime', clock)
    payload = {'checkedAt': NOW.isoformat(), 'method': 'independent_web_research', 'researcher': 'Independent desk',
               'scope': ['Economy'], 'queries': ['new report'],
               'events': [{**event()['events'][0], 'event': 'Major primary institution report', 'sector': 'Economy'}]}
    payload['events'][0]['sources'][0]['finding'] = 'Publisher evidence confirms a new economic report.'
    monkeypatch.setattr(images, 'download', lambda _, url, __: (
        b'<meta property="article:published_time" content="2026-10-07T12:00:00Z">', url))
    monkeypatch.setattr(extract, 'extract_text_from_html', lambda *_: 'publisher report ' * 100)
    monkeypatch.setattr(editorial, 'codex_review', lambda *_args, **_kwargs: discovery.IndependentChecklist.model_validate(payload))
    target = tmp_path / 'checklist.json'
    discovery.discover_coverage(target, NOW, {})
    context_path = target.with_suffix('.context.json')
    context = json.loads(context_path.read_text())
    context['sourceVerificationVersion'] = 3
    context_path.write_text(json.dumps(context))
    proof_path = target.with_suffix('.verified.json')
    proof = json.loads(proof_path.read_text())
    proof['contextHash'] = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
    proof_path.write_text(json.dumps(proof))
    monkeypatch.setattr(images, 'download', lambda *_: (_ for _ in ()).throw(ValueError('source unavailable')))
    with pytest.raises(discovery.CoverageVerificationError):
        discovery.discover_coverage(target, NOW, {}, checklist_file=target)
