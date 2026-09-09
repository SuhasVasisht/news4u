# Shared Spreads: Build And Serve

The neutral Shared Spreads layout is now the reader for the Next.js app and the standalone HTML build. The approved design artifacts remain unchanged.

## Daily Build

```sh
npm run build:daily
```

This runs collection and image verification, prepares source text and full podcast transcripts, invokes the Codex editorial admission and whole-edition selection passes, validates the review, exports `data/edition.json`, and renders `out/index.html` plus dedicated report pages. The Python virtual environment under `scripts/news_collector/.venv` is used by default. Set `PYTHON_BIN` to an executable name or path to override it.

The build machine needs an authenticated Codex CLI (`codex login`) and the collector's Python dependencies. Editorial calls use the existing CLI account and consume its usage allowance; no X or paid source API integration is enabled by this change. `NEWS_EDITOR_CODEX_BIN` and `NEWS_EDITOR_MODEL` can override the executable and model. Source text is untrusted input; the review runs with shell, browser, app, hooks, and web-search tools disabled. Malformed or unsupported decisions stop publication rather than admitting unreviewed content.

Reviews are cached by content and policy hash in `data/editorial/`. Full audio is transcribed locally with faster-whisper when a publisher does not supply sufficient transcript text. The first run downloads the `small.en` model and can take tens of minutes per episode on CPU. Transcripts are cached in the collector data directory; `NEWS_TRANSCRIPTION_MODEL` configures the model. Publisher transcripts, machine transcripts, and feed excerpts retain distinct reader-facing labels. Inaccessible or incomplete episodes are held, not summarized from a title. Notes are original editorial summaries, not verbatim transcripts or a guarantee that every detail of listening is reproduced.

The collector loads the existing root and collector `.env` files. Keep credentials on the build machine. The browser never calls source APIs or receives their credentials.

To rebuild the HTML from an already collected snapshot:

```sh
npm run build:static
```

The build requires the current date in `America/Los_Angeles`, a snapshot generated within 24 hours, and at least one selected item dated today. It rejects future dates and duplicate story IDs. Collection timestamps are not substituted for missing article dates. Old and undated database rows are excluded. On failure, the previous `out/index.html` remains in place. A lock prevents simultaneous static builds; after a crashed process, confirm no build is running before removing `data/static-build.lock`.

## Outputs And Review

| File | Purpose |
| --- | --- |
| `out/index.html` | Deploy this file to an ordinary static host; also opens directly in a browser |
| `out/build-review.json` | Build date, item counts, and source warnings |
| `data/edition.json` | Shared live-app and static-build snapshot |
| `data/edition-audit.json` | Source health, freshness exclusions, deduplication denominators and examples |
| `data/collection-run.json` | Last full daily collection results |

The HTML includes server-rendered news, React, CSS, fonts, and data. Reading works without JavaScript; interactive controls require JavaScript. Episode audio and unapproved photos remain publisher-hosted, so this is not a complete offline media archive. Images explicitly approved in `config/image-permissions.json` are optimized into local WebP assets during the build. Failed images are omitted and low-resolution thumbnails are not enlarged. Original summaries, podcast notes, and links are exported, not full source articles or transcripts. Review publisher reuse and image permissions before public redistribution.

Cloudflare publishing additionally assembles `/editions/` and immutable dated edition
and report pages in the public release bundle, migrates the previous reviewed paper,
and backs up the bundle outside Git. Deploy through `npm run publish:daily` or
`npm run publish:static`, not by uploading all of `out/`. See
[Cloudflare publishing](cloudflare-deployment.md) for archive retention, approved
image assets, local backup/restore, and pre-upload/public browser verification.

Today displays a rolling 48-hour news window plus clearly labeled reading/listening selections from a 30-day long-form window. Original dates remain visible; an older interview is not presented as today's breaking news. Source feeds sometimes supply discovery dates rather than original publication dates, especially Hacker News, Techmeme, and GDELT; do not interpret a newly surfaced item as proof the underlying event happened today.

