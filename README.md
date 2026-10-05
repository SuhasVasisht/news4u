# News App

For unattended daily publishing on a VM, use the [remote publisher setup](docs/remote-publisher.md). The legacy sync scheduler does not publish the static newspaper.

## Shared Spreads Reader And Static Daily Edition

The reader now uses the neutral Shared Spreads design. Run `npm run build:daily` to collect current sources and create `out/index.html`, or `npm run build:static` to rebuild an already-current snapshot. The same React reader powers the Next.js app and the standalone HTML.

See [static build, scheduling, and migration notes](docs/static-edition.md) and the [September 8 source and deduplication audit](docs/source-audit-2026-09-08.md). The older backend documentation below describes the retained Postgres/auth pipeline, not the new static-first reader's state model.

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
- startup catch-up on `web` boot if the current feed run is missing

## Repo Layout

```text
.
├── src/                          # Next.js app
├── drizzle/                      # SQL migrations
├── data/                         # local ignored runtime data
├── logs/                         # local ignored runtime logs
├── scripts/
│   ├── daily-sync.ts             # Manual app-side job runner
│   ├── migrate.ts                # DB migration runner
│   ├── seed.ts                   # Seed script
│   ├── scheduler-entrypoint.sh   # Cron bootstrap for Docker scheduler
│   ├── startup-catchup.ts        # Boot-time missed-run trigger
│   ├── web-entrypoint.sh         # Container startup wrapper
│   └── news_collector/           # Python collector project
├── tests/                        # App/unit/e2e tests
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── .env.production.example
```

## Daily Sync Architecture

The daily sync job is the integration point between the app and collector.

### Flow

1. Run `news_collector.jobs.collect`
2. Run `news_collector.jobs.digest`
3. Run `news_collector.jobs.publish`
4. Run app feed cleanup
5. Force-refresh the app feed for the current Pacific feed date

The publish step does not write directly to Postgres. It posts article batches to the app’s internal sync API, and the app persists them into Postgres.

### Entry points

- HTTP: `POST /api/internal/jobs/daily-sync`
- CLI: `npm run job:daily-sync`
- Scheduled: Docker `scheduler` service calls the HTTP endpoint on cron
- Boot recovery: `web` runs `npm run startup:catchup` after startup if the current feed run is missing

### Auth

- `POST /api/internal/jobs/daily-sync` requires `Authorization: Bearer ${INTERNAL_API_KEY}`
- internal feed endpoints accept either `INTERNAL_API_KEY` or `SYNC_API_KEY`
- collector publish uses `NEWS_APP_SYNC_API_KEY`

### Concurrency

The daily-sync route rejects overlapping runs with `409` while another run is active.

### Durability model

- app data is stored in Postgres
- collector state and caches are stored under `scripts/news_collector/data/`
- collector digests and sync outbox bundles are stored under `scripts/news_collector/output/`
- Docker Postgres persistence comes from the named volume `postgres_data`

This is durable across container restarts, but not a substitute for real backups.

## Environment Variables

Copy `.env.example` to `.env` for local or Docker development. This repo does not currently include a separate `.env.production.example`, so production should also start from `.env.example` and then replace every placeholder with real values.

### Core app env

- `POSTGRES_DB`: Postgres database name for Compose deployments
- `POSTGRES_USER`: Postgres username for Compose deployments
- `POSTGRES_PASSWORD`: Postgres password for Compose deployments
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
- `RUN_DB_MIGRATIONS_ON_STARTUP`: run DB migrations during web container boot
- `STARTUP_CATCHUP_ENABLED`: trigger a missed daily sync on app startup when needed
- `STARTUP_CATCHUP_URL`: internal endpoint used by startup catch-up
- `WEB_STARTUP_HEALTH_RETRIES`: max retries while waiting for the web app to become healthy on boot

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

### Production env recommendation

Start from:

```bash
cp .env.example .env
```

Then replace all placeholder credentials before starting the stack.

For the current Docker production path, set these explicitly:

```bash
NEWS_APP_BASE_URL=http://web:3000
NEWS_APP_SYNC_API_KEY=${SYNC_API_KEY}
PYTHON_BIN=
AUTH_TRUST_HOST=true
AUTH_URL=https://your-domain.example
NEXTAUTH_URL=https://your-domain.example
```

Notes:

