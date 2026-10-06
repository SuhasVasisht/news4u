# Daily publisher on a remote VM

## Native Ubuntu alternative with an existing Codex login

For a server already running Node 22, Python 3.12 and an authenticated Codex CLI,
use a clean checkout at `~/news-publisher` and the user service in
`deploy/news-publisher-user.service`. Keep unrelated dirty checkouts intact.
Install npm dependencies with `npm ci`; install uv 0.10.9 and run
`uv sync --project scripts/news_collector --locked --extra dev`. Install Chromium
for both Node and Python Playwright, including their Linux system dependencies.
Store the publisher credentials, `NEWS_EDITOR_MODEL=gpt-5.6-luna`, and
`NEWS_EDITOR_REASONING_EFFORT=medium` in the ignored,
mode-0600 `~/news-publisher/.env`. Set `NEWS_EDITOR_CODEX_BIN` to the existing CLI's
absolute path and `NEWS_BACKUP_DIR` outside the checkout. This service runs as the
existing user, so its original Codex authentication is reused without copying tokens.

```sh
mkdir -p ~/.config/systemd/user
cp deploy/news-publisher-user.service deploy/news-publisher-user.timer ~/.config/systemd/user/
sudo loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now news-publisher-user.timer
systemctl --user list-timers news-publisher-user.timer
journalctl --user -u news-publisher-user.service -n 100 --no-pager
```

The native user service fast-forwards `origin/main` immediately before each daily
run. Tracked local changes, a failed fetch, or a non-fast-forward stops the job
before collection; do not force-reset the checkout. After changing the committed service
unit, copy it to `~/.config/systemd/user/` and run `systemctl --user daemon-reload`.

Linger keeps the user service available after logout and boot. Enable only one publisher
timer; use either this native service or the Docker service below. Stop the legacy
`news-app-scheduler-1` container when transferring scheduling ownership, without stopping
its unrelated web/database services. Disable its restart policy to keep it stopped
after reboot. Test Codex, mailbox and Cloudflare access under the service user before
activation. `npm run publish:rehearse` runs the same checkpointed collection, editorial audit, sports,
export, build and local browser verification without uploading. It loads `.env` and
restores public history automatically. Its final status is `validated`, never
`published`; a later real run still must execute deployment.

To defer the first publication, add a user-service drop-in with an `ExecCondition`
checking the start date in America/Los_Angeles. For example, the following prevents
publishing before October 6, 2026, while leaving subsequent daily runs enabled:

```ini
[Service]
ExecCondition=/usr/bin/python3 -c "import datetime,sys,zoneinfo; now=datetime.datetime.now(zoneinfo.ZoneInfo('America/Los_Angeles')); sys.exit(now.date() < datetime.date(2026,10,6) or now.time() < datetime.time(7,5))"
```

Reload systemd after adding the drop-in. An earlier timer tick will be skipped; the
first eligible tick on the chosen date remains 07:05 Pacific. The time check also prevents
reboot catch-up from publishing a new day before that morning cutoff. Inspect the condition,
timer and journal together when confirming the first publication time.

The supported static publication command is `npm run publish:daily`. It runs collection
(including IMAP newsletters), evidence-based editorial selection and independent final
audit, sports review, export, static rendering, local Chromium checks, Cloudflare upload,
and hosted Chromium verification. The prompts, source configuration, reader profile,
quality gates, dependency locks, and deployment code live in Git. Generated stories,
mail, databases, credentials, and browser profiles do not.

The old `docker-compose.yml` / `job:daily-sync` stack is a separate Next/Postgres app.
**Do not use that scheduler for news.suhasv.com.** The publisher needs no web server,
Postgres, inbound HTTP port, or tunnel on the VM. Cloudflare continues serving the site.

## Install (Ubuntu 24.04 with Docker Engine and Compose v2 already installed)

Use a dedicated VM. A starting allocation is 4 CPUs, 8 GB RAM and 50 GB disk; podcast
transcription can use substantial CPU/disk. Test your workload and monitor free space.
Outbound HTTPS, DNS and Gmail IMAPS on port 993 must work. Keep the VM clock synchronized.

