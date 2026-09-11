import pytest

from news_collector.pipeline.editorial import ReviewBatch, EditionSelection
from news_collector.pipeline.edition_audit import AuditReview, IndependentChecklist
from news_collector.pipeline.edition_audit import DiscoverySource
from news_collector.pipeline.structured_output import review_schema


@pytest.mark.parametrize("model", [ReviewBatch, EditionSelection, AuditReview, IndependentChecklist])
def test_review_objects_require_every_property_without_defaults(model):
    def check(node):
        if isinstance(node, dict):
            assert "default" not in node
            if "properties" in node:
                assert node["required"] == list(node["properties"])
                assert node["additionalProperties"] is False
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)
    check(review_schema(model))


def test_optional_sector_stays_nullable_and_model_schema_is_unchanged():
    original = ReviewBatch.model_json_schema()
    schema = review_schema(ReviewBatch)
    sector = schema["$defs"]["Decision"]["properties"]["sector"]
    assert {"type": "null"} in sector["anyOf"]
    assert ReviewBatch.model_json_schema() == original


def test_url_format_is_api_compatible_without_weakening_local_validation():
    original = DiscoverySource.model_json_schema()
    schema = review_schema(DiscoverySource)
    assert "format" not in schema["properties"]["url"]
    assert schema["properties"]["publishedAt"]["format"] == "date-time"
    assert DiscoverySource.model_json_schema() == original
    with pytest.raises(ValueError):
        DiscoverySource(url="not a URL", publishedAt="2026-09-10T09:00:00Z",
                        finding="An attributed official announcement.")