- `NEWS_APP_BASE_URL` must point at the internal Docker service, not `127.0.0.1`
- leave `PYTHON_BIN` empty in Docker so the container uses its installed Python runtime
- `AUTH_URL` and `NEXTAUTH_URL` must match the public HTTPS origin used by the browser, or OAuth callbacks will redirect to the wrong host

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

Then generate unique local credentials:

```bash
SYNC_API_KEY=$(openssl rand -hex 32)
INTERNAL_API_KEY=$(openssl rand -hex 32)
AUTH_SECRET=$(openssl rand -hex 32)
PYTHON_BIN=scripts/news_collector/.venv/bin/python
```

Store the generated values in your ignored `.env` file; do not commit them.

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
npm run startup:catchup
npm run audit:data-pipeline
```

`npm run audit:data-pipeline` runs the collector pipeline in order and then prints the exact local artifacts to review:

- collector SQLite rows from `raw_items`, `normalized_items`, and `story_clusters`
- latest digest output under `scripts/news_collector/output/`
- latest sync outbox bundle under `scripts/news_collector/output/sync/`
- app-side article, story, and feed rows when `DATABASE_URL` is usable from the current shell
- feed/story HTTP responses if the app is reachable at `http://127.0.0.1:3000`

When reviewing score quality, compare:

- `payload_json.collector.importance_score`: collector reference score on the `0.0-1.0` scale
- `articles.score`: app-recomputed score on the `0-10` scale used by story/feed ranking
- `stories.importance_score`: story rollup derived from the best article score

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
```

The `web` container now runs migrations automatically on startup by default.

### Services

- `web`: Next.js app and embedded collector runtime
- `scheduler`: cron process that calls the daily-sync route
- `db`: Postgres 16
- `proxy`: Caddy reverse proxy on host port `80`

### Persistent data

Repo-local runtime data is stored in ignored paths:

- `scripts/news_collector/data/`
- `scripts/news_collector/output/`
- `logs/scheduler/`

Those should be preserved when moving machines if you want to keep collector state, digests, sync outbox history, and browser session profiles.

Postgres data is stored in the Docker named volume `postgres_data`.

### Health and startup behavior

- `db` has a `pg_isready` health check
- `web` has an `/api/health` health check
- `scheduler` waits for `web` to become healthy
- `proxy` waits for `web` to become healthy
- `web` runs boot-time catch-up to avoid missing a daily run just because the scheduler was down at 5:05 AM PT

### Notes

- `NEWS_APP_BASE_URL` should be `http://web:3000` so the scheduler container can publish into the app over the internal Docker network.
- `scheduler` posts to `http://web:3000/api/internal/jobs/daily-sync`.
- `proxy` fronts the app with Caddy on host port `80`.
- `syncArticles()` is transactional so a partial batch does not commit halfway through.

## Static Publishing To Cloudflare

The newspaper is built locally and deployed as static HTML to Cloudflare Pages.
The latest paper lives at `/`, and **Past editions** opens the dated archive at
`/editions/`. Generated editions and approved WebP media stay outside Git. Each
deployment backs up its public bundle to `~/news4u-backups/`; set `NEWS_BACKUP_DIR`
to use another location outside the workspace. Image redistribution permissions
are configured explicitly in `config/image-permissions.json`.
Use `npm run publish:daily` to collect, review, build, deploy, and test the public
site, or `npm run publish:static` to publish the already reviewed daily snapshot.
Deployment setup, DNS migration, credentials, verification and rollback are documented
in [docs/cloudflare-deployment.md](docs/cloudflare-deployment.md).

## Legacy Server Setup

This is the previous server deployment: Docker Compose on the host, Caddy bound to
local port `80`, and a Cloudflare tunnel forwarding the public hostname. It is not
required for the static Pages deployment. Keep unrelated tunnel routes intact.

### 1. Host requirements

- Docker Engine with `docker compose`
- a working Cloudflare Tunnel on the host
- outbound network access for the app and scheduler containers
- enough disk for the Postgres volume plus `scripts/news_collector/data/` and `scripts/news_collector/output/`

### 2. Required env values

Set these before first start:

```bash
POSTGRES_PASSWORD=replace-me
DATABASE_URL=postgres://postgres:<url-encoded-password>@db:5432/signal_desk
SYNC_API_KEY=replace-me
INTERNAL_API_KEY=replace-me
AUTH_SECRET=replace-me
AUTH_TRUST_HOST=true
AUTH_URL=https://your-domain.example
NEXTAUTH_URL=https://your-domain.example
NEWS_APP_BASE_URL=http://web:3000
NEWS_APP_SYNC_API_KEY=${SYNC_API_KEY}
PYTHON_BIN=
```

