# News Sources And Deduplication Audit

Reviewed September 8, 2026, approximately 00:35-01:05 America/Los_Angeles. These are observed local collection results, not guarantees of continued provider availability. No paid subscription was purchased, no login challenge was bypassed, and Reddit stayed disabled.

## Summary

The current edition is real collected data, not the design artifact's sample stories. The final seven-day analysis covers 398 eligible normalized rows, 395 distinct canonical article URLs, and 382 story clusters. The finite reader selects 106 stories using sector/publisher caps; 102 fall in its 48-hour Today window and four in Catch up. Four selected items have September 8 Pacific timestamps: one BBC politics article and three Product Hunt launches. Most current news is dated September 7, as expected just after midnight Pacific.

The UI and static build are usable. Source coverage is improved but not completely healthy: Guardian requires an RSS fallback, GDELT is partially rate-limited, Alpha Vantage is serving cached results, and X has no session. Do not label this a fully healthy source pipeline yet.

## Existing Sources

Counts below are eligible normalized rows from the last seven days, before story clustering and edition caps. The first full collection and later targeted retries are both included in the review.

| Configured source | Observed result | Seven-day rows | Notes |
| --- | --- | ---: | --- |
| TechCrunch | Working | 20 | Current RSS items, newest September 7 Pacific |
| BBC World | Working | 27 | Current RSS |
| BBC Politics | Working | 44 | Includes the September 8 00:04 Pacific article |
| SEC press releases | Working, quiet | 5 | Latest September 3; working endpoint does not imply a release every day |
| Guardian | Working via fallback | 38 | API returned 401; public section RSS successfully restores coverage. Replace the rejected API key if API fields are needed |
| Hacker News | Working | 22 | Discovery timestamps, not necessarily original article publication times |
| Techmeme | Working | 15 | Includes outlet links; aggregation timestamps and long editorial headlines |
| arXiv cs.AI | Working | 10 | Newest retrieved submission September 4; RSS/API fallback can lag the latest announcement cycle |
| GDELT | Partial | 20 | Two queries contributed results; another was rate-limited. Successful results are now retained |
| Alpha Vantage news | Cached on repeat | 126 | First run returned 150 rows, 24 rejected as duplicate fingerprints; repeat requests fell back to 25 cached items |
| Alpha Vantage movers | Cached; excluded from news | 0 dated | Returns market rows with a shared homepage URL and missing parsed timestamps. Not safe to present as today's article feed |
| TLDR Tech | Working after fix | 10 | Previously only one item was parsed; all relevant hydration arrays are now processed |
| TLDR AI | Working after fix | 10 | Same parser fix |
| AP top news | Working in this run | 6 | Six article pages collected. This remains an unofficial scraper, not a licensed, guaranteed wire feed |
| Product Hunt | Working | 39 | Launch data, not general reporting. Capped and down-ranked to avoid overwhelming tech leads |
| NewsAPI | Working, limited sample | 6 | Existing relevance filters leave few items; API coverage is not equivalent to complete outlet coverage |
| X | Unavailable | 0 | No persistent X browser profile exists; recommendations below |
| Reddit | Disabled | 0 | Left disabled as requested |

### Repairs Made

- Guardian falls back to public section RSS when the API rejects credentials.
- TLDR decodes the structured Next.js flight payload and collects all matching arrays. Nested arrays and Unicode have regression coverage. Both newsletters increased from one to ten retrieved stories in the live retest.
- GDELT requests English-language results in a 48-hour window, retries network disconnects, preserves successful queries, and reports partial status. Earlier code discarded all prior results when a later query disconnected.
- Cached results are labeled `cached`, rather than counted as a fresh successful upstream fetch. Cache timestamps are no longer renewed just because a cache was replayed.
- Collector HTTP errors no longer include query strings that could contain API keys.
- Classification uses word tokens for finance terms, avoiding substring matches such as `market` inside `marketing`.
- Fresh snapshot selection excludes undated items, future timestamps, and items older than seven days. It does not treat old market movers as current news.

## How Much Duplication Is There?

There are three different measurements. They must not be combined into one misleading percentage.

