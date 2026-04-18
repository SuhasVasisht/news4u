# News Collector

Local daily news ingestion pipeline with structured-first collectors, normalization, dedupe, ranking, SQLite storage, and Markdown/JSON digests.

## Quick start

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
playwright install chromium
cp .env.example .env
python -m news_collector.jobs.collect
python -m news_collector.jobs.digest
python -m news_collector.jobs.publish
pytest
```

## Jobs

- `python -m news_collector.jobs.collect`
- `python -m news_collector.jobs.digest`
- `python -m news_collector.jobs.publish`
- `python -m news_collector.jobs.replay`
- `python -m news_collector.jobs.live_test`
- `python -m news_collector.jobs.bootstrap_x_session`
- `python -m news_collector.jobs.bootstrap_reddit_session`

## Cron

```cron
7 * * * * cd /Users/banana/Documents/news_collector && . .venv/bin/activate && python -m news_collector.jobs.collect >> data/cron.log 2>&1
5 7 * * * cd /Users/banana/Documents/news_collector && . .venv/bin/activate && python -m news_collector.jobs.digest >> data/cron.log 2>&1
```
