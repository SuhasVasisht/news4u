from datetime import datetime, timezone
from pathlib import Path

import yaml

from news_collector.collectors.base import CollectorContext
from news_collector.collectors.rss import RSSCollector
from tests.helpers import FakeClient, FakeResponse
from tests.test_collectors import make_repository, make_settings


def test_ecb_uses_standard_rss_dates_and_announcement_attribution(tmp_path):
    config = yaml.safe_load((Path(__file__).parents[1] / "config/sources.yaml").read_text())
    source = next(s for s in config["collectors"] if s["name"] == "ecb_press")
    collector = RSSCollector(CollectorContext(name="ecb_press", config=source, defaults={},
                             settings=make_settings(tmp_path), repository=make_repository(tmp_path)))
    collector.client = FakeClient({source["url"]: FakeResponse(text='''<rss><channel><item>
      <title>Monetary policy decisions</title>
      <link>https://www.ecb.europa.eu/press/pr/date/2026/decision.html</link>
      <pubDate>Thu, 10 Sep 2026 14:15:00 +0200</pubDate>
      <description>Official decision</description></item></channel></rss>''')})
    collector.resolve_text = lambda url, summary: summary
    collector.resolve_image = lambda url, image: None
    item, = collector.collect()
    assert item.published_at == datetime(2026, 9, 10, 12, 15, tzinfo=timezone.utc)
    assert item.raw["_editorial_type"] == "announcement"
    assert item.raw["_edition_sector"] == "Economy"
    assert item.source == "ecb_press"
    assert source["editorial_limit"] == 4
