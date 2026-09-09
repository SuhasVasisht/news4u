# Cloudflare Static Publishing

Project: `news4u-suhasv`. Live domain: `https://news.suhasv.com`.
Pages URL: `https://news4u-suhasv.pages.dev`.

Domain migration and archive deployment completed September 9, 2026. The initial
paper contained 20 reviewed stories, 19 usable images and three podcast reports.
September 8 (25 stories) and September 9 have permanent dated editions. Public-domain
Chromium verification passed for every current report and every dated report hash,
saved-state persistence, browser-back navigation, the short edition, podcast notes,
no-JavaScript navigation and private-path 404s, with zero browser errors. Desktop,
mobile, archive and podcast screenshots were visually inspected. The release contains
97 hashed public files, about 11.2 MiB before compression, excluding remote media.

The September 9 collection completed at 10:23 UTC; the reviewed snapshot was generated
at 10:36 UTC. Codex CLI quota was exhausted, so the interactive desk used the validated
review-file fallback below. The published text was read end to end and checked against
the reviewed decisions. Tests: 33 app tests, 68 collector tests and 9 browser tests passed;
lint and TypeScript checks also passed. Source warnings remain visible in the private
build report: Guardian uses its public RSS fallback, GDELT was rate-limited, and
Alpha Vantage supplied cached rather than fresh results. Those warnings are not
represented as fresh API collection success.

At 11:29 UTC the September 9 correction replaced that selection with 24 reports,
including 23 source-verified images (22 rendered in the public browser check), one
full Lenny podcast report and a separate full Theo video analysis. Seven exact repeats
from September 8 were removed. The original September 9 edition is retained at
`/editions/2026-09-09-r8880d494a74e/`. The corrected release is
`ab2125f8.news4u-suhasv.pages.dev`, verified on the custom domain as well.
See [the September 9 source audit](source-audit-2026-09-09.md) for current counts,
new sources, novelty gates and remaining source-access limitations.

