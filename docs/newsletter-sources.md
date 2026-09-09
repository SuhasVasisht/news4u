# Newsletter sources

The daily collector includes the public equivalents of these newsletters. No mailbox connection is required.

| Source | Collection | Selection |
| --- | --- | --- |
| ByteByteGo | `https://blog.bytebytego.com/feed`, up to 10 recent posts | Analysis; the existing 30-day longform review window supports occasional posts. Paid posts may provide only a public excerpt. |
| AlphaSignal | Public `/news/` pages linked from `https://alphasignal.ai/`, up to 20 per run | Publisher publication timestamps, descriptions, topic tags, and article text enter the existing editorial relevance review. Failed individual pages report partial health while preserving successful results. |
| TLDR Tech and AI | `https://tldr.tech/api/latest/tech` and `/ai`, which redirect to dated daily issues | Each article becomes a separate candidate, with its original publisher URL and newsletter summary/date. Sponsor blocks and TLDR recruiting links are excluded. |

TLDR previously collected homepage highlights; daily issue parsing now captures the full latest public issue, up to 30 non-advertising stories per newsletter. It retains the dated issue URL in raw metadata. An unparseable issue reports degraded health rather than silently falling back to fewer homepage highlights. Other TLDR editions are not enabled.

All candidates use normal URL normalization, repeated-ingestion suppression, recent cross-source title/URL clustering, and editorial selection. AlphaSignal keeps its own article URL and citation metadata: citations may reference background material, so sharing a citation alone is not treated as proof of duplicate coverage. The editorial review can identify same-event duplicates with different headlines; heuristic clustering alone does not guarantee all semantic duplicates are caught.

Collection reads the latest public feed/pages, not email contents or historical inbox messages. It cannot guarantee email-only material, paid full text, or every issue missed during an extended outage. Relevance and admission use the app's existing editorial policy; collection does not force every item into the edition.

To collect just these sources:

```sh
cd scripts/news_collector
NEWS_COLLECTOR_SOURCES=bytebytego,alphasignal,tldr_tech,tldr_ai NEWS_COLLECTOR_FORCE_RUN=1 .venv/bin/python -m news_collector.jobs.collect
```

The standard daily build runs collection, editorial review, and snapshot export before building the reader. Existing published static pages change only after the next build and deployment.
