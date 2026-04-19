import { execFile } from "node:child_process";
import fs from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import postgres from "postgres";
import { collectorImportanceToArticleScore } from "@/lib/scoring";

const execFileAsync = promisify(execFile);
const rootDir = process.cwd();
const collectorDir = path.join(rootDir, "scripts", "news_collector");
const pythonBin = process.env.PYTHON_BIN || path.join(collectorDir, ".venv", "bin", "python");
const collectorDbPath =
  process.env.NEWS_COLLECTOR_DB_PATH || path.join(collectorDir, "data", "news_collector.db");
const collectorOutputDir =
  process.env.NEWS_COLLECTOR_OUTPUT_DIR || path.join(collectorDir, "output");
const syncOutboxDir =
  process.env.NEWS_COLLECTOR_SYNC_OUTBOX_DIR || path.join(collectorOutputDir, "sync");
const appUrl = process.env.AUDIT_APP_URL || "http://127.0.0.1:3000";
const appTimezone = process.env.APP_TIMEZONE ?? "America/Los_Angeles";
const appDailyResetHour = Number(process.env.APP_DAILY_RESET_HOUR ?? 5);

function loadDotenv(envPath: string) {
  if (!fs.existsSync(envPath)) {
    return;
  }

  for (const line of fs.readFileSync(envPath, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) {
      continue;
    }
    const separator = trimmed.indexOf("=");
    const key = trimmed.slice(0, separator).trim();
    const value = trimmed.slice(separator + 1).trim();
    if (!(key in process.env)) {
      process.env[key] = value;
    }
  }
}

loadDotenv(path.join(rootDir, ".env"));

type PythonJsonResult = {
  stdout: string;
  stderr: string;
  json: Record<string, unknown> | null;
};

type AuditRow = {
  title: string;
  status: string;
  detail?: string;
};

type PostgresArticleAuditRow = {
  id: string;
  title: string;
  score: number;
  payloadJson: Record<string, unknown> | null;
  ingestedAt: string;
  publishedAt: string;
  sourceSlug: string;
};

type PostgresStoryAuditRow = {
  id: string;
  canonicalHeadline: string;
  importanceScore: number;
  lastUpdatedAt: string;
  sourceCount: number;
  updateCount: number;
  representativeSourceSlug: string;
  representativeSourceName: string;
  topicSlugs: string[];
  representativeArticleScore: number;
  representativeSummaryLength: number;
  representativeContentLength: number;
  representativeTrustScore: number | null;
};

type PostgresFeedAuditRow = {
  feedDate: string | Date;
  storyId: string;
  section: string;
  rankPosition: number;
  rankScore: number;
  canonicalHeadline: string;
};

type PostgresAuditResult =
  | { available: false; detail: string }
  | {
      available: true;
      articles: PostgresArticleAuditRow[];
      stories: PostgresStoryAuditRow[];
      feedItems: PostgresFeedAuditRow[];
    };

function printSection(title: string) {
  console.log(`\n## ${title}`);
}

function printRows(rows: AuditRow[]) {
  for (const row of rows) {
    const suffix = row.detail ? `: ${row.detail}` : "";
    console.log(`- ${row.title} [${row.status}]${suffix}`);
  }
}

async function runPythonModule(moduleName: string): Promise<PythonJsonResult> {
  const env = {
    ...process.env,
    NEWS_COLLECTOR_FORCE_RUN: "1",
  };
  const { stdout, stderr } = await execFileAsync(pythonBin, ["-m", moduleName], {
    cwd: collectorDir,
    env,
  });

  let json: Record<string, unknown> | null = null;
  try {
    json = JSON.parse(stdout);
  } catch {
    json = null;
  }

  return { stdout, stderr, json };
}

async function runPythonQuery(script: string) {
  const { stdout } = await execFileAsync(pythonBin, ["-c", script], {
    cwd: collectorDir,
    env: {
      ...process.env,
      AUDIT_COLLECTOR_DB_PATH: collectorDbPath,
    },
  });
  return JSON.parse(stdout) as unknown;
}

