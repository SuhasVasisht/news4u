from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import re
from zoneinfo import ZoneInfo

from pypdf import PdfReader

from news_collector.collectors.base import BaseCollector, CollectorDegraded
from news_collector.models import RawItem


def pdf_text(content: bytes) -> str:
    if not content.startswith(b"%PDF-") or len(content) > 10_000_000:
        raise CollectorDegraded("Claims endpoint did not return a bounded PDF document")
    reader = PdfReader(BytesIO(content))
    if len(reader.pages) > 30:
        raise CollectorDegraded("Unexpected claims report length")
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def release_metadata(text: str) -> tuple[datetime, str]:
    flat = " ".join(text.split())
    date = re.search(
        r"EMBARGOED UNTIL\s+8:30 A\.M\.\s+\(Eastern\)\s+[A-Za-z]+,\s+"
        r"([A-Za-z]+ \d{1,2}, 20\d{2})", flat,
    )
    number = re.search(r"Release Number:\s*USDL\s+(\d{2})-(\d{4})-NAT\b", flat)
    if not date or not number or "UNEMPLOYMENT INSURANCE WEEKLY CLAIMS" not in flat:
        raise CollectorDegraded("Claims report release date, number, or heading is missing")
    published = datetime.strptime(date.group(1), "%B %d, %Y").replace(
        hour=8, minute=30, tzinfo=ZoneInfo("America/New_York")
    ).astimezone(timezone.utc)
    if published.strftime("%y") != number.group(1):
        raise CollectorDegraded("Claims release year does not match its document number")
    return published, f"20{number.group(1)}{number.group(2)}"


class DOLClaimsCollector(BaseCollector):
    source_type = "scrape"

    def __init__(self, context):
        super().__init__(context)
        self.client.headers["Accept"] = "application/pdf"

    def collect(self) -> list[RawItem]:
        response = self.client.get(self.context.config["url"])
        response.raise_for_status()
        text = pdf_text(response.content)
        published, number = release_metadata(text)
        if published > datetime.now(timezone.utc):
            raise CollectorDegraded("Claims report is still embargoed")

        # The latest PDF changes weekly. Publish only a verified immutable release URL.
        archive_url = None
        for directory in ("", "ui-claims/"):
            url = f"https://www.dol.gov/sites/dolgov/files/OPA/newsreleases/{directory}{number}.pdf"
            try:
                archived = self.client.get(url)
                archived.raise_for_status()
                archived_text = pdf_text(archived.content)
                if " ".join(archived_text.split()) == " ".join(text.split()):
                    archive_url = url
                    break
            except Exception:
                continue
        if not archive_url:
            raise CollectorDegraded("No matching dated archive for latest claims PDF; retry after DOL publishes it")

        body = text[text.index("SEASONALLY ADJUSTED DATA"):]
        return [RawItem(
            source=self.name, source_type=self.source_type, category=self.category,
            external_id=f"dol-claims-{number}",
            title=f"US Department of Labor: weekly unemployment claims, {published:%B %d, %Y}",
            url=archive_url, published_at=published, author="US Department of Labor",
            text=text, summary=body.split("\n\n", 1)[0][:1500],
            raw={"_editorial_type": "announcement", "_edition_sector": "Economy",
                 "release_number": number, "document_sha256": sha256(response.content).hexdigest(),
                 "latest_url": self.context.config["url"]},
        )]
