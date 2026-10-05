# Newsletter sources

The daily collector reads TLDR Tech and AI from the dedicated inbox, AlphaSignal from both the inbox and public site, and ByteByteGo through RSS.

| Source | Collection | Selection |
| --- | --- | --- |
| ByteByteGo | `https://blog.bytebytego.com/feed`, up to 10 recent posts | Analysis; the existing 30-day longform review window supports occasional posts. Paid posts may provide only a public excerpt. |
| AlphaSignal | Public `/news/` pages linked from `https://alphasignal.ai/`, up to 20 per run | Publisher publication timestamps, descriptions, topic tags, and article text enter the existing editorial relevance review. Failed individual pages report partial health while preserving successful results. |
| TLDR Tech and AI | Delivered daily emails (`tldr_email`) | Editorial blocks become separate original-publisher links. The old web collectors are disabled, with code retained for a manual fallback. |

TLDR previously collected homepage highlights; daily issue parsing now captures the full latest public issue, up to 30 non-advertising stories per newsletter. It retains the dated issue URL in raw metadata. An unparseable issue reports degraded health rather than silently falling back to fewer homepage highlights. The web paths are now disabled after the September 10 comparison below. Other TLDR editions are not enabled.

All candidates use normal URL normalization, repeated-ingestion suppression, recent cross-source title/URL clustering, and editorial selection. AlphaSignal keeps its own article URL and citation metadata: citations may reference background material, so sharing a citation alone is not treated as proof of duplicate coverage. The editorial review can identify same-event duplicates with different headlines; heuristic clustering alone does not guarantee all semantic duplicates are caught.

The web collectors read the latest public feed/pages, not email contents or historical inbox messages. They cannot guarantee email-only material, paid full text, or every issue missed during an extended outage. The dedicated inbox integration below also collects delivered newsletters. Relevance and admission use the app's existing editorial policy; collection does not force every item into the edition.

To collect just these sources:

```sh
cd scripts/news_collector
NEWS_COLLECTOR_SOURCES=bytebytego,alphasignal,tldr_email,alphasignal_email NEWS_COLLECTOR_FORCE_RUN=1 .venv/bin/python -m news_collector.jobs.collect
```

The standard daily build runs collection, editorial review, and snapshot export before building the reader. Existing published static pages change only after the next build and deployment.

## Dedicated newsletter inbox

An optional IMAP collector now feeds emailed TLDR and AlphaSignal links into the same ingestion, canonical URL deduplication, editorial review, and daily build. ByteByteGo stays on RSS. Mail collection runs when the daily report job runs; it is not a push listener.

Setup completed September 9, 2026 (Pacific): the dedicated Gmail account has two-step verification, a collector app password saved in the ignored local `.env.newsletters`, and verified TLS/read-only IMAP access. Both email sources are enabled locally. TLDR Tech + AI signup and its confirmation flow are complete; AlphaSignal displayed “You're on the list” and finished onboarding. AlphaSignal includes all AI topics plus news, papers, models, and repositories; optional partner newsletters were declined. The September 10 delivery review below supersedes the initial decision to keep every web source active.

The first live ingestion run reported `ok` for both email collectors with zero stories: only signup/security mail had arrived. The real TLDR confirmation message exposed an onboarding-help-link edge case, now covered by a regression test: control-message subjects are skipped before extracting any links. Daily layouts were subsequently validated on September 10; successful authentication alone did not establish extraction completeness.

### Connect the mailbox