```sh
sudo git clone git@github.com:SuhasVasisht/news-app.git /opt/news-app
cd /opt/news-app
sudo install -d -m 700 /etc/news-publisher
sudo install -m 600 deploy/publisher.env.example /etc/news-publisher/publisher.env
sudoedit /etc/news-publisher/publisher.env
sudo install -d -m 700 -o 10001 -g 10001 /var/lib/news-publisher /var/backups/news-publisher
sudo install -d -m 700 -o 10001 -g 10001 /var/lib/news-publisher/{data,out,collector-data,collector-output,codex,cache}
sudo docker compose -f compose.publisher.yml build
```

Fill in the existing Cloudflare account/token and mailbox username/app password.
Use the existing source API keys where available. Do not put the ordinary Gmail password
on the VM. Environment settings are passed at runtime, never baked into the image.
The example env file contains names/placeholders only. Compose overrides for state/env
paths are supported, but adjust the systemd unit as well if you use them.

Authenticate the editor inside its persistent private volume:

```sh
sudo docker compose -f compose.publisher.yml run --rm publisher codex login --device-auth
sudo docker compose -f compose.publisher.yml run --rm publisher codex login status
```

The [official Codex authentication documentation](https://learn.chatgpt.com/docs/auth)
documents device login and persistent auth. It recommends API key authentication for
programmatic jobs; to use that option, pipe your key through stdin to `codex login
--with-api-key` in the same container. Subscription login consumes the account's allowance.
Auth must remain writable so token refresh survives restarts. Neither login choice
guarantees unlimited usage. Do not commit or copy auth into the image. A dedicated login
on the VM avoids competing refreshes of a copied personal session.

Validate the installed image without publishing:

```sh
sudo docker compose -f compose.publisher.yml run --rm publisher sh -c 'npm test && npm run test:collector && npm run lint && npx tsc --noEmit && npx tsx scripts/publisher-smoke.ts'
```

Run the real pipeline once and inspect its journal, audit, and live site before enabling
the timer. This command **does publish** if today's edition is not already live:

```sh
sudo docker compose -f compose.publisher.yml run --rm --name news-publisher publisher
sudo install -m 644 deploy/news-publisher.service deploy/news-publisher.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now news-publisher.timer
sudo systemctl list-timers news-publisher.timer
```

The timer uses America/Los_Angeles explicitly, including DST: 07:05, then every half
hour through 22:35. `Persistent=true` catches a missed invocation after reboot. Adjust
the committed timer or a systemd override if newsletters arrive later. Only one machine
should own daily scheduling; stop the laptop/legacy scheduler when moving to the VM.

## Recovery and publication semantics

- The OS file lock covers supported manual build/deploy commands and the full publisher.
  It releases after exit or reboot; never delete `data/publisher.lock`. Lock-file presence
  alone does not mean a job is active. Use npm commands rather than invoking raw TS files.
- Atomic checkpoints resume successful phases within six hours of collection. A new
  local date, changed code/profile/model, changed publication history, or missing/changed
  checkpoint artifacts starts fresh. Normal retries preserve the review's own evidence
  caches. Transient model-capacity errors get two bounded retries with the same model before
  failing for the next timer attempt. No retry weakens an audit, switches models, or
  silently substitutes hand-edited JSON.
- A run crossing midnight stops before its next phase. It never manufactures editions
  for missed days. The next run collects for the current day.
- The live manifest is checked before collection and again before upload. An already
  published date is a no-op. Interrupted uploads are reconciled against the exact bundle;
  if that upload is live, verification resumes instead of publishing a second edition.
- Source errors are recorded in `data/collection-run.json` and source/audit files. A total
  collection failure blocks the run. Partial sources still go through the independent
  coverage/factual gate. Missing mailbox credentials block the unattended publisher.
  Fresh collections check sources immediately while retaining their rate-limit cooldowns.
- The previous site remains live through prepublication failures. A post-upload hosted
  verification failure is reported as failure and retried; the new site may already be
  live at that point. The publisher does not claim Cloudflare uploads are transactional
  with browser verification.

Fresh VMs recover the existing public release and every archived file from the live
manifest, validate hashes, and atomically retain it as publication history. A corrupt,
incomplete, or changing archive blocks publication. This protects archives and novelty
checks without putting a DB in Git. This recovery expects an existing production site;
initially launching a different empty site is a separate setup operation.

## State, backups, updates and monitoring

`/var/lib/news-publisher` holds the collector SQLite DB, mailbox UID cursor, extraction
caches, review/audit records, checkpoints, static output, retained archives and Codex
auth. Persist the entire directory across container replacements. If you start with
an empty DB, collection and eligible recent mail are replayed; public history prevents
already-published stories from being treated as new.

For a migration that preserves all private history, stop publishers on both hosts, then
transfer `data/`, `out/`, `scripts/news_collector/data/`, and
`scripts/news_collector/output/` over SSH into their corresponding volume directories.
Copy SQLite only while writers are stopped (including its WAL/SHM files if present),
or use SQLite's backup API. Restore ownership to UID/GID 10001. Authenticate separately
on the VM. Do not transfer `.venv`, `node_modules`, or a laptop's executable browser cache.

The deployer stores before/after release tarballs under `/var/backups/news-publisher`.
These are **public release backups, not database/auth backups**. Schedule encrypted VM
or volume snapshots separately, including state and `/etc/news-publisher`, and test a
restore. Monitor disk capacity and apply a backup retention policy. Archives have a
20,000-file release cap; the deployer stops rather than silently deleting old editions.

```sh
sudo journalctl -u news-publisher.service -n 150 --no-pager
sudo cat /var/lib/news-publisher/data/publisher-status.json
sudo cat /var/lib/news-publisher/data/publisher-state.json
sudo systemctl start news-publisher.service          # retry now
sudo docker compose -f /opt/news-app/compose.publisher.yml run --rm publisher npm run publish:check
```

`publish:check` returns nonzero if today's edition is absent or public recovery fails.
If an interrupted local upload is live, it completes verification. It does not collect
or upload. Point your existing monitoring at this command or the live manifest date
after your publication deadline, and alert on failed services/disk capacity. Journal and
state files make failures visible; no email/Slack alert destination is configured by default.
This is scheduled, retried publishing—not a promise that source outages, account limits,
or failed factual audits can always be overcome automatically.

For a manual update, disable the timer, wait for the active service to finish, pull with
`--ff-only`, rebuild the image, rerun the validation command, and re-enable the timer. Do
not update mid-publication. GitHub Actions builds and tests the Linux image without secrets
on each push/PR. For rollback, rebuild the last good Git
commit against the same persistent state; do not roll the DB back independently of its
publication history. A production content rollback requires an explicit reviewed release.

Local development uses `npm ci`, `uv sync --project scripts/news_collector --locked --extra
dev`, Node Chromium (`npx playwright install chromium`) and Python Chromium
(`scripts/news_collector/.venv/bin/python -m playwright install chromium`). The image pins
Node, uv and Codex versions; npm and uv locks pin application dependencies. Editorial
outputs can still vary with live news and model behavior; reproducibility means the same
pipeline and acceptance criteria, not byte-identical future articles.

Editorial retries retain the draft tied to the publisher run's date, code revision,
public history and collection start. A new run invalidates that draft. Independent
research can be reused only within its six-hour/day cutoff and unchanged research
configuration. Structurally valid factual batches, including hold findings, are cached against their full evidence,
prose, selection context, history, prompt and model settings, and are revalidated
on reuse. Coverage output contracts are checked inside the bounded model retry;
genuine missing coverage still blocks publication and permits one audited reselection.
No malformed coverage response can authorize deployment.

Audit schemas bind each story to its exact published text and available chunk IDs.
Cached holds remain holds until repair or selection changes the reviewed inputs;
retries do not repeatedly ask for a different verdict on unchanged evidence.

Independent must-cover discovery uses the same 48-hour breaking-news window as
ordinary editorial admission. Older context cannot create a new blocking event
without a recent, verified source for a material development. Discovery uses the
shared bounded review runner. Internal chunk markers and Markdown formatting are
normalized before selection and factual auditing; evidence links remain in the
review records and no factual claims are rewritten by that normalization.

Hard Codex account exhaustion is recorded in ignored `data/editor-quota.json`.
The scheduler reports `blocked` with the reset time and stops before collection or
further model calls while that block is active. Transient model capacity remains
separate and uses bounded retries. After adding credits or changing the funded
editor login, run `npm run publish:daily -- --retry-editor` once to clear the
operational block and test availability. Do not clear it repeatedly without
restoring capacity. A known reset time clears the block automatically when due;
unknown resets require explicit recovery. Already-live editions remain no-ops.
