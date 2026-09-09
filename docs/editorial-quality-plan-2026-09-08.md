# Editorial Quality And Source Plan

Research and implementation proposal, September 8, 2026. No subscriptions,
paid API access, source configuration, or ranking behavior changed by this review.

## What Is Wrong Today

The inspected edition contains 109 stories, including three Product Hunt listings
whose summaries are product taglines. Five MarketBeat stories and three MarketScreener
stories are present; several routine holdings/rating alerts rank beside substantive
reporting. These are not necessarily paid ads, but launch and promotional material
should not be presented as independently reported news.

The code explains the problem:

- pipeline/score.py primarily rewards freshness, configured collector trust, ticker
  presence, and confirmation counts. It does not assess article evidence or substance.
- pipeline/dedupe.py counts clustered rows as confirmations, not independently
  reported sources. The same article found through multiple collectors is not
  independent corroboration.
- jobs/export_edition.py subtracts points for Product Hunt and some stock-alert
  patterns but has no minimum editorial admission threshold.
- Publisher caps permit weaker material through; they are not a quality gate.
- RSSCollector often uses a summary as text. A model must know whether it has read
  actual article content, a feed excerpt, or only a title.

## Source Shortlist

The following endpoints were fetched directly and parsed successfully as RSS/Atom
during this review. Availability does not imply redistribution rights or editorial
approval of every entry.

| Source | Feed | Intended role |
| --- | --- | --- |
| Lenny | https://www.lennysnewsletter.com/feed | Product/building interviews and analysis |
| Dwarkesh | https://www.dwarkesh.com/feed | AI/research interviews and long-form analysis |
| Ars Technica | https://feeds.arstechnica.com/arstechnica/index | Technical reporting |
| The Verge | https://www.theverge.com/rss/index.xml | Technology/business reporting; exclude shopping deals |
| Simon Willison | https://simonwillison.net/atom/everything/ | Hands-on AI tooling and practitioner analysis |
| Interconnects | https://www.interconnects.ai/feed | Model research and open-model analysis |
| Latent Space | https://www.latent.space/feed | AI engineering interviews and analysis |
| OpenAI | https://openai.com/news/rss.xml | Primary announcements, not independent evaluation |
| Google DeepMind | https://deepmind.google/blog/rss.xml | Primary research and product announcements |
| Hugging Face | https://huggingface.co/blog/feed.xml | Open-model research and engineering |
| Financial Times technology | https://www.ft.com/technology?format=rss | Technology business reporting |
| Financial Times markets | https://www.ft.com/markets?format=rss | Markets reporting |
| Federal Reserve | https://www.federalreserve.gov/feeds/press_all.xml | Primary policy announcements; filter routine administration |
| MarketWatch | https://feeds.content.dowjones.io/public/rss/mw_topstories | Secondary candidate; exclude advice/clickbait irrelevant to daily news |

The BLS and CNBC endpoints tested returned HTTP 403 from this environment. Do not
call those integrations working. Anthropic's [newsroom](https://www.anthropic.com/news)
is another primary-source candidate but requires a separately verified ingestion path.
Reuters/Bloomberg are candidates for licensed access; existing occasional aggregator
links are not equivalent to direct, comprehensive coverage. FT feed availability
does not grant access to or permission to reproduce paywalled article bodies.

Lenny's tested feed contained 20 entries, ten with audio enclosures; Dwarkesh's
contained 20 entries, fourteen with audio. Both exposed content fields, but completeness
must be checked per entry. Add enclosure, duration, transcript availability, and
content completeness to ingestion. Strip sponsor blocks before summarizing. Do not
claim to summarize an entire episode from a short description.

Use a separate 30-day, unseen-only window for interviews/essays, with original dates.
The current 48-hour Today and seven-day export windows would hide slower publications:
Interconnects' latest returned entry was August 17, and Dwarkesh's September 1.
Do not relabel older interviews as breaking news.

## Theo And Kun