1. Create a dedicated email account. For Gmail, enable two-step verification and create an app password where the account permits it. See [Google's app-password instructions](https://support.google.com/accounts/answer/185833). A normal Google password is not the intended credential.
2. Subscribe that address to [TLDR Tech](https://tldr.tech/), [TLDR AI](https://tldr.tech/ai), and [AlphaSignal](https://newsletter.alphasignal.ai/). These are two publishers and three lists, matching the current Tech + AI coverage. Complete any subscription confirmations yourself during setup; the collector never follows confirmation or unsubscribe links.
3. Run the interactive setup from the repository root:

   ```sh
   scripts/news_collector/.venv/bin/python scripts/news_collector/news_collector/jobs/setup_mailbox.py
   ```

   The password prompt does not echo. The setup verifies TLS login and read-only folder access, then atomically saves `.env.newsletters` with owner-only permissions and enables the email sources. The file is ignored by Git and excluded from Docker builds. Credentials are stored locally in plaintext protected by filesystem permissions, not encrypted; do not add this file to shared artifacts. No inbox credentials enter story data or static output.
4. Run a targeted collection and inspect the source counts and stories:

   ```sh
   cd scripts/news_collector
   NEWS_COLLECTOR_SOURCES=tldr_email,alphasignal_email NEWS_COLLECTOR_FORCE_RUN=1 .venv/bin/python -m news_collector.jobs.collect
   ```

   Review source health and candidates when templates change. The first delivered issues were validated September 10; retirement decisions are recorded below.

Local commands automatically load `.env.newsletters`; existing process environment variables take precedence. Docker workers need the same variables supplied at runtime through an additional `env_file` or secret injection; this file is deliberately not baked into the image. The local daily workflow needs no extra scheduling changes.

### Collection behavior and limits

- Read-only IMAP over verified TLS; `BODY.PEEK` leaves read/unread flags intact. No deletion, forwarding, sending, or automatic account actions.
- Sender-domain allowlist for TLDR and AlphaSignal. This is a scope filter, not a substitute for the mailbox provider's spam/authentication checks.
- HTML and labeled plain-text links become story candidates. Sponsor, subscription, account, recruiting, and tracking-image links are filtered. Email layouts vary; relevance review remains necessary and exact extraction recall is not guaranteed.
- Follows article redirects to public HTTP(S) destinations, strips standard tracking parameters, extracts article text, and retains the newsletter send date as the date basis. Blocked/paywalled/unavailable articles retry; their full text is not guaranteed.
- At most 20 messages and 100 candidate article fetches per source per run, with 0.5 seconds between link attempts. HTTP 429 stops further requests to that host during the run. The existing daily job retries later; it does not sleep for a server's `Retry-After` interval. Image processing and editorial enrichment can make additional requests.
- Looks back 30 days. Stores processed UID sets scoped to mailbox identity and UIDVALIDITY, after raw/normalized items have been persisted. Interrupted runs replay safely through existing duplicate suppression. Partial messages retry; healthy empty inboxes report success. Messages older than the configured window are not automatically backfilled.
- Recipient addresses, authentication credentials, full email headers, and original email bodies are not stored in story metadata. Source attribution uses `tldr_email` / `alphasignal_email`; raw metadata retains only a message hash and date basis.

## September 10 delivery review and source decisions

All three daily messages arrived: TLDR Tech, TLDR AI and AlphaSignal. Actual MIME
samples were inspected locally, without changing their read/unread state.

- **TLDR Tech:** 14 non-sponsored email stories, matching all 14 web issue titles.
- **TLDR AI:** 17 email stories; the public daily issue exposed 13, all included in
  the email. Four additional email headlines were DeepSeek-V4.1-Flash, GPT-6 Astra /
  looped transformers, Additional findings, and Recursive Synthetic Improvement.
- **AlphaSignal:** eight editorial email stories after removing sponsored blocks,
  compared with a public front page containing other AI stories as well. The email
  points to original sources (including repositories and papers); the site provides
  distinct editorial writeups and additional events. It is not an identical archive.

Decision: disable routine `tldr_tech` and `tldr_ai` web collection; retain their
implementation as a manually enabled fallback. Keep `alphasignal` and
`alphasignal_email` enabled and let event-level editorial review choose the best
account. ByteByteGo remains on RSS. No additional subscriptions were added: first
measure the incremental value of these delivered lists in actual published editions.

The real templates exposed nested ad calls to action and footer links in the generic
parser. TLDR now extracts labeled story blocks; AlphaSignal extracts article headings
and their read-more links plus non-sponsored signals. Sponsor sections, paid signals,
referrals and account actions do not become candidates. Regression fixtures cover both.
The first production run resolved 29 of 31 TLDR story links and all eight AlphaSignal
links; TLDR reports partial health and retries its unavailable links. Successful HTTP
fetches still require evidence review (a login shell is not an article). Email delivery
does not remove publisher rate limits or paywalls. Shared gift access parameters are
removed from public URLs, including historical rows read under the current rules.

Newsletter send time records discovery in that issue. It does not establish that an
event is new: publication-history checks and editorial review reject prior events
rediscovered through another newsletter or publisher.
