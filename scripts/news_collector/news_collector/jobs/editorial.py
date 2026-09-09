from news_collector.pipeline.editorial import run_editorial
from news_collector.runtime import build_runtime
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-review", action="store_true")
    parser.add_argument("--review-file")
    args = parser.parse_args()
    settings, config, repository, _ = build_runtime()
    result = run_editorial(repository, settings, config, review_file=args.review_file, prepare_only=args.prepare_review)
    if args.prepare_review:
        print({"request": result["request"], "pending": result["pending"], "cached": len(result["decisions"])})
        return
    print({"reviewed": len(result["decisions"]), "admitted": sum(d["decision"] == "admit" for d in result["decisions"].values())})


if __name__ == "__main__":
    main()
