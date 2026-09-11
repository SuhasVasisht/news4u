from news_collector.jobs.export_edition import assemble_reviewed
from test_editorial import NOW, row, packet, decision


def test_audited_event_selection_is_not_merged_by_title_similarity():
    titles = ["Senate opens inquiry into AI incident", "Senate closes inquiry into AI incident"]
    packets = [{**packet(), "id": str(i), "url": f"https://example.com/{i}", "title": title}
               for i, title in enumerate(titles)]
    review = {"generatedAt": NOW.isoformat(), "packets": packets,
              "decisions": {p["id"]: decision(id=p["id"], headline=p["title"]).model_dump() for p in packets},
              "selection": {"selected_ids": ["0", "1"], "excluded": []}, "excluded": [], "policy": "test"}
    rows = [row(canonical_url=p["url"], title=p["title"]) for p in packets]
    snapshot, _ = assemble_reviewed(rows, review, NOW, "America/Los_Angeles", audited_selection=True)
    assert [s["id"] for s in snapshot["stories"]] == ["0", "1"]