function latestPathIn(dirPath: string) {
  if (!fs.existsSync(dirPath)) {
    return null;
  }
  const names = fs.readdirSync(dirPath).sort();
  if (names.length === 0) {
    return null;
  }
  return path.join(dirPath, names.at(-1)!);
}

async function readJson(filePath: string) {
  return JSON.parse(await readFile(filePath, "utf8")) as Record<string, unknown>;
}

async function probeApp() {
  try {
    const response = await fetch(`${appUrl}/api/health`);
    if (!response.ok) {
      return { reachable: false, detail: `health returned ${response.status}` };
    }
    const json = (await response.json()) as Record<string, unknown>;
  return { reachable: true, detail: JSON.stringify(json) };
  } catch (error) {
    return { reachable: false, detail: error instanceof Error ? error.message : String(error) };
  }
}

const TECH_TOPIC_SLUGS = new Set([
  "technology",
  "ai",
  "artificial-intelligence",
  "startups",
  "devtools",
  "cloud",
  "semiconductors",
]);
const TECH_SOURCE_HINTS = ["tech", "ai", "dev", "cloud", "data", "chip", "startup", "hacker", "product"];

function round(value: number) {
  return Math.round(value * 1000) / 1000;
}

function normalizedParts(date: Date) {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: appTimezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hour12: false,
  });
  const parts = formatter.formatToParts(date);
  return {
    year: Number(parts.find((part) => part.type === "year")?.value ?? "0"),
    month: Number(parts.find((part) => part.type === "month")?.value ?? "0"),
    day: Number(parts.find((part) => part.type === "day")?.value ?? "0"),
    hour: Number(parts.find((part) => part.type === "hour")?.value ?? "0"),
  };
}

function normalizeFeedDateKey(feedDate: string | Date) {
  if (feedDate instanceof Date) {
    return feedDate.toISOString().slice(0, 10);
  }
  return feedDate;
}

function addDays(dateKey: string, delta: number) {
  const [year, month, day] = dateKey.split("-").map(Number);
  const next = new Date(Date.UTC(year, month - 1, day + delta));
  return `${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, "0")}-${String(next.getUTCDate()).padStart(2, "0")}`;
}

function feedReferenceDate(feedDate: string | Date) {
  const boundaryDateKey = addDays(normalizeFeedDateKey(feedDate), 1);
  const [year, month, day] = boundaryDateKey.split("-").map(Number);
  let guess = new Date(Date.UTC(year, month - 1, day, appDailyResetHour + 8, 0, 0, 0));

  for (let index = 0; index < 4; index += 1) {
    const parts = normalizedParts(guess);
    const targetLocalAsUtc = Date.UTC(year, month - 1, day, appDailyResetHour, 0, 0, 0);
    const currentLocalAsUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, 0, 0, 0);
    const diff = targetLocalAsUtc - currentLocalAsUtc;
    if (diff === 0) {
      break;
    }
    guess = new Date(guess.getTime() + diff);
  }

  return new Date(guess.getTime() - 1);
}

function storyHasTechSignal(story: Pick<PostgresStoryAuditRow, "topicSlugs" | "representativeSourceSlug" | "representativeSourceName">) {
  return (
    story.topicSlugs.some((slug) => TECH_TOPIC_SLUGS.has(slug)) ||
    TECH_SOURCE_HINTS.some(
      (token) =>
        story.representativeSourceSlug.toLowerCase().includes(token) ||
        story.representativeSourceName.toLowerCase().includes(token),
    )
  );
}

