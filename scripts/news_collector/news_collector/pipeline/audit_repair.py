"""Bounded corrections and reuse of unchanged, evidence-bound factual checks."""
from copy import deepcopy
import re
from markdown_it import MarkdownIt
from pydantic import BaseModel, ConfigDict
from news_collector.pipeline.editorial import Decision, NoteSection, ReviewBatch, validate_decisions


class ProseCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    headline: str
    summary: str
    points: list[str]
    sections: list[NoteSection]
    caveats: list[str]


class ProseCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")
    corrections: list[ProseCorrection]


def apply_corrections(initial, corrections, packets):
    ids = [correction.id for correction in corrections.corrections]
    if len(ids) != len(set(ids)) or set(ids) != {packet["id"] for packet in packets}:
        raise ValueError("Corrections must account for every requested story exactly once")
    result = ReviewBatch(decisions=[Decision.model_validate({**initial[item.id], **item.model_dump()})
                                  for item in corrections.corrections])
    result = plain_review_prose(result)
    validate_decisions(result, packets)
    return result


def plain_review_prose(review):
    parser = MarkdownIt("commonmark", {"html": False})
    def plain(value):
        value = re.sub(r"\s*\[p\d+(?:\s*[,;]\s*p\d+)*\]", "", value)
        tokens = parser.parseInline(value)[0].children or []
        if any(token.type == "image" for token in tokens):
            raise ValueError("Images are not valid article prose")
        return "".join("\n" if token.type in {"softbreak", "hardbreak"} else token.content
                       if token.type in {"text", "code_inline"} else "" for token in tokens)
    for decision in review.decisions:
        decision.headline = plain(decision.headline)
        decision.summary = plain(decision.summary)
        decision.points = [plain(value) for value in decision.points]
        decision.caveats = [plain(value) for value in decision.caveats]
        for section in decision.sections:
            section.heading = plain(section.heading)
            section.body = plain(section.body)
    return review


def repairable_ids(report):
    return [story.id for story in report.review.stories
            if any(claim.verdict != "supported" for claim in story.claims)]


def prunable_optional_ids(report, checklist):
    failed = {story.id for story in report.review.stories
              if story.verdict != "pass" or any(claim.verdict != "supported" for claim in story.claims)
              or any(blocker.startswith(f"{story.id}:") for blocker in report.blockers)}
    if not failed:
        return []
    if any(not blocker.startswith("Must-cover event unresolved:")
           and not any(blocker.startswith(f"{story_id}:") for story_id in failed)
           for blocker in report.blockers):
        return []
    must_cover = {event["id"] for event in checklist["events"] if event["mustCover"]}
    protected = set().union(*(failed.intersection(item.story_ids)
                              for item in report.review.coverage
                              if item.event_id in must_cover), set())
    # Optional mapped stories may be removed; quality_review will run a fresh
    # coverage reconciliation instead of reusing the now-stale mapping.
    return sorted(failed - protected)


def reusable_story_checks(previous_request, request, report):
    # These shared inputs determine novelty, scope and evidence. Changed selection
    # or history requires a complete new review, not partial verdict reuse.
    for key in ("policy", "cutoff", "packets", "selection", "history", "checklist"):
        if previous_request.get(key) != request.get(key):
            return []
    before = {decision["id"]: decision for decision in previous_request["decisions"]}
    after = {decision["id"]: decision for decision in request["decisions"]}
    return [deepcopy(story) for story in report.review.stories
            if story.verdict == "pass" and before.get(story.id) == after.get(story.id)
            and not any(blocker.startswith(f"{story.id}:") for blocker in report.blockers)]
