# October 13 daily publisher reliability audit

An independent sub-agent reviewed the scheduler, checkpoint recovery, source
research/intake, editorial caches, sports selection/export and release verification.
It independently confirmed the morning failure from the VM journal, found further
producer/consumer defects, implemented the sports and cache corrections, and
reviewed the primary agent's source-provenance and recovery fixes. It made no
production changes. The primary agent integrated, tested and deployed the work.

## Actual failure

The 07:05 automatic run collected successfully. At 07:11 it rejected an accessible,
publisher-dated 393-word IMF report because authority detection used government
suffixes but omitted IMF's official `.org` domain. Its AP companion returned 403.
A later attempt similarly rejected a dated 469-word IMF report. These were false
source-authority rejections, not account quota exhaustion or a missing scheduler.

The 08:05 retry was a fraction of a second short of the exact one-hour cooldown
and was skipped. Three substantive failed starts exhausted the budget by 10:08;
later timer invocations had no path to recover automatically that edition day.
Yesterday's passing end-to-end run did not exercise these institution-domain or
real timer-jitter cases. The earlier assurance was therefore too broad.

## Findings and corrections

| Finding | Correction | Regression evidence |
| --- | --- | --- |
| Primary public institutions outside government suffixes were rejected | Exact institutional roots/subdomains and recognized government suffixes share one authority policy; arbitrary `.org` domains and lookalikes do not gain authority | Original morning evidence replay: rejected before, accepted after, same mandatory event retained; discovery and final gate tests cover institutional/government roots, aliases and lookalikes |
| Discovery verified redirected URLs but handed original/failed companions to downstream gates | Persist only actually verified final URLs and publisher timestamps for mandatory events; final gate and intake receive that same evidence | Redirect/blocked-companion normalization and same-publisher redirect rejection |
| Source proof could be stale after policy changes, or needlessly refetched during repair | Hash the complete authority policy and exact normalized checklist; checksum-bound same-pipeline evidence may be reused within the existing freshness limit | Same repair reuses verified snapshot during transient outage; changed checklist requires fresh verification; policy changes invalidate cache |
| Ordinary candidate limits could crowd out new required sources | Prioritize the bounded required URL set and prevent ordinary per-source limits alone from excluding it | Thirty older high-score research records plus one lower-score required article: the required article reaches the desk |
| Sports selection accepted duplicates that export rejected | Selection and export use one deterministic overlap predicate across groups | Model selection, cached retry and real sports export agree for same-group and misclassified cross-group duplicates |
| Malformed or contract-invalid news caches aborted the run | Regenerate only invalid cached work through normal bounded review | Invalid JSON, unknown evidence/selection IDs, and audit citation cases; valid factual holds remain blocked and cached |
| Scheduler jitter skipped valid hourly recovery; three failures abandoned the day | A 55-minute cooldown tolerates hourly jitter; sixteen starts match the configured 07:05–22:05 recovery slots; health distinguishes waiting, blocked and failed | Actual timer timestamps reproduced; afternoon retry allowed after morning failures; next-day/revision resets and final cap remain enforced |

## Validation and boundaries

Code fixes are in `145aa91`, with filesystem-independent test selection in
`a3411fa` and consistent government root/subdomain handling in `eee3f4a`.
Ubuntu validation passed 390 collector tests, 59 application tests and lint.
The complete no-upload VM rehearsal and publication results are recorded below
when finished. Runtime logs, source artifacts, databases, credentials and private
proof are excluded from Git.

Source freshness, promotion exclusions, publisher caps, required coverage,
independent factual/novelty audits, exact audited selection, same-day gates and
release byte verification remain enforced. Valid held evidence is never repeatedly
reviewed to seek a lucky approval. Quota exhaustion remains separately blocked.

This audit establishes the reproduced defects and their tested corrections. It
cannot prove success for every future publisher response, model response, account
state, network condition or hosting outage. A legitimate failed quality gate must
remain a visible failure rather than publishing an unsafe edition.
