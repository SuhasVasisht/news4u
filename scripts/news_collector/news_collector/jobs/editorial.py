from news_collector.pipeline.editorial import run_editorial
from news_collector.runtime import build_runtime
import argparse
import json
import os


def prepare_editorial(repository, settings, config, args):
    from news_collector.pipeline.quality_review import atomic_json
    output = settings.project_root.parent.parent / "data/editorial"
    marker = output / "publisher-draft.json"
    key = os.environ.get("NEWS_EDITORIAL_RUN_KEY")
    can_resume = key and not args.prepare_review and not args.review_file
    if can_resume and marker.exists():
        saved = json.loads(marker.read_text())
        if saved.get("key") == key:
            print("Resuming the editorial evidence snapshot for this publisher run", flush=True)
            latest = output / "latest.json"
            if latest.exists():
                progress = json.loads(latest.read_text())
                if (progress.get("generatedAt") == saved["review"].get("generatedAt")
                        and progress.get("historyHash") == saved["review"].get("historyHash")):
                    return progress
            return saved["review"]
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
    result = prepare_editorial(repository, settings, config, args)
    if args.prepare_review:
        print({"request": result["request"], "pending": result["pending"], "cached": len(result["decisions"])})
        return
    from news_collector.pipeline.quality_review import run_quality_review
    audit = run_quality_review(settings.project_root.parent.parent, result, args.checklist_file)
    print({"final_audit": audit.status, "metrics": audit.metrics})
    print({"reviewed": len(result["decisions"]), "admitted": sum(d["decision"] == "admit" for d in result["decisions"].values())})


if __name__ == "__main__":
    main()
