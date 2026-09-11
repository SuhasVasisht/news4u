from datetime import datetime, timezone

import pytest

from news_collector.jobs.export_edition import export_date


NOW = datetime(2026, 9, 11, 7, 5, tzinfo=timezone.utc)
ZONE = "America/Los_Angeles"
REVIEW = {"cutoff": "2026-09-11T05:48:20+00:00"}


def test_late_revision_is_explicit_and_retains_original_date():
    assert export_date(REVIEW, NOW, ZONE) == "2026-09-11"
    assert export_date(REVIEW, NOW, ZONE, "2026-09-10") == "2026-09-10"


@pytest.mark.parametrize("date", ["2026-09-11", "2026-09-09", "2026-09-12", "invalid"])
def test_late_revision_cannot_relabel_review(date):
    with pytest.raises(ValueError):
        export_date(REVIEW, NOW, ZONE, date)


def test_explicit_revision_cannot_revive_stale_review():
    with pytest.raises(ValueError):
        export_date({"cutoff": "2026-09-10T01:00:00+00:00"}, NOW, ZONE, "2026-09-09")