Optional but usually needed:

```bash
NEWSAPI_KEY=...
GUARDIAN_API_KEY=...
ALPHAVANTAGE_API_KEY=...
PRODUCTHUNT_TOKEN=...
AUTH_GOOGLE_ID=...
AUTH_GOOGLE_SECRET=...
```

### 3. Google OAuth setup

If you enable Google sign-in, the Google OAuth client must include the public callback URL:

```text
https://your-domain.example/api/auth/callback/google
```

Do not use `http://localhost:3000/...` in the production Google client.

### 4. Cloudflare tunnel setup

Point the public hostname at the local Caddy proxy on port `80`, not the Next.js process directly.

Example `~/.cloudflared/config.yml`:

```yaml
tunnel: <tunnel-uuid>
credentials-file: /home/<user>/.cloudflared/<tunnel-uuid>.json

ingress:
  - hostname: your-domain.example
    service: http://localhost:80
  - service: http_status:404
```

Then run the tunnel as a persistent service on the host.

### 5. Start production

```bash
docker compose up -d --build
```

That starts:

- `db`: Postgres 16 with persisted Docker volume storage
- `web`: Next.js app with startup migrations
- `scheduler`: cron-driven daily sync runner
- `proxy`: Caddy reverse proxy on `127.0.0.1:80`

### 6. Verify production health

Check container state:

```bash
docker compose ps
```

Check app health from inside the stack:

```bash
docker compose exec -T web curl -fsS http://127.0.0.1:3000/api/health
```

The expected production result includes:

```json
{"status":"ok","databaseConfigured":true}
```

Check the feed:

```bash
docker compose exec -T web curl -fsS http://127.0.0.1:3000/api/feed/today
```

Check the public site:

```bash
curl -I https://your-domain.example/
```

### 7. Logs and day-2 operations

Useful commands:

```bash
docker compose logs --tail=100 web
docker compose logs --tail=100 scheduler
docker compose logs --tail=100 proxy
docker compose exec -T scheduler sh -lc 'cd /app/scripts/news_collector && /opt/venv/bin/python -m news_collector.jobs.replay'
```

Use the replay command when collector data already exists on disk and you need to republish it into Postgres.

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

### Docker verification

```bash
docker compose ps
docker compose logs --tail=100 web
docker compose logs --tail=100 scheduler
docker compose exec -T web curl -fsS http://127.0.0.1:3000/api/health
```

## Common Workflows

### Fresh machine setup

1. Clone repo
2. Copy `.env.example` to `.env` or `.env.production.example` to `.env`
3. Fill in secrets and API keys
4. Start Docker Compose or install local Node/Python deps
5. Let web startup run migrations, or run them manually if you disabled startup migrations
6. Bootstrap X/Reddit sessions if you need those sources
7. Trigger `npm run job:daily-sync` or call the internal route once to verify

### Validate that sync is working

1. `GET /api/health`
2. trigger `POST /api/internal/jobs/daily-sync`
3. check `scripts/news_collector/output/`
4. check `scripts/news_collector/output/sync/`
5. check `GET /api/feed/today`
6. check `logs/scheduler/daily-sync.log` after the scheduled window if using Docker cron
7. or run `npm run audit:data-pipeline` to execute the same stages locally and print the review checkpoints in order

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
- `logs/scheduler/daily-sync.log`

### App boots but Auth.js logs `UntrustedHost`

Set the appropriate trusted host variables for your deployment before relying on auth in production. The current stack can still sync news, but auth host configuration should be completed separately.

### Web startup catch-up does not run

Check:

- `STARTUP_CATCHUP_ENABLED`
- `STARTUP_CATCHUP_URL`
- `INTERNAL_API_KEY`
- web container logs during boot

### Postgres survives restarts but not host loss

That is expected with the current Docker volume setup. Add external backups or managed Postgres if you need production-grade recovery.

## Current Defaults

- timezone: `America/Los_Angeles`
- daily feed reset hour: `5`
- scheduled sync: `5:05 AM PT`
- app root: repo root
- collector root: `scripts/news_collector`
- scheduler logs: `logs/scheduler/`
- Docker DB volume: `postgres_data`
