# News 4 u

A daily newspaper built from a Python news collector and a shared React reader. The public edition is served as static HTML on Cloudflare Pages at [news.suhasv.com](https://news.suhasv.com), with dedicated report pages, sports coverage, and a dated archive.

The daily publisher collects sources, reviews evidence, runs independent coverage and factual audits, builds the newspaper, and verifies it locally and on the public site. The repository also retains a Next.js app and a separate Postgres ingestion backend for development and legacy use.

## Reader and editorial pipeline

- Newspaper navigation with a full edition, a short edition, sections, search, and color themes.
- Dedicated report pages with original summaries, publisher attribution, source links, photographs, and podcast notes when available.
- A rolling 48-hour breaking-news window and separately labeled longer-form reading and listening selections.
- Source-date verification, duplicate-event checks, publisher caps, and evidence-bound factual review before publication.
- Sports review against prior editions so a new URL or retrospective article does not make an old event new.
- Archived editions and retained report links, with approved local image assets governed by `config/image-permissions.json`.

The current reader presents the complete published edition. It does not use the old saved, read, archived, or hidden-publisher state to hide stories, and it does not synchronize reading state through accounts. See [newspaper reading](docs/newspaper-reading.md), [themes](docs/edition-themes.md), and [editorial quality](docs/daily-editorial-quality.md).

## Repository layout

```text
src/                         Next.js app, shared reader, and retained backend
scripts/publish-daily.ts      Checkpointed daily publishing orchestrator
scripts/build-static.tsx      Static newspaper renderer
scripts/deploy-cloudflare.ts  Release assembly, backup, upload, and verification
scripts/news_collector/      Python collectors, editorial jobs, configuration, tests
config/                      Image redistribution permissions
public/fonts/                Bundled fonts and their licenses
deploy/                      Native and Docker systemd services and timers
docs/                        Deployment, editorial, and reader guides
tests/                       TypeScript unit tests and Playwright checks
drizzle/                     Legacy Postgres schema migrations
data/                        Ignored snapshots, reviews, checkpoints, and logs
out/                         Ignored generated HTML and media
compose.publisher.yml        Production static publisher container
docker-compose.yml           Legacy Next.js/Postgres stack
```

## Local setup

Use Node.js 22 and Python 3.10 or later (Python 3.12 is used for native Ubuntu setup). The publisher image pins Node 22.22.0, uv 0.10.9, and Codex CLI 0.157.1; `package-lock.json` and `scripts/news_collector/uv.lock` pin application dependencies.

Install JavaScript and Python dependencies, then Chromium for both Playwright runtimes:

```sh
npm ci
uv sync --project scripts/news_collector --locked --extra dev
npx playwright install chromium
scripts/news_collector/.venv/bin/python -m playwright install chromium
```

On Linux, install Playwright's system dependencies as described in the [remote publisher guide](docs/remote-publisher.md).

For collection and publishing, create a local environment file from the tracked example:

```sh
cp deploy/publisher.env.example .env
chmod 600 .env
```

Fill in the mailbox username and Gmail app password, Cloudflare token and account ID, and any optional source API credentials. Editorial review requires an authenticated Codex CLI and sufficient account capacity. `NEWS_EDITOR_CODEX_BIN`, `NEWS_EDITOR_MODEL`, and `NEWS_EDITOR_REASONING_EFFORT` can select the executable, model, and reasoning effort. The Python runtime defaults to `scripts/news_collector/.venv/bin/python`; `PYTHON_BIN` can override it.

The publisher loads root `.env` and `.env.newsletters`. The collector also loads its own `scripts/news_collector/.env`. Environment files, credentials, browser profiles, generated content, databases, and runtime logs stay outside Git. The tracked `deploy/publisher.env.example` is the setup template; root `.env.example` files are not included in a fresh clone.

To work on the reader:

```sh
npm run dev
```

Open `http://localhost:3000`. The reader loads `data/edition.json`; a fresh checkout without that snapshot shows an empty edition. Postgres is not required for the newspaper reader.

## Build and publish

| Command | Purpose |
| --- | --- |
| `npm run build:daily` | Collect, review news and sports, export a snapshot, and render static HTML without uploading |
| `npm run build:static` | Render an existing current snapshot into `out/` |
| `npm run publish:rehearse` | Run the daily publisher and local release verification without uploading |
| `npm run publish:daily` | Collect, audit, build, deploy to Cloudflare, and verify the hosted release |
| `npm run publish:check` | Check that today's edition is live; finish verification of a matching interrupted upload when needed |
| `npm run verify:deployed` | Verify the configured public site with Chromium |
| `npm run publish:static` | Run unit tests, build an existing reviewed snapshot, and deploy it |

`cloudflare-pages.json` sets the Pages project, domain, zone, and production branch. Update it before targeting your own deployment. The daily publisher restores the configured site's existing public manifest and archive before running; it expects an existing production release. Initial launch and Cloudflare configuration are covered in the [deployment guide](docs/cloudflare-deployment.md).

A static build requires a valid, fresh edition snapshot for the current Pacific date. Generated output includes `out/index.html`, `report-*.html`, shared reader assets, and build review records. Deploy through the supported npm commands: the deployer assembles an allowlisted public release in `data/cloudflare-bundle/`, including dated archives, rather than uploading the entire workspace or `out/` directory.

For a guarded correction to an edition already published today:

```sh
npm run publish:daily -- --revise-today --no-upload
# Inspect the validated rehearsal before uploading the correction.
npm run publish:daily -- --revise-today
```

The revision flow retains the original edition in the archive. Ordinary daily runs are no-ops when today's edition is already live. See [static build details](docs/static-edition.md) and [deployment and rollback](docs/cloudflare-deployment.md).

## Unattended publishing and recovery

Follow [the remote publisher setup](docs/remote-publisher.md) for either a native Ubuntu user service or the dedicated Docker publisher in `compose.publisher.yml`. The static publisher needs outbound access, persistent private state, editor authentication, and deployment credentials; it does not need a running Next.js server or Postgres.

The committed systemd timers run at 07:05 in `America/Los_Angeles`, then hourly through 22:05, with reboot catch-up. Enable one scheduling owner. The native user service checks for tracked changes and pulls `origin/main` with `--ff-only` before each invocation. Docker updates require rebuilding the image.

The publisher resumes matching successful checkpoints within six hours on the same local date. Editorial retries preserve validated evidence and repair progress; freshness, coverage, and factual gates still apply. Starts are limited to three per date and code/model revision, at least one hour apart. Hard editor quota exhaustion stops further collection and model calls until capacity is restored or a known reset time arrives.

After fixing an account or configuration block, an operator can retry explicitly:

```sh
npm run publish:daily -- --retry-editor
```

A failed prepublication run leaves the existing site live. Upload can succeed before hosted verification fails, so inspect the status and public manifest before assuming nothing was published. A later run reconciles a matching interrupted upload.

## State, logs, and backups

| Path | Contents |
| --- | --- |
| `data/edition.json` | Snapshot shared by Next.js and the static reader |
| `data/collection-run.json` | Source collection results and errors |
| `data/editorial/`, `data/quality/`, `data/sports/` | Review evidence, audit caches, and sports novelty records |
| `data/publisher-state.json` | Publication checkpoints |
| `data/publisher-status.json` | Current publication status |
| `data/publisher-attempts.json`, `data/editor-quota.json` | Retry budget and editor capacity block |
| `data/publisher-logs/publisher-YYYY-MM-DD.log` | Private timestamped publisher diagnostics |
| `scripts/news_collector/data/` | Collector SQLite database, caches, mailbox cursor, and optional browser profiles |
| `scripts/news_collector/output/` | Collector output and legacy sync outbox |

Supported publisher/build/deploy commands share an OS lock at `data/publisher.lock`; never delete it to bypass a running process. Diagnostic logs redact configured secrets, use private file permissions, and remove matching logs older than 30 days. `NEWS_PUBLISHER_LOG_DIR` can move logs outside the checkout.

Deployments back up public release bundles to `~/news4u-backups/` by default, or `NEWS_BACKUP_DIR` when set. Public release backups do not back up the collector database, mailbox state, credentials, or editor authentication. Preserve private state separately and follow the migration and backup instructions in the [remote publisher guide](docs/remote-publisher.md).

## Checks

```sh
npm test
npm run test:collector
npm run lint
npx tsc --noEmit
npm run build
npm run test:e2e
```

Collector tests use the virtual environment installed above. Playwright starts the development app unless `E2E_BASE_URL` points to an existing server. Static end-to-end checks require a built `out/index.html`; content checks also need a suitable edition snapshot. `npm run test:all` combines unit tests, collector tests, the Next.js build, and Playwright.

GitHub Actions builds `Dockerfile.publisher` on pushes and pull requests, then runs unit tests, collector tests, lint, TypeScript checks, and publisher smoke validation without production credentials. It does not publish the newspaper.

## Retained backend and collector tools

The repository retains Auth.js/Google OAuth, Drizzle/Postgres migrations, feed APIs, and collector-to-app article ingestion. These are separate from the static publication workflow; the legacy daily sync does not publish the Cloudflare newspaper.

Useful legacy commands include `npm run db:migrate`, `npm run db:seed`, `npm run job:daily-sync`, and `npm run audit:data-pipeline`. `docker-compose.yml` contains the legacy web, database, scheduler, and Caddy services. Consult their source configuration before using this stack; removed job, story-action, and preference routes are not part of the current HTTP API.

Collector jobs can also run from `scripts/news_collector/` with its virtual environment activated. See the [collector README](scripts/news_collector/README.md), [newsletter setup](docs/newsletter-sources.md), [sports desk](docs/sports-desk.md), and [source configuration](scripts/news_collector/config/sources.yaml).

## License

Project code and documentation are licensed under the [MIT License](LICENSE), copyright © 2026 Suhas Vasisht.

Bundled Libre Caslon Display and Newsreader fonts retain their SIL Open Font License 1.1 terms; see [Caslon's license](public/fonts/Caslon-LICENSE.txt) and [Newsreader's license](public/fonts/Newsreader-LICENSE.txt). Third-party dependencies and publisher content retain their respective rights and licenses. Image redistribution is configured separately in `config/image-permissions.json`.
