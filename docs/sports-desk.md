# Daily sports back page

The daily build now adds a compact **Sports in brief** section after the main
newspaper. It has NFL, Soccer and NBA columns, plus up to two **Elsewhere in sport**
items for major results outside those sports. The section uses normal page scrolling,
not independently scrolling panels. Every selected article has a dedicated report
page and the existing save/read/archive controls.

## Sources tested

All eight RSS feeds returned HTTP 200 and parseable entries in the September 9,
2026 evening run:

| Feed | URL | Entries |
| --- | --- | ---: |
| ESPN NFL | https://www.espn.com/espn/rss/nfl/news | 26 |
| Guardian NFL | https://www.theguardian.com/sport/nfl/rss | 20 |
| ESPN NBA | https://www.espn.com/espn/rss/nba/news | 18 |
| Guardian NBA | https://www.theguardian.com/sport/nba/rss | 20 |
| BBC Football | https://feeds.bbci.co.uk/sport/football/rss.xml | 80 |
| ESPN Soccer | https://www.espn.com/espn/rss/soccer/news | 18 |
| Guardian Football | https://www.theguardian.com/football/rss | 58 |
| BBC Sport | https://feeds.bbci.co.uk/sport/rss.xml | 71 |

Feed health is distinct from editorial selection. Guardian NBA worked but had no
eligible article within 48 hours. The final reviewed selection contained seven
articles, not one article from every feed. ESPN describes its feed format in its
[RSS FAQ](https://www.espn.com/espn/news/story?page=rssinfo); BBC documents its feeds
in its [RSS guide](https://www.bbc.co.uk/sport/articles/cqllxj2n4kyo).

ESPN's public JSON endpoints supply scores and standings, independently of article
summaries. Nine leagues passed both endpoint checks (18 checks total): NFL, NBA,
Champions League, Premier League, La Liga, Bundesliga, Serie A, MLS and NWSL.

```text
https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard
https://site.api.espn.com/apis/v2/sports/{sport}/{league}/standings
```

These are public website endpoints, not a contracted, supported API with an uptime
guarantee. They currently require no subscription or API key. The integration uses
the standard HTTP client user-agent: ESPN rejected the custom crawler user-agent
in the initial test. It does not use authentication bypasses or cached historical
results to disguise failures. Endpoint failures are visible in Sources and the
affected scoreboard/table; an empty successful schedule says no games, not failure.

## Scope and quality

- Article limits: two NFL, three Soccer, two NBA and two elsewhere. Limits are
  ceilings, not quotas. This allowance does not consume the main paper's 28 slots.
- Full accessible source text is evidence-reviewed. Minimum evidence, citation,
  completeness and quality gates are shared with the main editorial pipeline.
- Summaries target 40-75 words, with a hard 95-word cap, at most two short points
  and no deep-dive sections. Betting, fantasy, predictions and routine previews
  are filtered or held. Prior-edition URL/title checks and editorial event-level
  review prevent republishing yesterday's articles.
- Scores cover the previous and next 24 hours, in a timestamped static snapshot.
  The compact list favors in-progress games, recent finals and upcoming fixtures;
  it shows at most six games per competition and links to full scoreboards.
- Scheduled games never receive a fabricated 0-0 score. In-progress scores are
  marked as such at collection time; future-dated played games are rejected.
- Tables retain the provider's season label and are sorted by supplied rank,
  not the API's arbitrary array order. The NBA endpoint currently returns 2025-26
  standings while its schedule is in the 2026-27 preseason; these labels remain
  separate. No games in the NBA window is expected, not a broken source.
- Tables show up to three teams per group, with links to full standings. Zero-game
  tables are described as not yet started. This is not a full playoff bracket or
  exhaustive coverage of every soccer competition.
- Score/table snapshots may recur across editions because they describe current
  state. Articles about the same completed event should not recur the following day.

## Pipeline

Configuration: `scripts/news_collector/config/sports.yaml`.
Review policy: `scripts/news_collector/config/sports-prompt.md`.
Local-only evidence and reviewed snapshots: `data/sports/` (ignored by Git).

`npm run build:daily` now automatically collects and reviews sports after the main
editorial pass and before export. `npm run publish:daily` includes this step before
Cloudflare deployment. The existing CLI review must be available and within quota;
failure stops publication, rather than putting unreviewed articles into the paper.

For an interactive evidence review, including when CLI review is unavailable:

```sh
npm run sports:prepare
# Review data/sports/review-request.json and produce an evidence-bound review JSON.
npm run sports:apply -- /absolute/path/to/review.json
npm run deploy:static -- --revise-today
```

The review uses the same ExternalReview schema as the main desk, binds to the
request hash, and applies only to the exact immutable source/score snapshot that
was reviewed. Requests expire after six hours or at the next Pacific date. Export
and static build reject yesterday's sports snapshot. Applying a sports review
re-exports the existing, still-current main editorial review; it does not silently
collect or approve new main-paper articles. If that main review has expired, refresh
the main desk first. No generated HTML is manually patched.

The September 9 rollout retained the 27 reviewed main stories and added seven
sports briefs. Its sports collection cutoff was 20:52 PDT. Earlier editions remain
in the static archive, with no new credentials, databases or runtime data in Git.

## Verified release

Published to https://news.suhasv.com/#sector-sports and verified on the actual
domain at 21:00 PDT, September 9. Pages deployment:
https://8648371f.news4u-suhasv.pages.dev.

The release passed local and hosted browser verification, all 34 dedicated report
pages, exact displayed score comparisons, archive/revision checks, no-JavaScript
reading and desktop/390px/320px overflow checks. Actual-domain screenshots were
visually inspected. All five static Playwright tests, 36 application tests and
100 collector tests passed; TypeScript and lint checks passed. Runtime verification
and screenshots are in `data/cloudflare-verification/news.suhasv.com/` (not Git).