### 1. Repeat Fetches Rejected At Ingestion

The first full live collection returned 393 raw observations and inserted 365 normalized rows: **28 rejected, or 7.1%**. Of these rejections, 24 were from overlapping Alpha Vantage news queries, two from movers, and two from NewsAPI. The local database already contained earlier historical collections, so this is not a pristine new-database benchmark.

A second full collection shortly afterward returned 292 observations and inserted 60: **232 rejected, or 79.5%**. Most were expected re-fetches from the first run; new Guardian fallback results accounted for 38 new rows. This demonstrates repeat-ingestion suppression, not 79.5% duplicate events in a reader's news feed. Different sources were cached or skipped between runs, so these are not directly comparable recall measurements.

### 2. Duplicate Articles And Syndication In The Recent Window

The final seven-day window contains:

| Stage | Count |
| --- | ---: |
| Eligible normalized observations | 398 |
| Distinct canonical article URLs | 395 |
| Story clusters after current URL/title matching | 382 |
| Rows collapsed by clustering | 16 / 398 = **4.0%** |
| Selected for the finite edition | 106 |

Only three recent rows repeat a canonical URL. The rest of the 16 collapsed observations involve title-level grouping across URLs. The drop from 382 to 106 is **edition selection**, not deduplication.

Observed clusters include syndicated coverage of Novartis/Pfizer's Minipress transaction, SLB's data-center investment, GameStop earnings, and German regional elections. Multiple linked reports are preserved in the reader. Multiple URLs or publishers do not prove independent reporting; syndicated copies should not be marketed as independent confirmations.

The historical raw table contains many repeated fetches, including 976 BBC Politics observations over 124 distinct URLs. Alpha Vantage movers has 495 observations using one homepage URL: that does **not** mean 494 duplicate articles. It illustrates why homepage URLs cannot serve as the identity for structured market records.

### 3. Same Event, Different Headlines: Still Under-Merged

Current clustering uses canonical URLs, whole-title fuzzy similarity, and extracted entity overlap. It is conservative and is not a semantic event model. The inspection found obvious residual candidate groups, including:

- Mistral's funding announcement surfaced via Hacker News and a substantially longer Techmeme headline.
- BBC and Techmeme coverage of Grindr's settlement concerning HIV-status data sharing.
- German election reports with different sentence structures remaining in separate clusters.

The automated residual-pair report also flags formulaic investment headlines about **different companies**. Those should not be merged merely because their titles look alike. I have not claimed a precision/recall score: there is no manually labeled benchmark yet.

### Recommended Next Dedupe Work

1. Separate article identity from event identity. Persist canonical-URL aliases and collector provenance even when an incoming fingerprint is rejected.
2. Maintain stable event IDs over time. Current snapshot IDs derive from a cluster's URLs; a changed cluster membership can change an ID. Browser-retained saved excerpts mitigate loss of saved reading material, but an alias table is needed for durable account migration.
3. Candidate-match within a bounded time window using entities, normalized numbers/currencies, and action terms; rerank with embeddings or a small semantic classifier only for plausible pairs.
4. Require agreement on the subject and event; guard against distinct companies, contradictory facts, different product versions, and recurring earnings dates.
5. Label 100-200 candidate pairs from real editions, including hard negatives, before loosening thresholds. Measure false merges separately from missed duplicates.
6. Count independent reporting separately from syndication and discovery feeds.

The cross-run clustering bug has already been fixed: new arrivals are now compared with recent stored items, not only with other arrivals from the same run. Timestamp comparisons use SQLite date functions instead of lexicographic comparisons of mixed timestamp formats. A 72-hour guard prevents similar recurring headlines from different weeks merging; identical article URLs still group together.

## Getting X/Twitter Posts

The existing collector relies on a logged-in browser profile and currently produces zero posts. Even with a profile, its daily configuration rotates through only five of ten accounts and takes at most two posts each, with a 24-hour lookback. At one run per day, that can leave gaps for every other account. It also uses the first rendered line as a headline, which may be an account label rather than the actual post text.

