# News App

Combined personal news app and collector repo.

## Layout

- `src/`: Next.js app, APIs, feed logic, auth, and UI
- `scripts/news_collector/`: Python collector pipeline
- `scripts/daily-sync.ts`: manual daily sync runner
- `scripts/scheduler-entrypoint.sh`: Docker scheduler bootstrap

## Local setup

1. Copy `.env.example` to `.env.local` for app dev or `.env` for Docker Compose.
2. Install app deps:

```bash
npm install
```

3. Install collector deps when running outside Docker:

```bash
cd scripts/news_collector
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

If you want the app's daily-sync route to invoke that local venv, set `PYTHON_BIN=scripts/news_collector/.venv/bin/python` in your local `.env`.

4. Start the app:

```bash
npm run dev
```

Without `DATABASE_URL`, the UI uses the seeded in-memory data. With Postgres configured, run:

```bash
npm run db:migrate
npm run db:seed
```

## Daily sync

- Internal endpoint: `POST /api/internal/jobs/daily-sync`
- Auth: `Authorization: Bearer ${INTERNAL_API_KEY}`
- Flow: collect -> digest -> publish -> cleanup -> feed refresh
- Docker scheduler default: `5 5 * * *` in `America/Los_Angeles`

Run it manually from the repo root:

```bash
npm run job:daily-sync
```

## Docker Compose

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec web npm run db:migrate
```

The stack includes:

- `web`: Next.js app plus embedded Python collector runtime
- `scheduler`: cron service that hits the daily-sync endpoint at 5:05 AM PT
- `db`: Postgres
- `proxy`: Caddy reverse proxy with basic auth

Collector runtime data is stored in ignored repo-local paths:

- `scripts/news_collector/data/`
- `scripts/news_collector/output/`

## Optional browser-backed sources

`x_search` and `reddit` require persistent Playwright profile directories. Those profiles are intentionally not committed.

Bootstrap them on a machine that needs those sources:

```bash
cd scripts/news_collector
source .venv/bin/activate
python -m news_collector.jobs.bootstrap_x_session
python -m news_collector.jobs.bootstrap_reddit_session
```

If the profile directories are missing, those collectors are skipped as degraded and the rest of the daily sync continues.

## Tests

```bash
npm test
npm run test:collector
npm run build
npm run test:e2e
```
