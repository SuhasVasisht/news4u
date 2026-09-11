from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from news_collector.collectors.base import CollectorContext, CollectorDegraded
from news_collector.collectors.dol_claims import DOLClaimsCollector, pdf_text, release_metadata
from news_collector.collectors.rss import RSSCollector
from tests.helpers import FakeClient, FakeResponse
from tests.test_collectors import make_repository, make_settings


REPORT = """TRANSMISSION OF MATERIALS IN THIS RELEASE IS EMBARGOED UNTIL
8:30 A.M. (Eastern) Thursday, September 11, 2025
UNEMPLOYMENT INSURANCE WEEKLY CLAIMS
SEASONALLY ADJUSTED DATA
In the week ending September 6, the advance figure was 263,000.
Release Number: USDL 25-1377-NAT"""


def collector_for(tmp_path, name, cls):
    config = yaml.safe_load((Path(__file__).parents[1] / "config/sources.yaml").read_text())
    source = next(s for s in config["collectors"] if s["name"] == name)
    return cls(CollectorContext(name=name, config=source, defaults={},
                               settings=make_settings(tmp_path), repository=make_repository(tmp_path)))


def test_claims_uses_release_not_observation_or_fetch_date():
    published, number = release_metadata(REPORT)
    assert published == datetime(2025, 9, 11, 12, 30, tzinfo=timezone.utc)
    assert number == "20251377"
    winter = REPORT.replace("September 11", "January 09")
    assert release_metadata(winter)[0].hour == 13


@pytest.mark.parametrize("text", [REPORT.replace("EMBARGOED UNTIL", "Issued"),
    REPORT.replace("25-1377", "26-1377"), REPORT.replace("WEEKLY CLAIMS", "OTHER DATA")])
def test_claims_rejects_missing_or_inconsistent_identity(text):
    with pytest.raises(CollectorDegraded):
        release_metadata(text)


def test_claims_rejects_non_pdf():
    with pytest.raises(CollectorDegraded):
        pdf_text(b"<html>Access denied</html>")


def test_claims_verifies_archive_and_retains_evidence(tmp_path, monkeypatch):
    collector = collector_for(tmp_path, "dol_claims", DOLClaimsCollector)
    root = "https://www.dol.gov/sites/dolgov/files/OPA/newsreleases/"
    monkeypatch.setattr("news_collector.collectors.dol_claims.pdf_text", lambda content: content.decode())
    collector.client = FakeClient({
        collector.context.config["url"]: FakeResponse(text=REPORT),
        root + "20251377.pdf": FakeResponse(text=REPORT.replace("263,000", "264,000")),
        root + "ui-claims/20251377.pdf": FakeResponse(text=REPORT),
    })
    item, = collector.collect()
    assert item.url == root + "ui-claims/20251377.pdf"
    assert item.text == REPORT
    assert item.external_id == "dol-claims-20251377"
    assert item.raw["_edition_sector"] == "Economy"
    assert item.raw["_editorial_type"] == "announcement"


def test_claims_fails_closed_without_matching_archive(tmp_path, monkeypatch):
    collector = collector_for(tmp_path, "dol_claims", DOLClaimsCollector)
    monkeypatch.setattr("news_collector.collectors.dol_claims.pdf_text", lambda content: REPORT)
    collector.client = FakeClient({collector.context.config["url"]: FakeResponse(text=REPORT)})
    with pytest.raises(CollectorDegraded, match="No matching dated archive"):
        collector.collect()


def test_claims_does_not_publish_embargoed_release(tmp_path, monkeypatch):
    collector = collector_for(tmp_path, "dol_claims", DOLClaimsCollector)
    future = REPORT.replace("2025", "2099").replace("25-1377", "99-1377")
    monkeypatch.setattr("news_collector.collectors.dol_claims.pdf_text", lambda content: future)
    collector.client = FakeClient({collector.context.config["url"]: FakeResponse(text=future)})
    with pytest.raises(CollectorDegraded, match="still embargoed"):
        collector.collect()


def test_senator_rss_has_full_evidence_and_announcement_attribution(tmp_path):
    collector = collector_for(tmp_path, "hawley_oversight", RSSCollector)
    collector.client = FakeClient({collector.context.config["url"]: FakeResponse(text='''
      <rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>
      <title>Hawley requests documents</title><link>https://www.hawley.senate.gov/inquiry/</link>
      <pubDate>Thu, 10 Sep 2026 20:49:44 +0000</pubDate><description>Short excerpt</description>
      <content:encoded><![CDATA[<p>The senator's office says it requested documents.</p>]]></content:encoded>
      </item></channel></rss>''')})
    collector.resolve_image = lambda *args: None
    item, = collector.collect()
    assert "requested documents" in item.text
    assert item.published_at == datetime(2026, 9, 10, 20, 49, 44, tzinfo=timezone.utc)
    assert item.raw["_editorial_type"] == "announcement"
    assert item.raw["_edition_sector"] == "Deals & regulation"
