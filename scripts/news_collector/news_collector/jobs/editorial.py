from news_collector.pipeline.editorial import run_editorial
from news_collector.runtime import build_runtime
import argparse
import json
import os
import hashlib
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo


def prepare_editorial(repository, settings, config, args, required_urls=()):
    from news_collector.pipeline.quality_review import atomic_json
    output = settings.project_root.parent.parent / "data/editorial"
    marker = output / "publisher-draft.json"
    key = os.environ.get("NEWS_EDITORIAL_RUN_KEY")
    from news_collector.utils import canonicalize_url
    def accounts_for_sources(review):
        represented = {canonicalize_url(p["url"]) for p in review.get("packets", [])}
        represented.update(canonicalize_url(p["url"]) for p in review.get("excluded", []))
        return set(required_urls) <= represented
    can_resume = key and not args.prepare_review and not args.review_file
    if can_resume and marker.exists():
        saved = json.loads(marker.read_text())
        if saved.get("key") == key:
            print("Resuming the editorial evidence snapshot for this publisher run", flush=True)
            latest = output / "latest.json"
            if latest.exists():
                progress = json.loads(latest.read_text())
                if (progress.get("generatedAt") and progress.get("generatedAt") == saved["review"].get("generatedAt")
                        and progress.get("historyHash") == saved["review"].get("historyHash")
                        and accounts_for_sources(progress)):
                    return progress
            if accounts_for_sources(saved["review"]):
                return saved["review"]
    latest = output / "latest.json"
    if can_resume and latest.exists():
        # Preserve source-bound desk work across stage fixes. A draft without
        # approval must still run the independent audit; reuse is not permission.
        from news_collector.pipeline.editorial import POLICY_VERSION, reader_profile, source_hash, ReviewBatch, validate_decisions
        from news_collector.pipeline.publication_history import load_history, history_hash
        from news_collector.pipeline.quality_review import verify_final_audit
        try:
            approved = json.loads(latest.read_text())
            now = datetime.now(timezone.utc)
            cutoff = datetime.fromisoformat(approved["cutoff"])
            profile = reader_profile()
            date = now.astimezone(ZoneInfo(profile["timezone"])).date().isoformat()
            prompt = (settings.project_root / "config/editorial-prompt.md").read_text()
            policy = hashlib.sha256((POLICY_VERSION + prompt + json.dumps(profile, sort_keys=True)
                + os.environ.get("NEWS_EDITOR_MODEL", "default")
                + os.environ.get("NEWS_EDITOR_REASONING_EFFORT", "default")).encode()).hexdigest()
            history = load_history(settings.project_root.parent.parent, date)
            enabled = {c["name"] for c in config["collectors"] if c.get("enabled", True)}
            current = {}
            for row in repository.fetch_recent_items(limit_hours=30 * 24):
                # Repository order puts the newest record first. An older copy
                # of the same URL must not overwrite its current input hash.
                current.setdefault((row["source"], row["canonical_url"]), source_hash(row))
            selected = set(approved["selection"]["selected_ids"])
            if (accounts_for_sources(approved) and approved["policy"] == policy
                    and approved["historyHash"] == history_hash(history)
                    and cutoff.astimezone(ZoneInfo(profile["timezone"])).date().isoformat() == date
                    and timedelta(0) <= now - cutoff < timedelta(hours=6)
                    and all(p["source"] in enabled and p.get("inputHash")
                            == current.get((p["source"], p["url"])) for p in approved["packets"] if p["id"] in selected)):
                validate_decisions(ReviewBatch(decisions=list(approved["decisions"].values())), approved["packets"])
                if approved.get("finalAudit"):
                    verify_final_audit(approved, history, now)
                    print("Resuming the independently approved editorial snapshot after policy/source/history validation", flush=True)
                else:
                    print("Resuming the source-bound editorial draft; independent final audit still required", flush=True)
                atomic_json(marker, {"key": key, "review": approved})
                return approved
        except (ValueError, KeyError):
            pass  # Changed/incomplete approval requires the normal fresh desk.
    result = run_editorial(repository, settings, config, review_file=args.review_file, prepare_only=args.prepare_review)
    if can_resume:
        atomic_json(marker, {"key": key, "review": result})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-review", action="store_true")
    parser.add_argument("--review-file")
    parser.add_argument("--checklist-file")
    args = parser.parse_args()
    settings, config, repository, _ = build_runtime()
    required_urls = set()
    if not args.review_file and any(c["name"] == "coverage_research" and c.get("enabled", True) for c in config["collectors"]):
        from news_collector.pipeline.coverage_discovery import discover_coverage
        from news_collector.pipeline.coverage_intake import collect_required_sources
        from news_collector.pipeline.editorial import reader_profile
        cutoff = datetime.now(timezone.utc)
        output = settings.project_root.parent.parent / "data/editorial"
        checklist = discover_coverage(output / "checklist.json", cutoff, reader_profile(), args.checklist_file)
        required_urls = collect_required_sources(checklist, cutoff, repository, settings.user_agent)
    result = prepare_editorial(repository, settings, config, args, required_urls)
    if args.prepare_review:
        print({"request": result["request"], "pending": result["pending"], "cached": len(result["decisions"])})
        return
    from news_collector.pipeline.quality_review import run_quality_review
    audit = run_quality_review(settings.project_root.parent.parent, result, args.checklist_file)
    print({"final_audit": audit.status, "metrics": audit.metrics})
    print({"reviewed": len(result["decisions"]), "admitted": sum(d["decision"] == "admit" for d in result["decisions"].values())})


if __name__ == "__main__":
    main()