The account shortlist is @theo and user-specified @kunchenguid. Theo's
[official site](https://t3.gg/) links to @theo and YouTube @t3dotgg.
The Kun X page could not be read directly in this environment; no claim is made
about its current contents or an alternative handle.

Prefer the official [user-post timeline API](https://docs.x.com/x-api/users/get-posts).
Resolve handles to stable user IDs, store a per-account cursor, page through new
posts, and advance the cursor only after successful persistence. Exclude reposts
and conversational replies from primary candidates, while recovering relevant
thread context. Preserve original URLs, authorship, timestamps, disclosures and
referenced links. Group commentary with its underlying story instead of counting
it as another independent news report.

The existing browser-profile X collector lacks authenticated access and neither
requested account is in its configuration. Adding handles alone will not fix access.
Avoid depending on unofficial mirror scraping for the daily edition.

[X pricing](https://docs.x.com/x-api/getting-started/pricing) currently lists $0.005
per post read. An illustrative 40 new posts/day across the two accounts is $6 per
30-day month for post reads alone, excluding lookups and other billable resources.
Use a hard spending cap and verify console prices before enabling. Retrieval cost
is incurred before editorial rejection; rejected posts are not free.

## Admission Before Ranking

Proposed pipeline:

Collect -> extract content -> validate images -> deduplicate -> deterministic
exclusions -> editorial review -> validate decisions -> assemble edition -> static HTML.

Product Hunt should remain an optional discovery inbox, not an automatic paper
source. A genuinely consequential launch can graduate with substantive evidence.
Also reject explicit sponsorships, affiliate deal lists, thin SEO rewrites, repeated
routine stock-rating/holding notices and contextless social posts.

The editorial review should classify each item as reporting, analysis, interview,
primary announcement, launch promotion, or social commentary. Keep quality, personal
relevance, importance, and freshness separate. Primary announcements and expert
opinions are useful but should retain those labels and attribution.

Suggested initial quality rubric: evidence/provenance 30%, substantive new information
25%, depth/context 20%, specificity 15%, and transparency/disclosures 10%.
These are tunable editorial judgments, not objective truth or calibrated probabilities.
Rank admitted items by quality, topic relevance and real-world significance, with
freshness as a secondary factor. Do not reward a ticker alone. Count independent
originating reports, not aggregator rediscoveries or syndicated copies.

Start with roughly 20-35 admitted stories and a five-to-eight-item short edition,
not a quota that must be filled. Put interviews and practitioner perspectives into
clearly labeled reading/listening groups. On quiet days publish less.

## Codex Sanity Pass

The installed CLI supports codex exec, --sandbox read-only, --ephemeral,
--output-schema and --output-last-message. These capabilities are documented in
[official non-interactive guidance](https://learn.chatgpt.com/docs/non-interactive-mode).

Implement a separate editorial job between collection and export. Give it a bounded
candidate packet containing stable IDs, actual extracted content/excerpts, publication
dates, provenance, source type, disclosures, completeness and duplicate groups.
Use batches for initial review and a final edition-wide selection pass.

Require schema-validated JSON with: candidate ID, admit/hold/reject, content type,
quality dimensions, importance, relevance, reason, evidence references, duplicate
group and confidence. A publishable decision must reference evidence in the supplied
packet; titles alone must not produce high-confidence judgments.

Keep review isolated from credentials, source configuration, shell tools, publication
rights and arbitrary network access. Treat all article/post text as untrusted data,
including instructions embedded in it. Read-only filesystem access alone does not
prevent data exfiltration: restrict mounted files, environment and network/tools.
The model returns decisions; ordinary validated code performs publication.

Persist decisions keyed by content hash, policy version and model configuration.
Cache unchanged content, cap runtime/input/output costs, validate IDs and timestamps,
and invalidate decisions when source text changes. Output-schema compliance does
not prove factual accuracy.

Initially run in shadow mode: compare the proposed edition with today's edition,
review a 50-100-item human-labeled sample including rejected items, and measure
promotional leakage, duplicate leakage, missed major stories and acceptance by type.
Your keep/reject feedback should refine the policy instead of silently promoting
entire domains.

On timeout, malformed output or inadequate evidence, hold affected items. If the
edition cannot meet the review gate, retain the last approved edition with its
original date and an operational alert. Never silently publish unreviewed inventory.

For a local scheduled job, saved CLI authentication can be reused on the trusted
machine. A hosted worker needs its own secure authentication setup; neither this
chat nor a Codex subscription automatically installs or schedules it there.
The current worker does not yet contain this editorial job. No paid model run or
scheduling change was made during this research.

## Suggested Rollout

1. Quarantine Product Hunt and routine stock alerts; repair independence counting.
2. Add the verified priority feeds with bounded per-source item limits and type labels.
3. Add long-form/podcast extraction, sponsor removal and honest completeness metadata.
4. Run the Codex editorial job in shadow mode and calibrate on your feedback.
5. Enable the admission gate, then add the two X accounts with authenticated access
   and a spending limit.
