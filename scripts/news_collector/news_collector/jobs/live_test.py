from __future__ import annotations

import json

from news_collector.runtime import build_runtime


def main() -> None:
    _settings, _config, _repository, collectors = build_runtime()
    results = []
    for collector in collectors:
        result = collector.run(force=True)
        results.append(
            {
                "collector": collector.name,
                "status": result.status,
                "reason": result.reason,
                "items": len(result.items),
                "sample_title": result.items[0].title if result.items else None,
            }
        )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
