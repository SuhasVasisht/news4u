# Daily editorial quality

## Publication path

`npm run build:daily` collects sources, prepares full source evidence, reviews
candidates, selects the edition, runs independent web discovery and a separate
final factual/coverage audit, refreshes sports, and exports the static bundle.
`npm run deploy:static` publishes a successful bundle. Same-day content revisions
use `--revise-today`; neither command should edit an exported story by hand.

The live edition is retained when review or export fails. A draft in
`data/editorial/latest.json` is not proof of successful publication.

## Reader priorities

`scripts/news_collector/config/editorial-profile.json` is the versioned editorial
contract: technology and AI, finance/economy and deals/regulation, consequential
world/policy/science news, substantive followed voices, and concise sports.
Evidence quality is an admission floor, separate from importance and relevance.
No outlet is entitled to publication and no sector quota justifies weak filler.
Changes to the profile invalidate candidate-review caches.
Validated candidate batches are checkpointed atomically so a later failure can be
resumed. Each batch and the complete pass still undergo ranking validation. One
bounded retry is allowed for structurally invalid reviewer output; failing a
retry stops the build. Private raw responses are retained under
`data/editorial/responses/` for diagnosis, not publication.

The final selection compares events against published history, not simply URLs
or refreshed collection timestamps. Reports on the same event are consolidated
editorially. Repeat coverage requires a specific, evidence-backed material update.
Older essays and podcasts retain their true publication dates and cannot be
recycled as new daily content.

## Independent review

Discovery receives only the profile and edition cutoff, never the selected draft.
It searches and opens public sources, records queries, dated article URLs and
findings, and produces a sampled coverage benchmark. Sources published after the
cutoff cannot be used to manufacture a missing event. Discovery is not exhaustive.

The final reviewer receives selected articles and full source packets, publication
history, that checklist, and a metadata index of rejected candidates. It checks
published claims against cited evidence, distinguishes allegations and company
claims from established facts, and traces omissions to discovery, extraction,
deduplication or selection. Must-cover omissions, unsupported or uncertain claims,
promotional stories, unexplained repeat events and incomplete checks block export.

The audit is hash-bound to the evidence, article text, selection, candidate index,
history and checklist. It cannot be reused after those inputs change. Structural
tests verify this contract; they do not prove that a model's factual judgment is
correct. Full transcript evidence and broad notes coverage remain prerequisites
for podcast summaries. A YouTube description is not a transcript.

## Private artifacts and metrics

All generated files remain outside version control:

- `data/editorial/review-request.json`: candidates and evidence to review.
- `data/editorial/checklist.json`: independent research record.
- `data/editorial/quality-review-request.json`: hash-bound final review input.
- `data/editorial/quality-review-response.json`: reviewer output, including failed checks.
- `data/editorial/quality-audit.json`: latest final audit and blockers.
- `data/quality/history/`: dated audit metrics, including selected/reviewed stories,
  covered/missing sampled events, omission causes, duplicate event groups,
  unresolved claims, promotional stories and material updates.

Coverage rates describe the sampled checklist, not all world news. URL rediscovery
counts are not semantic deduplication recall. Compare like-for-like metrics and
inspect omitted-event reasons before concluding that quality improved.

For a separate recheck of an existing draft:

```sh
cd scripts/news_collector
.venv/bin/python -m news_collector.jobs.quality_review
```

An externally researched checklist or final audit can be supplied with
`--checklist-file` or `--audit-file`. External reviews must satisfy the same schema,
freshness and input-hash checks. Do not hand-edit the paper to bypass a failed gate.

## Source limitations

Source availability and editorial quality are different checks. A successful feed
request can still yield only teasers, ads or inaccessible full articles.
The source-health record must preserve failures rather than reporting old cached
items as current success. Newsletter IMAP authentication failures require a valid
mailbox/app password; no ranking change can recover inaccessible mail. Official
YouTube RSS gets bounded retries for intermittent 404/5xx responses, not an
unconditional healthy status. Official releases are attributed announcements,
not independent corroboration.

Anthropic newsroom discovery follows same-site dated article cards, including
absolute URLs outside `/news/`, and orders them by their publisher-provided dates.
Sports discovery deduplicates repeated feed URLs and resolved article IDs before
review; sport-specific review batches still enforce complete candidate accounting.