**Recommended path:** an opt-in official X API collector, not browser automation as the critical daily dependency. Use an allowlist of company/researcher accounts, incremental IDs, bounded pagination, and deduplication by post ID. Cache user IDs; keep author, publication time, original post URL, referenced posts, and expanded outbound URLs. Expand an outbound article into the matching news event while retaining the post as an attributed discovery/source item. A linked post without independently reported facts should not inflate confirmation counts.

The [official recent-search endpoint](https://docs.x.com/x-api/posts/search-recent-posts) can support account-filtered searches. A combined query such as `(from:OpenAI OR from:AnthropicAI OR from:GoogleDeepMind) -is:retweet` is preferable to unbounded keyword searches for this use case. Persist checkpoints only after a successful completed retrieval and provide overlap after missed daily runs.

The [current official pricing page](https://docs.x.com/x-api/getting-started/pricing) lists $0.005 per post read and $0.010 per user read, with prepaid credits and spending limits. An illustrative 100 new posts/day is about **$15/month in post reads**, excluding user lookups and other billable resources. Confirm rates and set a hard spending limit in the developer console before enabling collection. No X API implementation was enabled and no credits were purchased in this task.

A static snapshot needs special care: follow [X display requirements](https://docs.x.com/developer-terms/display-requirements) and [developer policy](https://docs.x.com/developer-terms/policy), including attribution and handling deleted/changed posts. A once-daily immutable archive cannot guarantee timely removals; consider storing post IDs/links and using official embeds, or adding a compliance refresh/removal step. Do not export private messages, cookies, browser profiles, or bearer tokens.

## Important Missing Sources

The largest gap is direct coverage from primary technology sources and a few major specialist outlets. Broad aggregators do not replace those feeds.

The following public endpoints were requested directly during this audit and returned HTTP 200 with parseable entries. They are recommendations, **not silently enabled additions**:

| Source | Verified feed | Observed entries | Why add it |
| --- | --- | ---: | --- |
| Ars Technica | `https://feeds.arstechnica.com/arstechnica/index` | 20 | Deeper technical reporting; see its [official feed directory](https://arstechnica.com/rss-feeds/) |
| The Verge | `https://www.theverge.com/rss/index.xml` | 10 | Major consumer-tech and platform coverage |
| OpenAI | `https://openai.com/news/rss.xml` | 1,173 | Direct announcements; enforce freshness and per-run caps before fetching article pages |
| Cloudflare | `https://blog.cloudflare.com/rss/` | 20 | Infrastructure, security, and developer changes |
| GitHub | `https://github.blog/feed/` | 10 | Developer platform updates |
| NVIDIA | `https://blogs.nvidia.com/feed/` | 18 | Compute and hardware announcements |

Also add a monitored [Anthropic newsroom](https://www.anthropic.com/news) source; a first-party RSS endpoint was not established in this audit. For wire coverage, assess a licensed Reuters/AP offering if comprehensive, dependable world/business news is required; do not assume an old public Reuters RSS endpoint is usable. Label vendor announcements as primary/vendor sources, not independent journalism.

Priority order: Ars + The Verge; direct AI/developer announcements; official X allowlist; licensed wire coverage if required. Reddit can remain optional.

## Static Build Review And Remaining Gates

- Real September 8 build, with source timestamps retained and April-era data excluded.
- No dummy headlines, invented article bodies, or design-study sources in the exported edition.
- Neutral Shared Spreads, native single-page scrolling, mobile layout checks, working search/ranking/save/archive/reader, no-JavaScript reading, and offline browser interactions verified.
- Some publisher images are blocked or invalid; they are omitted on load failure. Low-resolution thumbnails are constrained rather than enlarged. Photos are still remote, not guaranteed offline assets.
- Guardian API key replacement, upstream quotas, and X credentials remain external prerequisites. Cache availability is not fresh-source health.
- Public redistribution/imagery permissions and X display/removal compliance need review before public deployment.
- The new reader is browser-local and snapshot-driven. Historical Postgres account state is retained in the database but is not yet migrated into the new reader; see [migration boundary](static-edition.md#state-and-migration-boundary).
- The static Docker configuration validates, but no production rollout or overnight cron execution was performed.