function computeStoryAudit(story: PostgresStoryAuditRow, referenceDate: string) {
  const freshnessHours = Math.max(
    0,
    (new Date(referenceDate).getTime() - new Date(story.lastUpdatedAt).getTime()) / (60 * 60 * 1000),
  );
  const freshness = Math.max(0, 100 - (freshnessHours / 36) * 100);
  const momentum = Math.min(story.updateCount, 5) * 20;
  const techBoost = storyHasTechSignal(story) ? 14 : 0;
  const corroborationBoost = Math.min(story.sourceCount, 4) * 2.5;
  const total = 0.6 * story.importanceScore + 0.25 * freshness + 0.15 * momentum + techBoost + corroborationBoost;

  return {
    freshness: round(freshness),
    momentum: round(momentum),
    techBoost: round(techBoost),
    corroborationBoost: round(corroborationBoost),
    total: round(total),
    hasTechSignal: techBoost > 0,
  };
}

function storyFeedEligibility(story: PostgresStoryAuditRow) {
  if (story.representativeTrustScore !== null && story.representativeTrustScore < 0.6) {
    return "trust_below_threshold";
  }
  if (story.representativeSummaryLength < 20) {
    return "summary_too_short";
  }
  if (story.representativeContentLength < 20) {
    return "content_too_short";
  }
  if (story.representativeTrustScore !== null && story.representativeTrustScore >= 0.75) {
    return "eligible";
  }
  if (story.representativeTrustScore === null && story.sourceCount < 2 && story.updateCount < 2 && story.representativeSummaryLength < 30) {
    return "thin_untrusted_single_source";
  }
  if (story.representativeArticleScore < 5 && story.sourceCount < 2 && story.updateCount < 2) {
    return "low_score_single_source";
  }
  return "eligible";
}

function canUseConfiguredDatabase() {
  const databaseUrl = process.env.DATABASE_URL;
  if (!databaseUrl) {
    return false;
  }

  try {
    const url = new URL(databaseUrl);
    if (url.hostname === "db" && !fs.existsSync("/.dockerenv")) {
      return false;
    }
  } catch {
    return false;
  }

  return true;
}

async function auditPostgres(): Promise<PostgresAuditResult> {
  if (!canUseConfiguredDatabase() || !process.env.DATABASE_URL) {
    return {
      available: false,
      detail: "DATABASE_URL is missing or unusable from this shell; Postgres checks skipped.",
    };
  }

  const sql = postgres(process.env.DATABASE_URL, { prepare: false, max: 1 });
  try {
    const articles = await sql<PostgresArticleAuditRow[]>`
      select
        a.id,
        a.title,
        a.score,
        a.payload_json as "payloadJson",
        a.ingested_at as "ingestedAt",
        a.published_at as "publishedAt",
        s.slug as "sourceSlug"
      from articles a
      join sources s on s.id = a.source_id
      order by a.ingested_at desc
      limit 5
    `;
    const stories = await sql<PostgresStoryAuditRow[]>`
      select
        st.id,
        st.canonical_headline as "canonicalHeadline",
        st.importance_score as "importanceScore",
        st.last_updated_at as "lastUpdatedAt",
        st.source_count as "sourceCount",
        st.update_count as "updateCount",
        coalesce(rs.slug, '') as "representativeSourceSlug",
        coalesce(rs.name, '') as "representativeSourceName",
        ra.score as "representativeArticleScore",
        char_length(trim(ra.summary)) as "representativeSummaryLength",
        char_length(trim(ra.content_text)) as "representativeContentLength",
        case
          when jsonb_typeof(ra.payload_json -> 'collector') = 'object'
            and jsonb_typeof((ra.payload_json -> 'collector') -> 'trust_score') = 'number'
          then ((ra.payload_json -> 'collector') ->> 'trust_score')::double precision
          else null
        end as "representativeTrustScore",
        coalesce(
          array_remove(array_agg(distinct tp.slug), null),
          '{}'::text[]
        ) as "topicSlugs"
      from stories st
      left join articles ra on ra.id = st.representative_article_id
      left join sources rs on rs.id = ra.source_id
      left join story_articles sa on sa.story_id = st.id
      left join article_topics at on at.article_id = sa.article_id
      left join topics tp on tp.id = at.topic_id
      group by
        st.id,
        rs.slug,
        rs.name,
        ra.score,
        ra.summary,
        ra.content_text,
        ra.payload_json
      order by last_updated_at desc
      limit 5
    `;
    const feedItems = await sql<PostgresFeedAuditRow[]>`
      select
        dfr.feed_date as "feedDate",
        dfi.story_id as "storyId",
        dfi.section,
        dfi.rank_position as "rankPosition",
        dfi.rank_score as "rankScore",
        st.canonical_headline as "canonicalHeadline"
      from daily_feed_items dfi
      join daily_feed_runs dfr on dfr.id = dfi.feed_run_id
      join stories st on st.id = dfi.story_id
      order by dfr.feed_date desc, dfi.section asc, dfi.rank_position asc
      limit 12
    `;

    return { available: true, articles, stories, feedItems };
  } finally {
    await sql.end();
  }
}

