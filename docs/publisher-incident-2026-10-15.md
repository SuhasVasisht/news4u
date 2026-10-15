# October 15 sports admission failure

The native Ubuntu timer started the publisher at 07:06 and retried at 08:06.
Collection and the independent news audit passed; sports review failed both times.
The failed model response admitted a 75-word BBC championship article. The shared
validator correctly requires at least 80 words, but candidate intake sent that
ineligible article to the model. Both bounded attempts admitted it, so the same
impossible admission blocked the entire edition on the automatic retry too.

The validator's generic “lacks evidence” message did not identify which source
condition failed. It now includes the candidate ID and deterministic reason.
Sports intake shares the validator's source gate and creates explicit holds for
articles below 80 words, truncated articles and articles without evidence chunks
before model calls. These holds have no publishable prose and are recorded as
`sports_candidate_held`. Eligible evidence still receives normal editorial,
novelty and factual review; malformed output for eligible articles still blocks.
No article, required coverage or factual approval was manually changed.

## Reproduction and validation

Five new source-gate scenarios fail against the previous code and pass with the
fix. They cover the actual 75-word failure, 79 words, truncation, missing chunks,
and a batch containing no eligible article. Additional cases verify the 80/81-word
boundary, persistence/reuse, exact candidate accounting, and continued rejection
of malformed eligible decisions. Replaying the exact saved failed packet produces
a hold with zero model calls; its original admission remains rejected.
The complete original 47-candidate request also passes candidate validation in
an isolated replay: original validated decisions are rebatched and revalidated,
while all six source-ineligible packets receive holds. No new model call or
publication occurs in that replay. The fresh full VM run is separate evidence.

Local and Ubuntu checks pass 460 collector tests, 61 application tests, lint and
TypeScript. Full-history and staged-diff Gitleaks scans pass. Private inputs,
responses, regression output and journals are retained in ignored
`data/reliability-proof-2026-10-15/`; credentials and runtime data are not committed.

## Which scheduler actually runs

The active scheduler is `news-publisher-user.timer`, invoking the native
`news-publisher-user.service` in `~/news-publisher`. The old
`news-app-scheduler-1` container has been stopped for ten days and does not own
scheduling. The container remains a portable deployment option checked in CI.
The workflow label now says that explicitly rather than claiming the VM uses it.

Journal inspection confirmed service starts on October 12, 13, 14 and twice on
October 15 before intervention. Counts include manual recovery starts and should
not be interpreted as entirely unattended publication. Today's two morning starts
were automatic. Timer activity alone does not prove a successful paper: inspect
the date/status in `data/publisher-status.json`, stage completion/failure records,
and the live manifest. The service's hourly retries, lock, bounded attempt budget,
Luna model and quality requirements remain in place.

The previous tests covered malformed output and coverage interruptions but did
not cover a valid model decision admitting a deterministically ineligible sports
source. The new gate and tests address that omission; they do not claim every
possible future model or source failure has been eliminated.

## Publication outcome

The normal full no-upload pipeline passed at 08:58:16 Pacific, including fresh
collection, live Luna review, factual and novelty audits, sports, export, static
build, and local browser verification. News repair and sports repair ran through
their bounded automatic paths; unresolved sports copy was omitted. The final
edition has 18 news stories and seven sports stories, with zero unresolved news
claims or duplicate news event groups. AP returned a recorded nonfatal 403.

The native publisher service started at 08:59:20, reused all five validated
stages, and completed verified deployment at 09:02:49. The live edition is
https://news.suhasv.com/editions/2026-10-15/ . Hosted verification checked all 25
reports and images, preserved the prior archives, and found no browser errors.
Desktop/mobile layout and live article/archive/sports navigation were independently
checked. Temporary hosted propagation and transport failures recovered through
existing bounded retries; no upload or quality check was bypassed.

The timer was restored after verified publication, with the next automatic slot
at 09:05 Pacific and the usual hourly slots through 22:05. Tomorrow's first slot
is 07:05 Pacific, with configured short timer jitter. Lingering is enabled so the
user service does not require an SSH login. Private run receipts and the next
automatic trigger's journal are retained with the incident proof.
