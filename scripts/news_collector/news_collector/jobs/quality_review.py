import argparse
import json
from news_collector.pipeline.quality_review import run_quality_review
from news_collector.runtime import build_runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checklist-file")
    parser.add_argument("--audit-file")
    args = parser.parse_args()
    settings, _, _, _ = build_runtime()
    root = settings.project_root.parent.parent
    review = json.loads((root / "data/editorial/latest.json").read_text())
    result = run_quality_review(root, review, args.checklist_file, args.audit_file)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
