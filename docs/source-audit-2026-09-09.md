# September 9 Source And Publication Audit

The corrected paper contains 24 reports. The original September 9 version is retained
as an earlier revision; September 8 remains unchanged. Read the current paper at
https://news.suhasv.com and historical editions at https://news.suhasv.com/editions/.

## What Was Fixed

- Added prior-publication checks before candidate selection, again at export, and at
  deployment. Canonical URLs include previously published coverage links; similar
  recent titles are checked conservatively. The editorial desk also compares events.
- The old September 9 paper repeated 7 of September 8's 25 stories: 35% of its own
  20-story selection. The corrected 24-story edition has zero repeated IDs or URLs.
  The history filter blocked 22 candidate records. Semantic duplicate recall cannot
  be quantified without a labeled dataset; different headlines still need desk review.
- Raised the default review budget from 3 to 8 per source/category and gave TLDR,
  Hacker News and Techmeme larger discovery budgets. Quality admission is still required.
- Preserved editorial ordering instead of re-sorting it by a quality-weighted score.
  Importance drives the condensed edition; the reader can still choose another order.
- Preserved discovery credits from raw ingestion even when normalized URLs collapse.
- Restricted daily podcasts to the latest eligible episode per show; an already-read
  episode no longer triggers an older-backlog replacement. Full transcript requirements
  remain. Today's Lenny report has 10 substantive note sections; Theo has 8.
- Added BBC Business, NPR Business, DOJ Antitrust, Al Jazeera, BBC Science, BBC Health
  and Krebs on Security. Added AI, Economy, Deals & regulation and Science & health sections.
- SEC, Federal Reserve and DOJ releases receive a seven-day consideration window,
  keeping their actual dates. No older announcement is relabeled as today's event.
- Fixed DOJ extraction to retain settlement conditions; increased SQLite write tolerance
  and enabled WAL after a concurrent image-refresh lock failure, then reran successfully.
- Alpha Vantage retains partial fresh topic results instead of discarding them when a
  later topic hits quota. Product Hunt remains disabled; additional automated stock-pick
  publishers are excluded. Vendor promotion is not automatically treated as reporting.

## Every Configured Source

Checks ran September 9, approximately 03:58-04:20 Pacific. Counts below are each
source's latest collection result and the corrected edition's publication credits.
Collection can return earlier articles. Publication credits can overlap for the same
article, and they are not independent confirmations. A working feed is not a guarantee
that its linked articles are readable or selected.

| Source | Collection status | Collected | Published |
| --- | --- | ---: | ---: |
| TechCrunch | OK | 20 | 0 |
| BBC World | OK | 26 | 2 |
| BBC Politics | OK | 30 | 0 |
| SEC press releases | OK | 25 | 1 |
| Guardian | Partial: public RSS; API rejected | 40 | 1 |
| Hacker News | OK | 20 | 2 |
| Techmeme | OK | 15 | 0 |
| arXiv cs.AI | OK | 10 | 0 |
| GDELT | Partial: some HTTP 429 responses | 10 | 0 |
| Alpha Vantage News | Cached: upstream quota | 25 | 1 |
| Alpha Vantage Movers | OK; not article content | 30 | 0 |
| TLDR Tech | OK | 13 | 3 |
| TLDR AI | OK | 17 | 1 |
| ByteByteGo | OK | 10 | 1 |
| AlphaSignal | OK | 12 | 3 |
| AP Top News | OK | 6 | 1 |
| X | Disabled | 0 | 0 |
| Product Hunt | Disabled | 0 | 0 |
| Reddit | Disabled | 0 | 0 |
| NewsAPI | OK | 10 | 0 |
| Ars Technica | OK | 12 | 0 |
| The Verge | OK | 10 | 0 |
| Simon Willison | OK | 8 | 0 |
| Interconnects | OK | 4 | 0 |
| Latent Space | OK | 4 | 0 |
| Lenny | OK | 4 | 1 |
| Dwarkesh | OK; latest interview already published | 4 | 0 |
| OpenAI News | OK | 8 | 1 |
| DeepMind | OK | 8 | 0 |
| Hugging Face | OK | 8 | 0 |
| FT Markets | OK feed; thin linked text | 12 | 0 |
| FT Technology | OK feed; thin linked text | 12 | 0 |
| Federal Reserve | OK; no important new release selected | 8 | 0 |
| MarketWatch | OK feed; mostly thin linked text | 10 | 0 |
| Anthropic News | OK; newest collected item September 1 | 6 | 0 |
| Theo video | OK; public captions | 3 | 1 |
| BBC Business | OK | 20 | 1 |
| DOJ Antitrust | OK | 10 | 1 |
| NPR Business | OK feed; inaccessible full article text | 10 | 0 |
| Al Jazeera | OK | 20 | 3 |
| BBC Science | OK | 10 | 1 |
| BBC Health | OK | 10 | 0 |
| Krebs on Security | OK | 8 | 1 |