This is a local build-and-publish pipeline, not a Cloudflare-hosted collector or
Next.js server. Cloudflare receives static HTML, CSS, JavaScript and a public release
manifest. No Functions, Worker runtime, database, R2 bucket, or paid plan is enabled.
[Static requests are free and unlimited](https://developers.cloudflare.com/pages/functions/pricing/#static-asset-requests).
The release checks the [Free plan upload limits](https://developers.cloudflare.com/pages/platform/limits/):
20,000 files and 25 MiB per file. Approved photos can be bundled as static WebP assets;
other photos and original podcast audio remain publisher-hosted.

## Edition Archive

`/` serves the latest published edition. `/editions/` lists the retained newspapers,
and `/editions/YYYY-MM-DD/` is a permanent edition with its own report pages and
public snapshot. The reader's **Past editions** link opens this archive; **Archived**
still means browser-local saved-away stories, not the historical newspaper library.

Each deployment preserves dated HTML, original story selection, notes, text, assets,
and ordering. Reusing a story ID in tomorrow's report cannot overwrite yesterday's
dated report. A different snapshot for an already frozen date is rejected by default.
An intentional correction uses `npm run deploy:static -- --revise-today`: the old
version is preserved at a content-addressed dated revision URL, linked from the
archive, before the corrected current-day edition becomes canonical. This flag
cannot rewrite previous days. Exact retries are allowed without the flag.
The existing September 8 paper is migrated from its reviewed deployed snapshot.

The full retained public archive is uploaded with every release. Local staging is
assembled separately and only replaces the prior bundle after all release checks pass.
The previous staging bundle remains under `data/cloudflare-bundle.previous`.
`data/cloudflare-published/` retains the last successfully verified deployment and
is the source of historical editions for the next release. A failed new staging
attempt does not become the historical source for tomorrow's paper.
No history, images, generated HTML, credentials or transcripts are committed to Git.

## Image Permissions

`config/image-permissions.json` contains exact approved image URLs:

```json
{
  "approved": [{
    "imageUrl": "https://publisher.example/photo.jpg",
    "credit": "Photographer / approved license",
    "licenseUrl": "https://publisher.example/photo-license"
  }]
}
```

Only add an entry after confirming permission to redistribute and resize that image.
The initial list is empty because publisher reuse licenses have not been supplied.
Unapproved images remain external; they are not downloaded into the static bundle.
This means the media pipeline is implemented, but the current publisher photos are
not all self-hosted. Full podcast audio is not copied or redistributed.

On every build, approved images are downloaded with a 20 MiB input limit and timeout,
decoded with a pixel limit, checked against the 400 x 200 minimum, resized to at most
1600 pixels wide without enlargement, and encoded as WebP. The content hash determines
the filename, so duplicate image bytes share one `/media/HASH.webp` asset. Credit and
the permission link are rendered with the image, including sidebar photos. Failed
optimization falls back to the publisher URL and is recorded privately in
`data/media-audit.json`. Redirect destinations require explicit review rather than
silently widening an approved URL. The public snapshot keeps the original image URL
alongside any approved local asset metadata.

## Backups

Deployments create compressed copies of the public bundle before staging and after
successful public verification in `~/news4u-backups/`, outside the Git workspace.
Set `NEWS_BACKUP_DIR` in `.env` to another directory outside the project, preferably
an externally backed-up or synced location. Failure to create a required backup stops
the command. No paid storage service or off-machine backup has been provisioned.

These archives contain the public edition snapshots, reports and bundled media, not
the private collector database, raw transcripts, editorial caches or credentials.
Keep a separate protected machine backup for those private build inputs.
To restore a chosen trusted backup into an empty recovery directory:

```sh
mkdir -p /path/to/recovery
tar -xzf /path/to/DATE-published.tar.gz -C /path/to/recovery
```

Inspect it before replacing the local bundle. Do not restore over the live workspace
while a build or deployment is running. Keep historical files when moving build machines.

## Credentials

Use Node 22 or newer, `npm ci`, and `npx playwright install chromium`.
Add these values to the ignored `.env`, or supply them in a trusted CI environment:

```dotenv
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_API_TOKEN=your-api-token
```

The existing misspelled `CLOUFLARE_ACCOUNT` and `CLOUFLARE_API_KEY` variables are
supported as fallbacks. The latter must contain a bearer API token, not a Global API
Key that requires email authentication. Tokens never go in command arguments or the
published files. Do not commit `.env` or upload it as a build artifact.

For publishing, grant Account / Cloudflare Pages / Edit on the account. Initial DNS
migration additionally needs Zone / Zone / Read and Zone / DNS / Edit on `suhasv.com`.
A narrower Pages-only token can be used after migration. DNS access was confirmed after
the token permissions were updated on September 9, 2026.

## First Deployment And DNS Migration

```sh
npm run build:static
npm run deploy:static -- --pages-only
npm run deploy:static -- --connect-domain --skip-upload
```

The first command renders the reviewed local snapshot without collecting again.
The second creates the Direct Upload Pages project if absent, uploads the public
bundle and verifies its Pages URL. The third verifies the existing uploaded release,
attaches the custom domain to Pages and replaces only `news.suhasv.com`'s tunnel CNAME.
`--skip-upload` uses the existing staged manifest without rebuilding or enforcing a new
publication date. It still requires the live release to match the local bundle and pass
browser verification before changing DNS. Normal uploads retain the freshness gate.
It refuses to overwrite unrelated DNS targets or other record types. The original
record is backed up under `data/cloudflare-dns-before-*.json` before the change.

Replacing that hostname's CNAME disconnects its tunnel routing. The tunnel itself is
not deleted: removing a shared tunnel could disrupt unrelated services. Locally managed
cloudflared configuration is not rewritten. Do not rerun an old `cloudflared tunnel
route dns` command for this hostname after migration.

Custom-domain verification retries while DNS/certificate activation propagates. A
failed verification exits nonzero; an uploaded Pages release alone does not count as
a completed custom-domain deployment. No paid plan is selected automatically.

## Daily Local Workflow

```sh
npm run publish:daily
```

This runs app and collector tests, collects and reviews the news locally, renders the
static paper, builds the archive, tests the bundle locally in Chromium, uploads it,
then tests both the Pages URL and the custom domain in Chromium.
Local collection still needs its existing source credentials, authenticated Codex CLI,
Python dependencies and podcast transcription cache. None of those run in Cloudflare.

### When Automated Editorial Review Is Unavailable

Codex CLI usage limits stop publication and leave the live edition unchanged. The
pipeline does not buy credits, switch to a billed API or admit unreviewed material.
A reviewer can complete the same evidence-bound process interactively:

```sh
npm run review:prepare
# Review data/editorial/review-request.json and author a review file.
npm run review:apply -- data/editorial/desk-YYYY-MM-DD.json
npm run deploy:static
```

The review file follows `ExternalReview` in
`scripts/news_collector/news_collector/pipeline/editorial.py`: request hash, reviewer,
timezone-aware review time, a decision for every pending candidate, and an edition
selection accounting for all admitted candidates, including cached decisions. Every
admission needs valid source-chunk evidence. Podcast notes must cover the beginning
and final portion of a complete transcript. Unread candidates must remain held.
Reviews expire after 24 hours; changed source packets or policy invalidate the hash.
Keep these files private in ignored `data/`, not in Git or the public bundle.
This is a manual review fallback, not an unattended replacement for available CLI
quota. The normal daily command still requires a working editorial provider.

When the new paper has already been generated and reviewed:

```sh
npm run publish:static
```

For an already built, unchanged artifact, `npm run deploy:static` uploads directly.
Rerun public verification with `npm run verify:deployed`. All commands are noninteractive
with environment credentials, so the same pipeline can be run by a trusted CI runner.
No GitHub automatic deployment or daily schedule is activated: publishing is explicitly
triggered locally, as requested. Direct Upload also supports external CI without moving
the content generation into Cloudflare; see [Cloudflare's CI guidance](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/).

## Release Contents And Verification

Only the current reviewed edition and its referenced reader assets are copied from
`out/` into `data/cloudflare-bundle/`. Existing files in that release directory preserve
previously published report links. Old unreviewed reports, screenshots, audit records,
environment files and collector state from the wider workspace are not swept into the
deployment. Unexpected files, symlinks, credentials, stale snapshots and mismatched
embedded edition data stop deployment.

Keep `data/cloudflare-published/` with the local publishing workspace to preserve historical
report links across releases. This is the last remotely verified release; an unsuccessful
staging attempt does not become the source for later archives. If moving machines, transfer that public bundle along
with the private build state through appropriate separate channels. The hard file-limit
check prevents unlimited archive growth from silently exceeding the Free plan.

The public `edition-manifest.json` contains edition date, generation time, story count
and file hashes, plus the dated edition index. Verification compares the served index and manifest with the local
release, opens every report, tests saved-state persistence and the short edition, checks
desktop/mobile overflow, checks podcast sections, tests no-JavaScript navigation and
requires a real 404 for unknown URLs. `_headers` makes HTML revalidate so a new daily
edition is not hidden by a long browser cache. There is no SPA catch-all fallback.
Archive checks follow dated edition/report/back links with and without JavaScript,
verify every retained dated report against its recorded hash, and check bundled media
bytes. Archive desktop/mobile screenshots are included in verification output.

Screenshots and verification results stay private under `data/cloudflare-verification/`.
`data/cloudflare-deployment.json` records a successful deployment and whether the custom
domain was verified. A release lock prevents concurrent uploads.

## Rollback

Use the Cloudflare Pages dashboard's deployment rollback to a previous successful
production deployment. Keep DNS pointed at Pages; normal rollback does not require a
tunnel. An emergency DNS restoration can use the saved original CNAME only if the old
tunnel and origin are actually working. A failed post-deployment verification is reported
as failure; the script does not silently claim success or change DNS back to a dead origin.
