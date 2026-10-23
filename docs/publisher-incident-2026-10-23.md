# October 23 coverage-source verification delay

October 23 published through the VM's normal automatic 09:05 retry, completing
at 09:28:13 Pacific with 17 news stories and seven sports stories. Hosted checks
verified all 24 reports and 23 images, preserved prior editions, and found no browser
errors. Desktop/mobile/sports screenshots and live date, article, archive and
sports navigation were inspected independently. No manual build, upload, runtime
edit or audit override was used. The recovery completed before the parser fix
described below was deployed; do not attribute the successful retry to that fix.

The 07:05 and 08:06 runs started normally but stopped during coverage discovery.
Several researched sources were unavailable or could not supply publisher-dated
evidence. In the 08:06 attempt, the official Treasury announcement was accessible
and contained 702 extracted words, yet verification treated its date as missing.
The parser recognized schema.org metadata but missed Drupal's explicit
`field--name-field-news-publication-date` containing a `time[datetime]` element.

The parser now recognizes that publication field only inside an article and only
when it supplies one unambiguous date. Existing explicit metadata retains
precedence. Arbitrary time elements, modified dates, footer dates and ambiguous
publication dates are not accepted as substitutes. The source-verification
algorithm version increases from 4 to 5 so old evidence proof is revalidated.
Unavailable publishers still fail verification; the change does not bypass
freshness, source independence, date matching, article length or required coverage.

Two regressions failed against the old parser and pass after the fix. Tests also
cover unrelated/modified/ambiguous dates, wrong claimed dates, future and stale
sources, and invalidation of algorithm-version 3 and 4 proof. Local validation
passes 471 collector tests, 61 application tests, lint and TypeScript checks.
Replaying the real saved Treasury HTML and the original rejected requirement now
verifies its publisher timestamp, `2026-10-22T21:00:00+00:00`, while retaining
`mustCover: true`. This replay makes no model call and does not change the edition.

The scheduler remained enabled throughout this investigation. A publisher was
already running when the VM became reachable, so no competing run was started.
The live archive also contains editions for every date October 16–22. The native
systemd user service remains the publisher, with hourly recovery slots beginning
at 07:05 Pacific and user lingering enabled.

Access initially failed because this Mac was logged out of Tailscale. The known
VM was reached over its local-network address using strict validation against its
existing SSH host key. That access problem did not cause the publishing failure.
Private journals, saved source HTML, failing-test output, frozen verification
receipt and hosted screenshots are retained in ignored
`data/reliability-proof-2026-10-23/`; no secrets or generated data are committed.
