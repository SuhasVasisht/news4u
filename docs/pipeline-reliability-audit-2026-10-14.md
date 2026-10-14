# October 14 publisher recovery and independent audit

October 14 is live at https://news.suhasv.com with 21 news stories and six sports
stories. The normal VM service completed deployment at 09:21:56 Pacific. Hosted
verification checked all 27 reports and images, preserved prior editions, and
reported no browser errors. Desktop, mobile, article, archive and sports navigation
were also inspected independently.

## Failure and corrections

The 07:05 and 08:05 scheduled runs both started. Collection succeeded; the final
gate blocked an IMF story that repeated October 13 without a material update.
Coverage reconciliation did not receive that novelty finding and treated the held
story as coverage of a mandatory event. Pruning then protected it because of that
mandatory mapping. This was an internal contract deadlock, not a quota or timer
failure.

| Defect | Correction | Evidence |
| --- | --- | --- |
| Coverage could map a held repeat as fresh mandatory coverage | Pass factual/novelty findings into coverage reconciliation; require valid prior-publication accounting or retain a missing-event block | Exact failed morning request replayed through Luna: all three mandatory events retained, repeated story excluded, 21 stories passed |
| A changed cutoff or unrelated selection could obtain a new verdict for unchanged held facts | Reuse individual findings only when evidence, prose, history, policy and same-edition freshness agree; preserve validated request/response pairs and prioritize matching holds | Isolated rehearsal exposed the inconsistent approval before upload; direct evidence comparison and frozen replay recovered the original hold |
| Sports model output used a historical ID where the consumer required current-batch IDs | Constrain the structured duplicate reference schema to current-batch IDs; historical duplicates remain held with a null pointer and explanation | Saved failed response, schema regression test, and full successful sports rehearsal |
| Malformed shared audit files could prevent the next day's fresh review | Ignore unusable optimization files while retaining valid immutable findings | Real two-day orchestration with publication history and four malformed/wrong-type cache cases; corrupt latest response cannot erase a same-day hold |
| A failed companion story could strand a required event even when a passed account remained | Reconcile coverage independently against the retained subset before accepting removal; reuse factual findings | Positive and missing-required-event cases, plus interrupted coverage request and persisted resume; held facts reviewed only once |
| An old secondary publisher could corroborate a fresh required development | Require both independent publishers within the 48-hour freshness window, or fresh authoritative evidence; bump source-proof algorithm version | Stale-background rejection, fresh corroboration acceptance, and old-version proof invalidation |

The last three findings came from a fresh independent agent after publication.
The review also inspected scheduler retries, checkpoints, deployment recovery,
history invalidation and lock forwarding; it found no further high-confidence
defect in those paths. Existing factual, novelty, evidence and mandatory coverage
gates remain enforced.

## Operational proof

The final isolated VM rehearsal passed collection, live Luna review, news and
sports audits, export, build and local verification at 09:17:20. Production was
mounted read-only during rehearsal. A private pre-recovery backup was retained
outside Git; the validated runtime snapshot then passed production no-upload
replay at 09:18:26. Publication used the ordinary native service and deploy stage.
Generated stories and audit verdicts were not manually edited.

The persistent user timer was restored at 09:23:17. Without another manual start,
it triggered the native service, pulled Git, detected the already-published
October 14 edition and exited successfully at 09:23:21. The timer remains enabled
with hourly recovery slots from 07:05 through 22:05 Pacific, and user lingering
enabled. October 15's first slot is 07:05 Pacific, with configured short jitter.

Final validation: 439 collector tests, 59 application tests and lint pass locally
and on Ubuntu. Tests include frozen failure contracts, next-day state reuse,
interrupted coverage recovery, unchanged-hold preservation and source-proof
invalidation. Private logs, audit inputs/results, hosted verification receipt and
screenshots are retained under ignored `data/reliability-proof-2026-10-14/`;
credentials, database, editions and media are excluded from commits.

This verifies the failures reproduced here and the configured unattended retry
path. It cannot guarantee every future external source or model response will
succeed. A genuinely unsupported required event still blocks publication, leaves
the previous edition live, and records the reason for the next bounded retry.

Source health warnings during recovery included AP access rejection, Guardian
fallback and cooldowns for GDELT/Alpha Vantage. Mandatory coverage was still
accounted for through verified evidence; optional omissions remain recorded in
the edition's audit.