## Daily Scheduling

A separate deployment is supplied so the existing production stack is not silently replaced. Authenticate its dedicated Codex directory first (`NEWS_EDITOR_AUTH_DIR` defaults to `./data/editor-auth`), for example:

```sh
CODEX_HOME="$PWD/data/editor-auth" codex login
```

Do not commit this directory or serve it publicly. Then:

```sh
docker compose -f docker-compose.static.yml up --build -d
```

It serves `out/` on `http://localhost:8080` and builds at 05:05 Pacific daily, configurable with `DAILY_SYNC_CRON` in `.env`. Startup builds a missing or out-of-date edition. The builder has outbound networking; the old Compose backend-only scheduler network was unsuitable for reaching external news APIs. The static deployment needs neither Postgres nor a running Next.js server. It uses the existing worker image and adds a static Caddy service. No production deployment or host cron entry was activated during implementation.

For a non-Docker scheduler, run `npm run build:daily` from the repository directory once a day in the configured timezone. Ensure Node and Python are on the scheduler's PATH. Serve the resulting file; do not expose `.env`, collector state, or `data/`.

## State And Migration Boundary

The new reader stores saved, read, archived, hidden-publisher, and manual ranking state in `news4u-reader-v1` localStorage. Saved and archived excerpts are retained locally when they age out of a later snapshot. Browser storage can be cleared or denied and is not an account backup. Preferences do not sync across devices or origins; local-file storage behavior is browser-dependent.

This is intentionally a static-first reader. The existing Postgres database, Auth.js backend, ingestion endpoints, and historical data have not been deleted, but the new reader reads the collector snapshot rather than the old personalized Postgres feeds. Existing account-saved items and old article/story IDs are not automatically migrated to the new snapshot IDs. Account-state migration/synchronization needs a separate adapter before treating this as a drop-in replacement for signed-in, multi-device use.

All reading routes use the new layout. Legacy story links resolve to their original publisher when the retained backend can find them; unknown IDs return 404. The static edition uses dedicated HTML report pages, not Next.js API routes or authentication. Optional color themes remain deferred in `designs/TODO.md`.

## Verification

```sh
npm test
npm run test:collector
npm run lint
npm run build
npm run build:static
E2E_BASE_URL=http://localhost:3010 npm run test:e2e
```

Without `E2E_BASE_URL`, Playwright can start the development app on port 3000. Static tests require a built `out/index.html`; they verify offline interaction and readable HTML with JavaScript disabled. The Docker configuration has been validated, but the new Docker services have not been deployed or exercised through a real overnight scheduled run.
# Report Pages And Short Edition

Report headlines now open dedicated reading pages, not dialogs. Static output includes
`report-*.html` and shared `reader-*.css/js` assets alongside the self-contained index.
For Cloudflare, serve the allowlisted `data/cloudflare-bundle/` assembled by the
deployment pipeline, which retains older report links and dated edition snapshots.

The "I do not have time" tab shows up to eight priority stories in the current
48-hour edition, honoring hidden publishers and archived stories. It includes a lead
from each available sector, caps repeat publishers, and down-ranks routine stock alerts.
Manual sector ordering does not alter this importance-ranked selection.

Image resolution now runs inside the Python collection pipeline, before raw storage
and normalization, and in the legacy publishing path. Each collection also refreshes
the prior seven days of stored articles so duplicates cannot retain old thumbnails.
Snapshot export and HTML rendering do not rewrite image URLs.

The pipeline resolves publisher image metadata and verifies actual image dimensions.
Images below 400 x 200 pixels or unavailable images are omitted, never enlarged or
replaced with unrelated stock photos. Results and dimensions are stored in the collector
database's `image_quality_cache` table. Successful checks expire after seven days;
failures expire after six hours, so the next daily collection retries them.
The former post-export image job and JSON cache are no longer used.
Photos remain remote and may be unavailable offline or if a publisher blocks requests.