function collectorScoreAuditRows(
  articles: Array<{
    title: string;
    score: number;
    payloadJson: Record<string, unknown> | null;
    publishedAt: string;
    sourceSlug: string;
  }>,
) {
  return articles.map((article) => {
    const collector = article.payloadJson?.collector;
    if (!collector || typeof collector !== "object") {
      return {
        title: article.title,
        status: "stored",
        detail: `source=${article.sourceSlug} app_score=${article.score} (non-collector payload)`,
      } satisfies AuditRow;
    }
    const payload = collector as Record<string, unknown>;

    const trustScore = typeof payload.trust_score === "number" ? payload.trust_score : null;
    const expected =
      trustScore === null
        ? null
        : collectorImportanceToArticleScore({
            publishedAt: article.publishedAt,
            trustScore,
            engagement: payload.engagement && typeof payload.engagement === "object" ? (payload.engagement as Record<string, unknown>) : null,
            symbols: Array.isArray(payload.symbols) ? payload.symbols : [],
          });
    const collectorScore =
      typeof payload.importance_score === "number" ? payload.importance_score : null;
    return {
      title: article.title,
      status: expected === article.score ? "ok" : "check",
      detail: `source=${article.sourceSlug} app_score=${article.score} expected=${expected ?? "n/a"} collector_ref=${collectorScore ?? "n/a"}`,
    } satisfies AuditRow;
  });
}

function storyRankingAuditRows(stories: PostgresStoryAuditRow[], feedItems: PostgresFeedAuditRow[]) {
  const latestFeedDate = feedItems[0]?.feedDate;
  if (!latestFeedDate) {
    return [] as AuditRow[];
  }

  const rankedStoryIds = new Set(feedItems.map((item) => item.storyId));
  const referenceDate = feedReferenceDate(latestFeedDate).toISOString();
  return stories.map((story) => {
    const components = computeStoryAudit(story, referenceDate);
    const feedItem = feedItems.find((item) => item.storyId === story.id);
    const rankMatch = feedItem ? round(feedItem.rankScore) === components.total : false;
    const eligibility = storyFeedEligibility(story);
    return {
      title: story.canonicalHeadline,
      status: feedItem ? (rankMatch ? "ok" : "check") : rankedStoryIds.size > 0 ? "check" : "stored",
      detail: [
        `importance=${round(story.importanceScore)}`,
        `freshness=${components.freshness}`,
        `momentum=${components.momentum}`,
        `techBoost=${components.techBoost}${components.hasTechSignal ? " (tech-signal)" : ""}`,
        `corroboration=${components.corroborationBoost}`,
        `expected_rank=${components.total}`,
        feedItem ? `stored_rank=${round(feedItem.rankScore)}` : "not_in_latest_feed",
        `eligibility=${eligibility}`,
        `feed_date=${normalizeFeedDateKey(latestFeedDate)}`,
        `topics=${story.topicSlugs.join(",") || "none"}`,
        `rep_source=${story.representativeSourceSlug || "unknown"}`,
      ].join(" "),
    } satisfies AuditRow;
  });
}

