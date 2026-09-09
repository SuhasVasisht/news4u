# Image Pipeline Verification

## Implementation

Image quality is enforced in collection before raw storage and normalization, and
before legacy publishing. Collection also refreshes the seven-day database window,
including duplicates and articles from sources skipped by their collection schedule.
Rejected images are explicitly cleared, not retained by a null-coalescing update.

Feed extraction prefers larger media content to thumbnails. Publisher metadata is
resolved and actual image files are decoded and verified with Pillow. The minimum
accepted dimensions are 400 x 200. Article URLs and publisher logos in JSON-LD are
not treated as article images.

The database stores image URLs, dimensions, check times, and original candidates for
retry. Successful checks expire after seven days; failures after six hours. Publisher
images remain remote, so subsequent blocking or deletion cannot be prevented.

The post-export enrichment job has been removed. Export verifies that every image
matches its checked database record; it does not repair or replace image URLs.

## Live Runs

Two complete executions of `npm run build:daily`:

| UTC snapshot time | Recent URLs checked | Verified | Omitted | Exported stories | Exported images |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-09-08 09:19:49 | 426 | 391 | 35 | 109 | 97 |
| 2026-09-08 09:21:34 | 441 | 406 | 35 | 109 | 97 |

The first run populated the new database quality cache without importing the old
post-export JSON cache. The second used normal cache behavior and collected further
arrivals. All 109 shared story IDs had identical image selections; no image regressed.
An independent database comparison confirmed all 97 exported image URLs and minimum
dimensions matched normalized records and quality records.

Existing source limitations remain: Guardian uses RSS fallback, GDELT is rate-limited,
Alpha Vantage can return cached responses, and X lacks an authenticated profile.
Neither run reported a collector crash.

## Regression Coverage

48 collector tests pass, including original-image selection, tiny-image rejection,
publisher-fetch fallback, cache expiry, failure retry, retention of retry candidates,
duplicate-row updates, explicit removal of bad images, structured metadata parsing,
and rejection of unverified images during export. Five browser tests and lint pass.
