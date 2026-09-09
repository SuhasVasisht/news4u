import json
from datetime import datetime, timedelta, timezone

import pytest

from news_collector.collectors.alphasignal import AlphaSignalCollector
from news_collector.collectors.base import CollectorContext, CollectorDegraded
from news_collector.collectors.tldr import TLDRCollector
from news_collector.pipeline.dedupe import cluster_items
from news_collector.pipeline.editorial import exclusion
from news_collector.pipeline.normalize import normalize_item
from tests.helpers import FakeClient, FakeResponse
from tests.test_collectors import make_settings, make_repository


def collector(cls, tmp_path, name, **config):
    instance = cls(CollectorContext(name=name, config={'category': 'tech', **config},
        defaults={}, settings=make_settings(tmp_path), repository=make_repository(tmp_path)))
    instance.resolve_text = lambda url, summary: summary
    instance.resolve_image = lambda *args: None
    return instance


def test_tldr_daily_issue_excludes_ads_jobs_and_keeps_original_links(tmp_path):
    c = collector(TLDRCollector, tmp_path, 'tldr_ai', url='https://tldr.tech/api/latest/ai',
                  newsletter='ai', daily_issue=True)
    html = '<h1>TLDR AI 2026-09-08</h1>'
    for title, url in [('New model (3 minute read)', 'https://example.com/model?utm_source=tldr'),
                       ('Try this (Sponsor)', 'https://ad.example/'),
                       ('Product Manager', 'https://jobs.ashbyhq.com/tldr/job')]:
        html += f'<article><a href="{url}"><h3>{title}</h3></a><div class="newsletter-html">A summary.</div></article>'
    c.client = FakeClient({c.context.config['url']: FakeResponse(text=html)})
    items = c.collect()
    assert len(items) == 1
    assert items[0].title == 'New model'
    assert normalize_item(items[0]).canonical_url == 'https://example.com/model'
    assert items[0].published_at.date().isoformat() == '2026-09-08'
    assert items[0].raw['_newsletter_url'] == 'https://tldr.tech/ai/2026-09-08'
    c.client = FakeClient({c.context.config['url']: FakeResponse(text='<h1>Subscribe</h1>')})
    with pytest.raises(CollectorDegraded):
        c.collect()


def test_alphasignal_partial_pages_metadata_and_cross_source_dedupe(tmp_path):
    c = collector(AlphaSignalCollector, tmp_path, 'alphasignal', url='https://alphasignal.ai/')
    metadata = {'@type': 'NewsArticle', 'headline': 'New reasoning model released',
                'datePublished': '2026-09-08T10:00:00Z', 'description': 'A new model.',
                'mentions': [{'name': 'Reasoning'}], 'image': ['https://example.com/photo.jpg']}
    c.client = FakeClient({
        'https://alphasignal.ai/': FakeResponse(text='<a href="/news/model">Model</a><a href="/news/model">Again</a><a href="/news/broken">Broken</a><a href="https://other.example/news/a">Other</a>'),
        'https://alphasignal.ai/news/model': FakeResponse(text=f'<script type="application/ld+json">{json.dumps(metadata)}</script>'),
        'https://alphasignal.ai/news/broken': FakeResponse(status_code=503),
    })
    result = c.run(force=True)
    assert result.status == 'partial'
    assert len(result.items) == 1
    item = result.items[0]
    assert item.tags == ['Reasoning']
    assert item.published_at.isoformat() == '2026-09-08T10:00:00+00:00'
    assert c._parse_article('<h1>Undated</h1>', item.url) is None
    row = dict(id=1, title=item.title, canonical_url=item.url, source='alphasignal',
               category='tech', importance_score=.7, summary=item.summary,
               published_at=item.published_at.isoformat(), entities_json='[]', symbols_json='[]')
    other = dict(row, id=2, source='tldr_ai', canonical_url='https://example.com/model')
    assert len(cluster_items([row, other])) == 1
    unrelated = dict(other, id=3, title='A different company releases a video editor')
    assert len(cluster_items([row, unrelated])) == 2


def test_bytebytego_uses_longform_window():
    now = datetime.now(timezone.utc)
    row = {'source': 'bytebytego', 'canonical_url': 'https://blog.bytebytego.com/p/example',
           'title': 'How payment systems work', 'published_at': (now - timedelta(days=8)).isoformat()}
    assert exclusion(row, now) is None