async function main() {
  printSection("Preflight");
  console.log(`- collector python: ${pythonBin}`);
  console.log(`- collector db: ${collectorDbPath}`);
  console.log(`- collector output: ${collectorOutputDir}`);
  console.log(`- app url: ${appUrl}`);

  const appProbe = await probeApp();
  console.log(`- app reachability: ${appProbe.reachable ? "ok" : "skip"}${appProbe.detail ? ` (${appProbe.detail})` : ""}`);

  printSection("Source Audit");
  const liveTest = await runPythonQuery(`
import json
import signal
from news_collector.runtime import build_runtime

class TimeoutError(Exception):
    pass

def handler(signum, frame):
    raise TimeoutError("timed out")

signal.signal(signal.SIGALRM, handler)
_settings, _config, _repository, collectors = build_runtime()
results = []
for collector in collectors:
    try:
        signal.alarm(25)
        result = collector.run(force=True)
        signal.alarm(0)
        results.append({
            "collector": collector.name,
            "status": result.status,
            "reason": result.reason,
            "items": len(result.items),
            "sample_title": result.items[0].title if result.items else None,
        })
    except Exception as exc:
        signal.alarm(0)
        results.append({
            "collector": collector.name,
            "status": "error",
            "reason": str(exc),
            "items": 0,
            "sample_title": None,
        })
print(json.dumps(results))
`);
  console.log(JSON.stringify(liveTest, null, 2));

  printSection("Collect");
  const collect = await runPythonModule("news_collector.jobs.collect");
  console.log(collect.stdout.trim());
  const collectRows = (await runPythonQuery(`
import json
import os
import sqlite3

conn = sqlite3.connect(os.environ["AUDIT_COLLECTOR_DB_PATH"])
conn.row_factory = sqlite3.Row
payload = {
  "raw_items": [dict(row) for row in conn.execute("select id, source, category, title, published_at from raw_items order by id desc limit 5")],
  "normalized_items": [dict(row) for row in conn.execute("select id, source, category, importance_score, title from normalized_items order by id desc limit 5")],
  "clusters": [dict(row) for row in conn.execute("select cluster_id, category, score, confirmation_count, title from story_clusters order by score desc limit 5")],
}
print(json.dumps(payload))
`)) as {
    raw_items: Array<Record<string, unknown>>;
    normalized_items: Array<Record<string, unknown>>;
    clusters: Array<Record<string, unknown>>;
  };
  console.log(`- latest raw_items: ${JSON.stringify(collectRows.raw_items, null, 2)}`);
  console.log(`- latest normalized_items: ${JSON.stringify(collectRows.normalized_items, null, 2)}`);
  console.log(`- top story_clusters: ${JSON.stringify(collectRows.clusters, null, 2)}`);

  printSection("Digest");
  const digest = await runPythonModule("news_collector.jobs.digest");
  console.log(digest.stdout.trim());
  const latestDigestDir =
    typeof digest.json?.output_dir === "string" ? digest.json.output_dir : latestPathIn(collectorOutputDir);
  if (latestDigestDir) {
    const digestJsonPath = path.join(latestDigestDir, "digest.json");
    if (fs.existsSync(digestJsonPath)) {
      const digestJson = await readJson(digestJsonPath);
      console.log(`- digest path: ${digestJsonPath}`);
      console.log(
        `- digest summary: ${JSON.stringify(
          {
            digest_date: digestJson.digest_date,
            top_tech: Array.isArray(digestJson.top_tech) ? digestJson.top_tech.length : 0,
            top_world_politics: Array.isArray(digestJson.top_world_politics)
              ? digestJson.top_world_politics.length
              : 0,
            top_finance: Array.isArray(digestJson.top_finance) ? digestJson.top_finance.length : 0,
            rising_stories: Array.isArray(digestJson.rising_stories) ? digestJson.rising_stories.length : 0,
          },
          null,
          2,
        )}`,
      );
    }
  }

  let latestPublishedStoryId: string | null = null;

  if (appProbe.reachable) {
    printSection("Publish");
    const publish = await runPythonModule("news_collector.jobs.publish");
    console.log(publish.stdout.trim());
    const outboxDir =
      Array.isArray(publish.json?.outbox_dirs) && typeof publish.json.outbox_dirs.at(-1) === "string"
        ? String(publish.json.outbox_dirs.at(-1))
        : latestPathIn(syncOutboxDir);
    if (outboxDir) {
      const manifestPath = path.join(outboxDir, "manifest.json");
      const articlesPath = path.join(outboxDir, "articles.json");
      if (fs.existsSync(manifestPath)) {
        console.log(`- latest outbox manifest: ${manifestPath}`);
        console.log(`- manifest: ${JSON.stringify(await readJson(manifestPath), null, 2)}`);
      }
      if (fs.existsSync(articlesPath)) {
        const payload = await readJson(articlesPath);
        const firstArticle = Array.isArray(payload.articles) ? payload.articles[0] : null;
        console.log(`- first published payload: ${JSON.stringify(firstArticle, null, 2)}`);
      }
    }
  } else {
    printSection("Publish");
    console.log("- skipped because the local app is not reachable; app/db/ui stages were not executed.");
  }

  printSection("App Storage");
  const postgresAudit = await auditPostgres();
  if (!postgresAudit.available) {
    console.log(`- ${postgresAudit.detail}`);
  } else {
    const articles = postgresAudit.articles;
    const stories = postgresAudit.stories;
    const feedItems = postgresAudit.feedItems;
    printRows(collectorScoreAuditRows(articles));
    printRows(storyRankingAuditRows(stories, feedItems));
    console.log(`- latest stories: ${JSON.stringify(stories, null, 2)}`);
    console.log(`- latest feed items: ${JSON.stringify(feedItems, null, 2)}`);
    latestPublishedStoryId = feedItems[0]?.storyId ?? null;
  }

  printSection("HTTP Feed");
  if (!appProbe.reachable) {
    console.log("- skipped because the local app is not reachable.");
  } else {
    const todayResponse = await fetch(`${appUrl}/api/feed/today`);
    const catchupResponse = await fetch(`${appUrl}/api/feed/catchup`);
    const today = (await todayResponse.json()) as Record<string, unknown>;
    const catchup = (await catchupResponse.json()) as Record<string, unknown>;
    console.log(`- /api/feed/today: ${JSON.stringify(today, null, 2)}`);
    console.log(`- /api/feed/catchup: ${JSON.stringify(catchup, null, 2)}`);

    const firstTodayStory =
      Array.isArray(today.important) && today.important[0] && typeof today.important[0] === "object"
        ? (today.important[0] as Record<string, unknown>)
        : Array.isArray(today.other) && today.other[0] && typeof today.other[0] === "object"
          ? (today.other[0] as Record<string, unknown>)
          : null;
    const storyId =
      (typeof firstTodayStory?.id === "string" ? firstTodayStory.id : null) ?? latestPublishedStoryId;
    if (storyId) {
      const storyResponse = await fetch(`${appUrl}/api/stories/${storyId}`);
      console.log(`- /api/stories/${storyId}: ${JSON.stringify(await storyResponse.json(), null, 2)}`);
      console.log(`- browser review: ${appUrl}/`);
      console.log(`- browser review: ${appUrl}/story/${storyId}`);
      const topics = Array.isArray(firstTodayStory?.topics) ? firstTodayStory.topics : [];
      const firstTopic =
        topics.find((topic) => typeof topic === "object" && topic && typeof (topic as Record<string, unknown>).slug === "string") as
          | Record<string, unknown>
          | undefined;
      if (firstTopic?.slug) {
        console.log(`- browser review: ${appUrl}/topics/${firstTopic.slug}`);
      }
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
