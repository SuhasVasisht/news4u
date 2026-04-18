# News App

`news-app` is a combined repository for:

- a self-hosted Next.js news reader
- a Python-based news collector and digest pipeline
- a scheduled daily sync that pushes fresh collector data into the app every morning

The app lives at the repo root. The collector lives at `scripts/news_collector/`. The intended deployment model is a single repo that can be moved to another machine and started there with the same structure.

## What This Repo Contains

### App

- Next.js 16 app router app
- feed APIs, story state APIs, auth, and settings UI
- Drizzle schema and migrations
- in-memory fallback mode when no database is configured

### Collector

- Python collector pipeline under `scripts/news_collector`
- source fetchers, normalization, dedupe, clustering, digest generation, and publish jobs
- outbox artifacts and digest files written under `scripts/news_collector/output`

### Scheduler

- a daily orchestration flow exposed by `POST /api/internal/jobs/daily-sync`
- a CLI entrypoint at `npm run job:daily-sync`
- a Docker scheduler service that triggers the job at `5:05 AM` in `America/Los_Angeles`

## Repo Layout

```text
.
├── src/                          # Next.js app
├── drizzle/                      # SQL migrations
├── scripts/
│   ├── daily-sync.ts             # Manual app-side job runner
│   ├── migrate.ts                # DB migration runner
│   ├── seed.ts                   # Seed script
│   ├── scheduler-entrypoint.sh   # Cron bootstrap for Docker scheduler
│   └── news_collector/           # Python collector project
├── tests/                        # App/unit/e2e tests
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

## Daily Sync Architecture

The daily sync job is the integration point between the app and collector.

### Flow

1. Run `news_collector.jobs.collect`
2. Run `news_collector.jobs.digest`
3. Run `news_collector.jobs.publish`
4. Run app feed cleanup
5. Force-refresh the app feed for the current Pacific feed date

### Entry points

- HTTP: `POST /api/internal/jobs/daily-sync`
- CLI: `npm run job:daily-sync`
- Scheduled: Docker `scheduler` service calls the HTTP endpoint on cron

### Auth

- `POST /api/internal/jobs/daily-sync` requires `Authorization: Bearer ${INTERNAL_API_KEY}`
- internal feed endpoints accept either `INTERNAL_API_KEY` or `SYNC_API_KEY`
- collector publish uses `NEWS_APP_SYNC_API_KEY`

### Concurrency

The daily-sync route rejects overlapping runs with `409` while another run is active.

## Environment Variables

Copy `.env.example` to `.env` for Docker or `.env.local` / `.env` for local development.

### Core app env

- `DATABASE_URL`: Postgres connection string
- `SYNC_API_KEY`: app sync bearer token for article ingestion
- `INTERNAL_API_KEY`: app internal job/feed token
- `AUTH_SECRET`: NextAuth secret
- `AUTH_GOOGLE_ID`: optional Google OAuth client ID
- `AUTH_GOOGLE_SECRET`: optional Google OAuth client secret
- `APP_TIMEZONE`: app timezone, defaults to `America/Los_Angeles`
- `APP_DAILY_RESET_HOUR`: feed reset hour, defaults to `5`

### Scheduler env

- `DAILY_SYNC_CRON`: cron expression for scheduled daily sync, defaults to `5 5 * * *`

### Collector env

- `NEWS_COLLECTOR_DB_PATH`: collector SQLite path relative to `scripts/news_collector`
- `NEWS_COLLECTOR_OUTPUT_DIR`: collector output dir relative to `scripts/news_collector`
- `NEWS_COLLECTOR_SYNC_OUTBOX_DIR`: collector sync outbox dir relative to `scripts/news_collector`
- `NEWS_COLLECTOR_USER_AGENT`: outbound collector user agent
- `NEWS_COLLECTOR_X_PROFILE_DIR`: persistent X profile dir
- `NEWS_COLLECTOR_REDDIT_PROFILE_DIR`: persistent Reddit profile dir
- `NEWS_APP_BASE_URL`: app base URL used by collector publish
- `NEWS_APP_SYNC_API_KEY`: bearer token used by collector publish
- `NEWS_APP_SYNC_BATCH_SIZE`: max articles per publish batch
- `NEWS_COLLECTOR_REPLAY_BATCH_SIZE`: replay batch size
- `NEWSAPI_KEY`: optional NewsAPI key
- `GUARDIAN_API_KEY`: Guardian API key
- `ALPHAVANTAGE_API_KEY`: Alpha Vantage API key
- `PRODUCTHUNT_TOKEN`: optional Product Hunt token
- `PYTHON_BIN`: optional Python executable for app-triggered collector runs

### Local host recommendation

If you want the app to invoke the collector venv on your machine, set:

```bash
PYTHON_BIN=scripts/news_collector/.venv/bin/python
```

In Docker you should leave `PYTHON_BIN` empty so the container uses its installed `python3`.

## Local Development

### 1. Install app dependencies

```bash
npm install
```

### 2. Install collector dependencies

```bash
cd scripts/news_collector
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install '.[dev]'
playwright install chromium
cd ../..
```

The collector currently expects Python `3.10+`. Using `3.12` is the safest local path.

### 3. Create local env

For a lightweight app-only local run:

```bash
cp .env.example .env
```

Then set at least:

```bash
SYNC_API_KEY=local-sync-key
INTERNAL_API_KEY=local-internal-key
AUTH_SECRET=local-auth-secret
PYTHON_BIN=scripts/news_collector/.venv/bin/python
```

### 4. Start the app

```bash
npm run dev
```

Without a working `DATABASE_URL`, the app uses in-memory mock data. That is useful for UI work but not for persistent ingestion.

### 5. Run database migrations when using Postgres

```bash
npm run db:migrate
npm run db:seed
```

## Running the Collector Manually

All collector commands run from `scripts/news_collector`.

```bash
cd scripts/news_collector
source .venv/bin/activate
python -m news_collector.jobs.collect
python -m news_collector.jobs.digest
python -m news_collector.jobs.publish
```

Useful additional jobs:

```bash
python -m news_collector.jobs.replay
python -m news_collector.jobs.live_test
python -m news_collector.jobs.bootstrap_x_session
python -m news_collector.jobs.bootstrap_reddit_session
```

## Running the Integrated Sync

### Manual CLI run

```bash
npm run job:daily-sync
```

### HTTP-triggered run

```bash
curl -X POST \
  -H "Authorization: Bearer ${INTERNAL_API_KEY}" \
  http://127.0.0.1:3000/api/internal/jobs/daily-sync