Totals: 43 configured; 40 enabled; 37 OK, 2 partial, 1 cached, 3 disabled.
The private `data/source-audit.json` contains stored, eligible, candidate, reviewed and
published counts, decision reasons and published titles. The paper's Sources view
shows collection, review and publication counts. Zero publication is not a silent
collector failure: candidates may be repeats, thin, promotional, less relevant, or
awaiting a full evidence review. In this interactive pass, 316 candidates were screened
and 24 selected reports received substantive review; unreviewed holds have quality 0.

## Coverage And Limits

TLDR Tech contributed CPU-capacity analysis, Apple's disclosed Sonera acquisition and
IEEE Spectrum's AlphaGenome reporting. TLDR AI contributed the unfinished-codebase
essay. AlphaSignal contributed Muse, Cohere's megakernel and Suno's licensing deal.
HN contributed the quantum-lab workflow and trademark analysis. SEC and DOJ provide
primary regulatory announcements; acquisitions include Apple/Sonera and Novartis/Pfizer.
World, elections and science now have independent reporting beyond tech feeds.

CNBC RSS, FTC Competition RSS and the tested SEC EDGAR current-filings endpoint
returned HTTP 403. They were not added as supposedly working collectors, and access
controls were not bypassed. SEC press RSS is working; it is not equivalent to complete
EDGAR or M&A coverage. NPR, FT and MarketWatch need better permitted full-text access
before they can consistently supply full reports. No paid subscription was purchased.

Official source directories checked: [SEC RSS](https://www.sec.gov/about/rss-feeds),
[DOJ Antitrust feeds](https://www.justice.gov/atr/news-feeds),
[Federal Reserve feeds](https://www.federalreserve.gov/feeds/feeds.htm), and
[FTC RSS](https://www.ftc.gov/stay-connected/rss).

Codex CLI remains usage-limited. This edition used the existing validated interactive
review-file workflow, not an unreviewed fallback. Until automated review is available,
daily publication needs the same review-file step; the pipeline stops rather than
publishing arbitrary candidates. No finite feed set guarantees complete world coverage.

## Repeatable Workflow

Run `npm run publish:daily` when automated editorial review is available. Otherwise:

```sh
npm run review:prepare
# Complete evidence-bound review of data/editorial/review-request.json.
npm run review:apply -- data/editorial/your-reviewed-decisions.json
npm run deploy:static
```

Only intentional same-day corrections use `npm run deploy:static -- --revise-today`.
Every deployment runs local and public Chromium checks, retains dated editions and
prior revisions, and backs up the public bundle outside Git. Do not delete
`data/cloudflare-published`: it supplies both the archive and publication history.

## Verification

Next production build, TypeScript and lint passed; 34 app tests, 81 collector tests
and 9 Playwright tests passed. The deployment verifier checked all 24 current reports,
their notes, source counts, image dimensions, short edition, local save persistence,
report navigation, no-JavaScript navigation, private-path 404s, and every historical
report hash, including the earlier September 9 revision. Desktop and mobile views
were inspected on the actual public domain. Of 23 pipeline-approved remote images,
22 rendered in the browser; the unavailable image was omitted rather than showing a
broken or undersized image. Remote publisher availability is not guaranteed.
