# Coverage failure and recovery rehearsal — October 14

These are controlled failure injections into the real review orchestration and
publisher state machine. They do not change the live edition, contact a model,
or manufacture replacement source material for publication.

| Injected failure | Required result |
| --- | --- |
| Coverage service fails after the factual desk holds a story | Persist the completed factual batch before coverage; resume from disk with the same hold even when collection advances its cutoff |
| A later factual batch fails after an earlier batch contains a hold | Preserve completed findings and review only outstanding evidence on resume |
| Eight-hour same-edition outage | Keep unchanged blocked findings; approvals still expire after six hours; next-day evidence requires review again |
| Mandatory event absent because of discovery, extraction, deduplication or selection | Repeated persisted retries remain blocked; only an actual newly supplied source packet can resolve the missing event |
| Three consecutive hourly coverage blocks | Preserve the live paper; resume the editorial stage without repeating valid collection; deploy once after recovery |
| All sixteen daily recovery slots fail coverage | Never deploy the unsupported edition; reset the retry budget and collect fresh on the next date |

The reproduced defect was a persistence gap: immutable factual findings were
saved only after the coverage call completed. A coverage or later-batch outage
could leave a hold solely in a cache keyed by the exact cutoff. Refreshed
collection changed that key and could obtain a different verdict for unchanged
facts. Completed factual batches are now independently archived before subsequent
calls. Same-edition holds also outlive the six-hour approval reuse limit; time
alone does not resolve a factual concern. Evidence/prose/history/policy changes
still require review, as does a new edition date.

Before the fixes, four interruption tests failed because unchanged held evidence
was reviewed again and incorrectly passed. After the fixes, the same tests block
correctly. Nine orchestration scenarios and four finding-reuse cases were added,
plus two durable publisher recovery scenarios. Final suites contain 452 collector
tests and 61 application tests; both pass along with lint and TypeScript checks.

## Public repository checks

Gitleaks scans all Git history with redacted output. One exact historical README
finding is allowlisted: a sample command using an environment-variable username
and a placeholder password. The exception is tied to that commit, path, rule and
line; new occurrences are scanned. A separate exact-value history check against
local credentials found only documented local development defaults, with no
newsletter or Cloudflare credential match. Tracked files exclude environment
files, databases and private keys; ignore rules cover runtime data and private
proof. No private scan output or runtime data is committed.

A new GitHub workflow job runs a pinned Gitleaks release against full history on
pushes and pull requests, checks the release archive checksum, and redacts all
findings. This detects accidental committed credentials; it does not replace
GitHub push protection or guarantee that every possible secret format is known.

Genuine missing evidence remains a publication blocker. Resilience means durable
findings, bounded retries, correct recovery when new evidence arrives, and keeping
the previous paper available while a required event is unsupported. It does not
mean approving an unsupported story.