```

The response includes:

- top-level status and timing
- per-step results for `collect`, `digest`, `publish`, `cleanup`, and `feedRefresh`
- optional collector skips such as missing persistent X/Reddit profiles

## Docker Compose

This is the preferred deployment model when moving the repo to another machine.

### Start the stack

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec web npm run db:migrate
```

### Services

- `web`: Next.js app and embedded collector runtime
- `scheduler`: cron process that calls the daily-sync route
- `db`: Postgres 16
- `proxy`: Caddy reverse proxy with basic auth

### Persistent data

Repo-local runtime data is stored in ignored paths:

- `scripts/news_collector/data/`
- `scripts/news_collector/output/`

Those should be preserved when moving machines if you want to keep collector state, digests, sync outbox history, and browser session profiles.

### Notes

- `NEWS_APP_BASE_URL` should remain `http://127.0.0.1:3000` inside the app container for self-calls during publish.
- `scheduler` posts to `http://web:3000/api/internal/jobs/daily-sync`.
- `proxy` fronts the app with Caddy and basic auth.

## Optional Browser-Backed Sources

Some collectors need persisted browser state:

- `x_search`
- `reddit`

These are intentionally optional and not committed.

### Bootstrap browser sessions

```bash
cd scripts/news_collector
source .venv/bin/activate
python -m news_collector.jobs.bootstrap_x_session
python -m news_collector.jobs.bootstrap_reddit_session
```

This will create profile directories under:

- `scripts/news_collector/data/x_profile`
- `scripts/news_collector/data/reddit_profile`

### Missing profile behavior

If those directories do not exist, those collectors degrade and the rest of the sync continues. They do not block the full daily job.

## Outputs and Artifacts

### Collector outputs

- `scripts/news_collector/output/YYYY-MM-DD/digest.md`
- `scripts/news_collector/output/YYYY-MM-DD/digest.json`

### Collector sync outbox

- `scripts/news_collector/output/sync/<run-id>/articles.json`
- `scripts/news_collector/output/sync/<run-id>/manifest.json`
- `scripts/news_collector/output/sync/<run-id>/last_response.json`

These are useful for debugging publish failures and replaying batches.

## API Summary

### Health

- `GET /api/health`

### Feed and story APIs

- `GET /api/feed/today`
- `GET /api/feed/catchup`
- `GET /api/feed/saved`
- `GET /api/feed/archived`
- `POST /api/stories/:id/read`
- `POST /api/stories/:id/save`
- `POST /api/stories/:id/archive`

### Internal sync APIs

- `POST /api/internal/articles/sync`
- `POST /api/internal/feed/generate`
- `POST /api/internal/feed/cleanup`
- `POST /api/internal/jobs/daily-sync`

## Testing

### App unit tests

```bash
npm test
```

### Collector tests

```bash
npm run test:collector
```

### Production build

```bash
npm run build
```

### Playwright

```bash
npm run test:e2e
```

### Full verification

```bash
npm run test:all
```

## Common Workflows

### Fresh machine setup

1. Clone repo
2. Copy `.env.example` to `.env`
3. Fill in secrets and API keys
4. Start Docker Compose or install local Node/Python deps
5. Run migrations
6. Bootstrap X/Reddit sessions if you need those sources
7. Trigger `npm run job:daily-sync` or call the internal route once to verify

### Validate that sync is working

1. `GET /api/health`
2. trigger `POST /api/internal/jobs/daily-sync`
3. check `scripts/news_collector/output/`
4. check `scripts/news_collector/output/sync/`
5. check `GET /api/feed/today`

## Troubleshooting

### `Invalid payload` during publish

Usually means the collector payload does not match the app sync schema. Inspect the latest:

- `scripts/news_collector/output/sync/<run-id>/articles.json`
- `scripts/news_collector/output/sync/<run-id>/last_response.json`

### App can’t run collector locally

Set:

```bash
PYTHON_BIN=scripts/news_collector/.venv/bin/python
```

and make sure the venv exists and has the collector dependencies installed.

### Browser-backed collectors are skipped

That is expected if the profile directories do not exist yet. Run the bootstrap jobs first.

### App uses mock data instead of Postgres

Check `DATABASE_URL`. Without a usable database connection, the app falls back to in-memory data.

### Docker scheduler is not firing

Check:

- `DAILY_SYNC_CRON`
- `APP_TIMEZONE`
- `INTERNAL_API_KEY`
- scheduler container logs

## Current Defaults

- timezone: `America/Los_Angeles`
- daily feed reset hour: `5`
- scheduled sync: `5:05 AM PT`
- app root: repo root
- collector root: `scripts/news_collector`
