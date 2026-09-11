# Coverage audit: September 10, 2026

## Scope

Independent sampled comparison of the September 10 paper, generated at **15:40 UTC / 08:40 PDT**, with reporting available that evening. Inspected the edition, editorial packets and decisions, source-health records, stored Techmeme HTML, and publication history. This is not an exhaustive news audit. No production collection, editorial application, or news publication was performed. Today's stories remain unchanged.

## Desk findings

- **AI / policy: missing before cutoff.** [Axios reported the Senate inquiry into OpenAI](https://www.axios.com/2026/09/10/openai-hugging-face-senate-investigation-hawley) at 09:00 UTC. Techmeme discovered it, but the collector selected the publisher homepage instead of the headline link. Packet `5ec1142460efc4b0da48` consequently had only 22 words and was held. The parser is fixed; the correct article still returns HTTP 403 here. This is a collection bug plus an access blocker, not simply a missing source subscription.
- **AI / science: ranking needs review.** [OpenAI's September 8 research announcement](https://openai.com/index/navier-stokes-solution/) was outside the primary source's 48-hour window. However, a 1,030-word Simon Willison discussion and a 3,584-word Latent Space discussion reached the September 10 desk. Both received the generic zero-score hold described below. No matching title appeared in the supplied 130-entry publication history. This is an older catch-up candidate, not September 10 breaking news. A report must attribute the research claims and preserve verification and priority caveats, not treat a company announcement as independently settled mathematics.
- **Technology: covered sample.** The paper includes [React 19.3](https://react.dev/blog/2026/09/09/react-19-3), including stable View Transitions and Fragment Refs, and links to the primary source. Its original date is September 9; a later discovery timestamp does not make the release a new event.
- **Economy / markets: covered major event.** The paper's ECB lead includes rate increases, oil, gas and borrowing costs, consistent with the [ECB policy statement](https://www.ecb.europa.eu/press/press_conference/monetary-policy-statement/2026/html/ecb.is260910~6a45359cfc.en.html). A readable BBC oil/borrowing-cost candidate was held, but substantial overlapping coverage exists in the lead. An absent Markets heading alone does not prove missing information.
- **US economy: source gap to consider.** [AP's weekly claims report](https://apnews.com/article/54d2e328e44f3cbe851a51426746e077) appeared at 12:38 UTC, before cutoff. No matching claims candidate was found in the prepared packets. AP collection failed with HTTP 403; retained AP candidates dated from September 8. Direct labor-statistics ingestion is also absent. This does not mean every weekly claims release needs a standalone article.
- **World: covered sample.** The [Philippines ferry disaster](https://www.theguardian.com/world/2026/sep/10/all) appears in the morning paper. Other international stories cover Mocha and Sudan. This sampled comparison does not establish comprehensive world coverage.
- **AI after cutoff: not a demonstrated morning miss.** [Anthropic's new threat report](https://www.anthropic.com/news) was covered by [AP at 20:50 UTC](https://apnews.com/article/00266dca90e4f8853f669648998d3bda), five hours after generation. Anthropic is already configured. Its date-only newsroom listing is insufficient to prove availability before the morning cutoff.
- **Reading / listening: not an empty-source problem.** Dwarkesh's essay and ByteByteGo analysis are present. Theo was held with an event-specific prior-coverage rationale. Lenny's roundup was held because it was not a new complete episode. Those are different from a broken collector; this audit did not independently listen to full audio.
- **Sports:** no independent rescoring of games in this audit. The existing result snapshot has its own collection timestamp. Earlier sports carryover and deduplication changes were preserved, not reviewed or overwritten here.

## Ranking confidence

The 331-packet main review assigned nonzero quality and importance only to the 24 admitted stories. **214 other candidates share exactly the same generic lower-incremental-value hold reason.** Some exclusions are sensible, but that record does not substantiate individual ranking decisions. There are also 54 insufficient-evidence holds and nine truncated-packet holds, which must not be promoted to fill space.

The practical diagnosis is a demonstrated URL bug, real access restrictions, and an insufficiently auditable first-stage ranking pass, not simply too few outlets.

## Repeatable fixes

1. Techmeme now chooses the main styled headline before thumbnail/fallback links. Publisher homepages, internal permalinks and non-HTTP links are ignored. Publisher attribution is separate. Tests cover text-only stories, favicon links, unrelated thumbnails and additional-coverage links.
2. Editorial instructions now distinguish evidence/relevance admission from final selection. Substantive reporting needs scoring and specific reasons instead of being zeroed after a paper is preselected.
3. A new-review gate rejects four or more identical, zero-score priority dismissals on readable, nontruncated 200+ word packets. It does not reject repeated ad/paywall holds, short excerpts, incomplete packets or explicit duplicate references. New review caches are written only after the complete pass clears the gate. This is a narrow safeguard, not a guarantee of correct ranking. Existing published exports are not retroactively invalidated. A read-only replay correctly rejects the current blanket decisions.
4. Added [ECB's official RSS](https://www.ecb.europa.eu/rss/press.html) through the existing collector as `announcement` / `Economy`, with eight fetched entries and four editorial candidates maximum. Normal event deduplication remains required: the primary release and newspaper coverage must not become redundant stories.

## Source probes

- ECB RSS: HTTP 200, 15 dated entries. The September 10 policy-decision page yielded 550 words; its press-conference page yielded 5,758. Both returned HTTP 200.
- Corrected Axios article: HTTP 403. The fixed discovery link does not guarantee usable full text. An accessible alternate account or authorized source is still needed.
- AP source health: HTTP 403 and zero new items. Stored older records are not evidence of current collection health.
- FT and MarketWatch: feeds worked, but sampled financial articles supplied only 15-25 words. Those teasers are not adequate evidence.
- CNBC: the alternate economy feed returned HTTP 200 and 30 entries, but five linked articles all returned HTTP 403. Its usual feed URL also returned HTTP 403. Not added as a working full-text source.
- BLS latest feed and the tested DOL RSS URL returned HTTP 403. Neither was enabled speculatively. Start a future labor/inflation integration from the [official BLS feed directory](https://www.bls.gov/feed/), with fresh access tests.
- Guardian API credentials were rejected, but public RSS fallback collected current stories. GDELT and Alpha Vantage reported rate-limit degradation.
- TLDR email contributed five published reports. AlphaSignal email and web contributed one each. TLDR email remains partial because some linked articles are unavailable.

The next content run must prepare fresh evidence and a new review, not reuse today's manual selection file. Revisit important held evidence and distinguish before-cutoff omissions, post-cutoff events, prior coverage, access failures, candidate budgets and genuine ranking exclusions. Nothing from this audit was inserted directly into a newspaper snapshot.

## Verification

Collector suite: **115 tests passed**, including new URL, ranking and ECB tests. Live probes were read-only, with no paid services or production writes. Stored Techmeme HTML reproduced the homepage bug; the fixed parser returned the correct dated article URL and publisher.
