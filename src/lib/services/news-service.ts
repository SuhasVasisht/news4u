import crypto from "node:crypto";
import { and, asc, desc, eq, inArray, isNotNull, lt } from "drizzle-orm";
import { auth } from "@/auth";
import { getDb, hasDatabase } from "@/lib/db/client";
import { collectorImportanceToArticleScore } from "@/lib/scoring";
import {
  articleTopics,
  articles,
  dailyFeedItems,
  dailyFeedRuns,
  sources,
  stories,
  storyArticles,
  topics,
  userDailyFeedItems,
  userDailyFeeds,
  userPreferences,
  userSourcePreferences,
  userStoryState,
  userTopicPreferences,
  users,
} from "@/lib/db/schema";
import { mockAppPreferences, mockSources, mockTopics, sampleSyncPayload } from "@/lib/mock-data";
import type {
  AppPreferences,
  ArchivedFeedResponse,
  CatchupFeedResponse,
  CatchupGroup,
  LocalStoryStateInput,
  SavedFeedResponse,
  ShellData,
  StoryCard,
  StoryDetail,
  SyncArticleInput,
  TodayFeedResponse,
  UserPreferences,
  ViewerStoryState,
} from "@/lib/types";

const ALGORITHM_VERSION = "v2";
const IMPORTANT_LIMIT = 8;
const OTHER_LIMIT = 20;
const CATCHUP_TOTAL_LIMIT = 8;
const CATCHUP_PER_DAY_LIMIT = 3;
const MAX_CARRYOVERS = 2;
const APP_TIMEZONE = process.env.APP_TIMEZONE ?? "America/Los_Angeles";
const APP_DAILY_RESET_HOUR = Number(process.env.APP_DAILY_RESET_HOUR ?? 5);
const TECH_TOPIC_SLUGS = new Set(["technology", "ai", "artificial-intelligence", "startups", "devtools", "cloud", "semiconductors"]);
const TECH_SOURCE_HINTS = ["tech", "ai", "dev", "cloud", "data", "chip", "startup", "hacker", "product"];

type Viewer = {
  id: string | null;
  name: string | null;
  email: string | null;
  image: string | null;
  isAuthenticated: boolean;
};

type UserDailyFeedRecord = {
  id: string;
  userId: string;
  feedDate: string;
  generatedFromFeedRunId: string;
  createdAt: string;
  clearedAt: string | null;
  status: string;
};

type MemoryStore = {
  initialized: boolean;
  users: Array<{ id: string; name: string | null; email: string | null; image: string | null }>;
  sources: typeof mockSources;
  topics: typeof mockTopics;
  sourcePrefs: Array<{ userId: string; sourceId: string; isHidden: boolean }>;
  topicPrefs: Array<{ userId: string; topicId: string; isMuted: boolean }>;
  prefs: Array<{ userId: string } & UserPreferences>;
  stories: Array<{
    id: string;
    canonicalHeadline: string;
    canonicalSummary: string;
    normalizedHeadline: string;
    fingerprint: string;
    status: string;
    firstPublishedAt: string;
    lastUpdatedAt: string;
    importanceScore: number;
    updateCount: number;
    sourceCount: number;
    representativeArticleId: string | null;
    searchDocument: string;
    createdAt: string;
    updatedAt: string;
  }>;
  articles: Array<{
    id: string;
    sourceId: string;
    storyId: string;
    externalId: string;
    title: string;
    summary: string;
    author: string | null;
    url: string;
    imageUrl: string | null;
    publishedAt: string;
    ingestedAt: string;
    contentText: string;
    score: number;
    payloadJson: Record<string, unknown> | null;
  }>;
  articleTopics: Array<{ articleId: string; topicId: string }>;
  runs: Array<{ id: string; feedDate: string; generatedAt: string; algorithmVersion: string; notes: string | null }>;
  runItems: Array<{
    id: string;
    feedRunId: string;
    storyId: string;
    section: string;
    rankScore: number;
    rankPosition: number;
    compactSummary: string | null;
    reasonJson: null;
    feedDate: string;
  }>;
  userDailyFeeds: Array<UserDailyFeedRecord>;
  userDailyFeedItems: Array<{
    id: string;
    userDailyFeedId: string;
    storyId: string;
    tab: string;
    section: string;
    rankPosition: number;
    isRead: boolean;
    isDismissed: boolean;
    isArchived: boolean;
    summaryOverride: string | null;
  }>;
  state: Array<{
    userId: string;
    storyId: string;
    firstSeenAt: string;
    lastSeenAt: string;
    lastReadAt: string | null;
    isRead: boolean;
    isSaved: boolean;
    isArchived: boolean;
    isDismissed: boolean;
    carryoverCount: number;
    archivedAt: string | null;
  }>;
};

declare global {
  var __memoryNewsStore__: MemoryStore | undefined;
}

function memoryStore(): MemoryStore {
  if (!globalThis.__memoryNewsStore__) {
    globalThis.__memoryNewsStore__ = {
      initialized: false,
      users: [],
      sources: structuredClone(mockSources),
      topics: structuredClone(mockTopics),
      sourcePrefs: [],
      topicPrefs: [],
      prefs: [],
      stories: [],
      articles: [],
      articleTopics: [],
      runs: [],
      runItems: [],
      userDailyFeeds: [],
      userDailyFeedItems: [],
      state: [],
    };
  }

  return globalThis.__memoryNewsStore__;
}

function uuid() {
  return crypto.randomUUID();
}

function normalizedParts(date = new Date(), timeZone = APP_TIMEZONE) {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  const parts = Object.fromEntries(formatter.formatToParts(date).map((part) => [part.type, part.value]));
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hour: Number(parts.hour),
  };
}

function toDateKey(parts: { year: number; month: number; day: number }) {
  return `${parts.year}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}`;
}

function addDays(dateKey: string, delta: number) {
  const [year, month, day] = dateKey.split("-").map(Number);
  const next = new Date(Date.UTC(year, month - 1, day + delta));
  return `${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, "0")}-${String(next.getUTCDate()).padStart(2, "0")}`;
}

function feedReferenceDate(feedDate: string) {
  const boundaryDateKey = addDays(feedDate, 1);
  const [year, month, day] = boundaryDateKey.split("-").map(Number);
  let guess = new Date(Date.UTC(year, month - 1, day, APP_DAILY_RESET_HOUR, 0, 0, 0));

  for (let index = 0; index < 4; index += 1) {
    const parts = normalizedParts(guess);
    const targetLocalAsUtc = Date.UTC(year, month - 1, day, APP_DAILY_RESET_HOUR, 0, 0, 0);
    const currentLocalAsUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, 0, 0, 0);
    const diff = targetLocalAsUtc - currentLocalAsUtc;
    if (diff === 0) {
      break;
    }
    guess = new Date(guess.getTime() + diff);
  }

  return new Date(guess.getTime() - 1);
}

export function currentFeedDate(now = new Date()) {
  const parts = normalizedParts(now);
  const today = toDateKey(parts);
  return parts.hour < APP_DAILY_RESET_HOUR ? addDays(today, -1) : today;
}

function compactSummary(value: string) {
  const sentence = value.split(".")[0]?.trim();
  const candidate = sentence?.length ? `${sentence}.` : value.trim();
  if (candidate.length <= 160) {
    return candidate;
  }

  return `${candidate.slice(0, 157).trimEnd().replace(/[^\w]+$/, "")}...`;
}

function normalizedIncomingScore(score: number | null | undefined) {
  return score ?? 5;
}

function collectorPayload(input: SyncArticleInput) {
  const collector = input.payload_json?.collector;
  if (!collector || typeof collector !== "object") {
    return null;
  }
  const payload = collector as Record<string, unknown>;

  const trustScore = payload.trust_score;
  if (typeof trustScore !== "number") {
    return null;
  }

  return {
    trustScore,
    engagement: payload.engagement && typeof payload.engagement === "object" ? (payload.engagement as Record<string, unknown>) : null,
    symbols: Array.isArray(payload.symbols) ? payload.symbols : [],
  };
}

function collectorTrustScore(payloadJson: Record<string, unknown> | null | undefined) {
  const collector = payloadJson?.collector;
  if (!collector || typeof collector !== "object") {
    return null;
  }
  const trustScore = (collector as Record<string, unknown>).trust_score;
  return typeof trustScore === "number" ? trustScore : null;
}

function incomingArticleScore(input: SyncArticleInput) {
  const collector = collectorPayload(input);
  if (collector) {
    return collectorImportanceToArticleScore({
      publishedAt: input.published_at,
      trustScore: collector.trustScore,
      engagement: collector.engagement,
      symbols: collector.symbols,
    });
  }

  return normalizedIncomingScore(input.score);
}

function normalizeTitle(title: string) {
  return title
    .toLowerCase()
    .replace(/\s+-\s+[a-z0-9 .]+$/i, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\b(the|a|an|to|from|into|for|of|and|or|on|in|with|without|another)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function storyFingerprint(title: string) {
  return normalizeTitle(title).split(" ").slice(0, 6).join("-");
}

function diceCoefficient(left: string, right: string) {
  const a = left.split(" ");
  const b = right.split(" ");
  const shared = a.filter((token) => b.includes(token)).length;
  if (a.length + b.length === 0) {
    return 0;
  }

  return (2 * shared) / (a.length + b.length);
}

async function getViewer(): Promise<Viewer> {
  const session = await auth();
  return {
    id: session?.user?.id ?? null,
    name: session?.user?.name ?? null,
    email: session?.user?.email ?? null,
    image: session?.user?.image ?? null,
    isAuthenticated: Boolean(session?.user?.id),
  };
}

function defaultViewerState(storyId: string): ViewerStoryState {
  return {
    storyId,
    isRead: false,
    lastReadAt: null,
    isSaved: false,
    isArchived: false,
    isDismissed: false,
  };
}

async function ensureMemorySeeded() {
  const store = memoryStore();
  if (store.initialized) {
    return;
  }

  for (const item of sampleSyncPayload) {
    const source = store.sources.find((entry) => entry.slug === item.source.slug)!;
    const articleId = uuid();
    const now = new Date().toISOString();
    const normalized = normalizeTitle(item.title);
    const fingerprint = storyFingerprint(item.title);
    const topicIds = item.topics.map((topic) => store.topics.find((entry) => entry.slug === topic.slug)?.id).filter(Boolean) as string[];
    const matchedStory = store.stories.find((story) => {
      const overlap = store.articleTopics
        .filter((entry) => store.articles.find((article) => article.id === entry.articleId)?.storyId === story.id)
        .some((entry) => topicIds.includes(entry.topicId));
      return story.fingerprint === fingerprint || (overlap && diceCoefficient(story.normalizedHeadline, normalized) >= 0.72);
    });

    let storyId = matchedStory?.id;
    if (!storyId) {
      storyId = uuid();
      store.stories.push({
        id: storyId,
        canonicalHeadline: item.title,
        canonicalSummary: item.summary,
        normalizedHeadline: normalized,
        fingerprint,
        status: "active",
        firstPublishedAt: item.published_at,
        lastUpdatedAt: item.published_at,
        importanceScore: (item.score ?? 0) * 10,
        updateCount: 1,
        sourceCount: 1,
        representativeArticleId: articleId,
        searchDocument: `${item.title} ${item.summary} ${item.content_text}`,
        createdAt: now,
        updatedAt: now,
      });
    }

    store.articles.push({
      id: articleId,
      sourceId: source.id,
      storyId,
      externalId: item.external_id,
      title: item.title,
      summary: item.summary,
      author: item.author ?? null,
      url: item.url,
      imageUrl: item.image_url ?? null,
      publishedAt: item.published_at,
      ingestedAt: now,
      contentText: item.content_text,
      score: item.score ?? 0,
      payloadJson: item.payload_json ?? null,
    });
    store.articleTopics.push(...topicIds.map((topicId) => ({ articleId, topicId })));
  }

  recomputeMemoryStoryRollups();
  store.initialized = true;
}

function recomputeMemoryStoryRollups() {
  const store = memoryStore();
  for (const story of store.stories) {
    const storyArticlesForStory = store.articles
      .filter((article) => article.storyId === story.id)
      .sort((left, right) => +new Date(right.publishedAt) - +new Date(left.publishedAt));
    const representative = [...storyArticlesForStory].sort(
      (left, right) =>
        right.score - left.score || +new Date(right.publishedAt) - +new Date(left.publishedAt),
    )[0];
    const sourceIds = new Set(storyArticlesForStory.map((article) => article.sourceId));
    story.canonicalHeadline = representative?.title ?? story.canonicalHeadline;
    story.canonicalSummary = representative?.summary ?? story.canonicalSummary;
    story.normalizedHeadline = normalizeTitle(story.canonicalHeadline);
    story.fingerprint = storyFingerprint(story.canonicalHeadline);
    story.firstPublishedAt = storyArticlesForStory.at(-1)?.publishedAt ?? story.firstPublishedAt;
    story.lastUpdatedAt = storyArticlesForStory[0]?.publishedAt ?? story.lastUpdatedAt;
    story.importanceScore = Math.max(...storyArticlesForStory.map((article) => article.score * 10), 0);
    story.updateCount = storyArticlesForStory.filter(
      (article) => +new Date(article.publishedAt) >= Date.now() - 48 * 60 * 60 * 1000,
    ).length;
    story.sourceCount = sourceIds.size;
    story.representativeArticleId = representative?.id ?? story.representativeArticleId;
    story.searchDocument = storyArticlesForStory
      .map((article) => `${article.title} ${article.summary} ${article.contentText}`)
      .join(" ");
    story.updatedAt = new Date().toISOString();
  }
}

async function withStore<T>(runDb: () => Promise<T>, runMemory: () => Promise<T>) {
  if (!hasDatabase) {
    return runMemory();
  }

  try {
    return await runDb();
  } catch (error) {
    if (error instanceof Error && /connect|ECONNREFUSED|ENOTFOUND/i.test(error.message)) {
      return runMemory();
    }
    throw error;
  }
}

async function upsertUser(viewer: Viewer) {
  if (!viewer.id) {
    return;
  }
  const viewerId = viewer.id;

  await withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return;
      }

      await db
        .insert(users)
        .values({
          id: viewerId,
          name: viewer.name,
          email: viewer.email,
          image: viewer.image,
          updatedAt: new Date(),
          lastLoginAt: new Date(),
        })
        .onConflictDoUpdate({
          target: users.id,
          set: {
            name: viewer.name,
            email: viewer.email,
            image: viewer.image,
            updatedAt: new Date(),
            lastLoginAt: new Date(),
          },
        });
    },
    async () => {
      const store = memoryStore();
      if (!store.users.find((entry) => entry.id === viewerId)) {
        store.users.push({
          id: viewerId,
          name: viewer.name,
          email: viewer.email,
          image: viewer.image,
        });
      }
    },
  );
}

type HydratedStory = StoryCard & { searchDocument?: string };
type FeedRunRecord = {
  id: string;
  feedDate: string;
  generatedAt: string;
  algorithmVersion: string;
  notes: string | null;
};

type GenerateDailyFeedOptions = {
  feedDate?: string;
  forceRefresh?: boolean;
};

type RankedStoryEntry<TStory> = {
  story: TStory;
  score: number;
};

type RankableStory = {
  id: string;
  canonicalSummary: string;
  importanceScore: number;
  lastUpdatedAt: string | Date;
  updateCount: number;
  sourceCount: number;
  topicSlugs: string[];
  representativeSourceSlug: string;
  representativeSourceName: string;
  representativeArticleScore: number;
  representativeSummaryLength: number;
  representativeContentLength: number;
  representativeTrustScore: number | null;
};

type RunItemSeed = {
  section: string;
  storyId: string;
  rankPosition: number;
  rankScore: number;
  compactSummary: string | null;
};

async function hydrateStoriesByIds(storyIds: string[], viewerId: string | null): Promise<HydratedStory[]> {
  if (storyIds.length === 0) {
    return [];
  }

  return withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return [];
      }

      const [storyRows, articleRows, sourceRows, topicRows, articleTopicRows, stateRows] = await Promise.all([
        db.select().from(stories).where(inArray(stories.id, storyIds)),
        db.select().from(articles).where(inArray(articles.storyId, storyIds)),
        db.select().from(sources),
        db.select().from(topics),
        db.select().from(articleTopics),
        viewerId
          ? db.select().from(userStoryState).where(eq(userStoryState.userId, viewerId))
          : Promise.resolve([]),
      ]);

      const topicMap = new Map(topicRows.map((row) => [row.id, row]));
      const sourceMap = new Map(sourceRows.map((row) => [row.id, row]));
      const stateMap = new Map(stateRows.map((row) => [row.storyId, row]));
      const topicsByArticle = new Map<string, string[]>();

      for (const join of articleTopicRows) {
        const current = topicsByArticle.get(join.articleId) ?? [];
        current.push(join.topicId);
        topicsByArticle.set(join.articleId, current);
      }

      const articlesByStory = new Map<string, typeof articleRows>();
      for (const article of articleRows) {
        if (!article.storyId) {
          continue;
        }
        const current = articlesByStory.get(article.storyId) ?? [];
        current.push(article);
        articlesByStory.set(article.storyId, current);
      }

      return storyIds
        .map((storyId) => {
          const story = storyRows.find((row) => row.id === storyId);
          if (!story) {
            return null;
          }

          const articlesForStory = (articlesByStory.get(story.id) ?? [])
            .sort((left, right) => +new Date(right.publishedAt) - +new Date(left.publishedAt))
            .map((article) => ({
              id: article.id,
              externalId: article.externalId,
              title: article.title,
              summary: article.summary,
              author: article.author,
              url: article.url,
              imageUrl: article.imageUrl,
              publishedAt: article.publishedAt.toISOString(),
              contentText: article.contentText,
              score: article.score,
              source: {
                id: sourceMap.get(article.sourceId)?.id ?? "",
                slug: sourceMap.get(article.sourceId)?.slug ?? "",
                name: sourceMap.get(article.sourceId)?.name ?? "Unknown",
                homepageUrl: sourceMap.get(article.sourceId)?.homepageUrl ?? null,
                iconUrl: sourceMap.get(article.sourceId)?.iconUrl ?? null,
              },
            }));

          const topicIds = new Set(
            articlesForStory.flatMap((article) => topicsByArticle.get(article.id) ?? []),
          );
          const representative =
            articlesForStory.find((article) => article.id === story.representativeArticleId) ?? articlesForStory[0];
          const state = stateMap.get(story.id);

          return {
            id: story.id,
            canonicalHeadline: story.canonicalHeadline,
            canonicalSummary: story.canonicalSummary,
            compactSummary: compactSummary(story.canonicalSummary),
            importanceScore: story.importanceScore,
            updatedAt: story.lastUpdatedAt.toISOString(),
            sourceCount: story.sourceCount,
            topics: [...topicIds]
              .map((topicId) => topicMap.get(topicId))
              .filter(Boolean)
              .map((topic) => ({
                id: topic!.id,
                slug: topic!.slug,
                name: topic!.name,
              })),
            representativeArticle: representative,
            articles: articlesForStory,
            viewerState: state
              ? {
                  storyId: story.id,
                  isRead: state.isRead,
                  lastReadAt: state.lastReadAt?.toISOString() ?? null,
                  isSaved: state.isSaved,
                  isArchived: state.isArchived,
                  isDismissed: state.isDismissed,
                }
              : defaultViewerState(story.id),
            searchDocument: story.searchDocument,
          } satisfies HydratedStory;
        })
        .filter(Boolean) as HydratedStory[];
    },
    async () => {
      await ensureMemorySeeded();
      const store = memoryStore();
      const stateMap = new Map(
        store.state.filter((entry) => entry.userId === viewerId).map((entry) => [entry.storyId, entry]),
      );
      return storyIds
        .map((storyId) => {
          const story = store.stories.find((entry) => entry.id === storyId);
          if (!story) {
            return null;
          }

          const articlesForStory = store.articles
            .filter((article) => article.storyId === story.id)
            .sort((left, right) => +new Date(right.publishedAt) - +new Date(left.publishedAt))
            .map((article) => {
              const source = store.sources.find((entry) => entry.id === article.sourceId)!;
              return {
                id: article.id,
                externalId: article.externalId,
                title: article.title,
                summary: article.summary,
                author: article.author,
                url: article.url,
                imageUrl: article.imageUrl,
                publishedAt: article.publishedAt,
                contentText: article.contentText,
                score: article.score,
                source,
              };
            });
          const topicIds = new Set(
            store.articleTopics
              .filter((entry) => articlesForStory.some((article) => article.id === entry.articleId))
              .map((entry) => entry.topicId),
          );
          const representative =
            articlesForStory.find((article) => article.id === story.representativeArticleId) ?? articlesForStory[0];
          const state = stateMap.get(story.id);

          return {
            id: story.id,
            canonicalHeadline: story.canonicalHeadline,
            canonicalSummary: story.canonicalSummary,
            compactSummary: compactSummary(story.canonicalSummary),
            importanceScore: story.importanceScore,
            updatedAt: story.lastUpdatedAt,
            sourceCount: story.sourceCount,
            topics: [...topicIds]
              .map((topicId) => store.topics.find((entry) => entry.id === topicId))
              .filter(Boolean) as typeof mockTopics,
            representativeArticle: representative,
            articles: articlesForStory,
            viewerState: state
              ? {
                  storyId: story.id,
                  isRead: state.isRead,
                  lastReadAt: state.lastReadAt,
                  isSaved: state.isSaved,
                  isArchived: state.isArchived,
                  isDismissed: state.isDismissed,
                }
              : defaultViewerState(story.id),
            searchDocument: story.searchDocument,
          } satisfies HydratedStory;
        })
        .filter(Boolean) as HydratedStory[];
    },
  );
}

function scoreStory(
  story: { importanceScore: number; lastUpdatedAt: string | Date; updateCount: number },
  referenceDate = new Date(),
) {
  const freshnessHours = Math.max(
    0,
    (referenceDate.getTime() - +new Date(story.lastUpdatedAt)) / (60 * 60 * 1000),
  );
  const freshness = Math.max(0, 100 - (freshnessHours / 36) * 100);
  const momentum = Math.min(story.updateCount, 5) * 20;
  const techBoost = "topicSlugs" in story && storyHasTechSignal(story as RankableStory) ? 14 : 0;
  const corroborationBoost = "sourceCount" in story && typeof story.sourceCount === "number" ? Math.min(story.sourceCount, 4) * 2.5 : 0;
  return 0.6 * story.importanceScore + 0.25 * freshness + 0.15 * momentum + techBoost + corroborationBoost;
}

function storyHasTechSignal(story: RankableStory) {
  return (
    story.topicSlugs.some((slug) => TECH_TOPIC_SLUGS.has(slug)) ||
    TECH_SOURCE_HINTS.some(
      (token) =>
        story.representativeSourceSlug.toLowerCase().includes(token) ||
        story.representativeSourceName.toLowerCase().includes(token),
    )
  );
}

function isStoryFeedEligible(story: RankableStory) {
  if (story.representativeTrustScore !== null && story.representativeTrustScore < 0.6) {
    return false;
  }
  if (story.representativeSummaryLength < 20) {
    return false;
  }
  if (story.representativeContentLength < 20) {
    return false;
  }
  if (story.representativeTrustScore !== null && story.representativeTrustScore >= 0.75) {
    return true;
  }
  if (story.representativeTrustScore === null && story.sourceCount < 2 && story.updateCount < 2 && story.representativeSummaryLength < 30) {
    return false;
  }
  if (story.representativeArticleScore < 5 && story.sourceCount < 2 && story.updateCount < 2) {
    return false;
  }
  return true;
}

function buildRunItemSeeds<TStory extends RankableStory>(
  eligible: Array<RankedStoryEntry<TStory>>,
  feedDate: string,
  referenceDate = feedReferenceDate(feedDate),
) {
  const currentThreshold = referenceDate.getTime() - 24 * 60 * 60 * 1000;
  const important = eligible
    .filter((entry) => isStoryFeedEligible(entry.story) && +new Date(entry.story.lastUpdatedAt) >= currentThreshold && entry.score >= 70)
    .slice(0, IMPORTANT_LIMIT);
  const other = eligible
    .filter(
      (entry) =>
        isStoryFeedEligible(entry.story) &&
        +new Date(entry.story.lastUpdatedAt) >= currentThreshold &&
        entry.score >= 45 &&
        !important.some((item) => item.story.id === entry.story.id),
    )
    .slice(0, OTHER_LIMIT);
  const catchup = eligible
    .filter((entry) => isStoryFeedEligible(entry.story) && +new Date(entry.story.lastUpdatedAt) < currentThreshold && entry.score >= 55)
    .slice(0, CATCHUP_TOTAL_LIMIT);

  return [
    ...important.map((entry, index) => ({
      storyId: entry.story.id,
      section: "today_important",
      rankPosition: index + 1,
      rankScore: entry.score,
      compactSummary: compactSummary(entry.story.canonicalSummary),
    })),
    ...other.map((entry, index) => ({
      storyId: entry.story.id,
      section: "today_other",
      rankPosition: index + 1,
      rankScore: entry.score,
      compactSummary: compactSummary(entry.story.canonicalSummary),
    })),
    ...catchup.map((entry, index) => ({
      storyId: entry.story.id,
      section: "catchup_candidate",
      rankPosition: index + 1,
      rankScore: entry.score,
      compactSummary: compactSummary(entry.story.canonicalSummary),
    })),
  ] satisfies RunItemSeed[];
}

async function loadDbRankableStories(): Promise<RankableStory[]> {
  const db = getDb();
  if (!db) {
    return [];
  }

  const [storyRows, articleRows, sourceRows, topicRows, articleTopicRows] = await Promise.all([
    db.select().from(stories),
    db.select().from(articles).where(isNotNull(articles.storyId)),
    db.select().from(sources),
    db.select().from(topics),
    db.select().from(articleTopics),
  ]);

  const sourceMap = new Map(sourceRows.map((row) => [row.id, row]));
  const topicMap = new Map(topicRows.map((row) => [row.id, row.slug]));
  const topicsByArticle = new Map<string, string[]>();
  for (const join of articleTopicRows) {
    const slug = topicMap.get(join.topicId);
    if (!slug) {
      continue;
    }
    const current = topicsByArticle.get(join.articleId) ?? [];
    current.push(slug);
    topicsByArticle.set(join.articleId, current);
  }

  const articlesByStory = new Map<string, typeof articleRows>();
  for (const article of articleRows) {
    if (!article.storyId) {
      continue;
    }
    const current = articlesByStory.get(article.storyId) ?? [];
    current.push(article);
    articlesByStory.set(article.storyId, current);
  }

  return storyRows.flatMap((story) => {
    const candidates = articlesByStory.get(story.id) ?? [];
    const representative =
      candidates.find((article) => article.id === story.representativeArticleId) ??
      [...candidates].sort((left, right) => right.score - left.score || +new Date(right.publishedAt) - +new Date(left.publishedAt))[0];
    if (!representative) {
      return [];
    }
    const source = sourceMap.get(representative.sourceId);
    return [{
      id: story.id,
      canonicalSummary: story.canonicalSummary,
      importanceScore: story.importanceScore,
      lastUpdatedAt: story.lastUpdatedAt,
      updateCount: story.updateCount,
      sourceCount: story.sourceCount,
      topicSlugs: [...new Set(candidates.flatMap((article) => topicsByArticle.get(article.id) ?? []))],
      representativeSourceSlug: source?.slug ?? "",
      representativeSourceName: source?.name ?? "",
      representativeArticleScore: representative.score,
      representativeSummaryLength: representative.summary.trim().length,
      representativeContentLength: representative.contentText.trim().length,
      representativeTrustScore: collectorTrustScore((representative.payloadJson as Record<string, unknown> | null) ?? null),
    }] satisfies RankableStory[];
  });
}

function loadMemoryRankableStories(): RankableStory[] {
  const store = memoryStore();
  return store.stories.flatMap((story) => {
    const candidates = store.articles.filter((article) => article.storyId === story.id);
    const representative =
      candidates.find((article) => article.id === story.representativeArticleId) ??
      [...candidates].sort((left, right) => right.score - left.score || +new Date(right.publishedAt) - +new Date(left.publishedAt))[0];
    if (!representative) {
      return [];
    }
    const source = store.sources.find((entry) => entry.id === representative.sourceId);
    return [{
      id: story.id,
      canonicalSummary: story.canonicalSummary,
      importanceScore: story.importanceScore,
      lastUpdatedAt: story.lastUpdatedAt,
      updateCount: story.updateCount,
      sourceCount: story.sourceCount,
      topicSlugs: [
        ...new Set(
          store.articleTopics
            .filter((entry) => candidates.some((article) => article.id === entry.articleId))
            .map((entry) => store.topics.find((topic) => topic.id === entry.topicId)?.slug)
            .filter(Boolean),
        ),
      ] as string[],
      representativeSourceSlug: source?.slug ?? "",
      representativeSourceName: source?.name ?? "",
      representativeArticleScore: representative.score,
      representativeSummaryLength: representative.summary.trim().length,
      representativeContentLength: representative.contentText.trim().length,
      representativeTrustScore: collectorTrustScore(representative.payloadJson),
    }] satisfies RankableStory[];
  });
}

async function ensureStoriesBackfilled() {
  await withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return;
      }

      const articleRows = await db.select().from(articles).orderBy(asc(articles.publishedAt));
      if (articleRows.every((article) => article.storyId)) {
        return;
      }

      const joinRows = await db.select().from(articleTopics);
      const storyRows = await db.select().from(stories);
      const topicIdsByArticle = new Map<string, string[]>();
      for (const join of joinRows) {
        const current = topicIdsByArticle.get(join.articleId) ?? [];
        current.push(join.topicId);
        topicIdsByArticle.set(join.articleId, current);
      }

      const storyTopicMap = new Map<string, Set<string>>();
      for (const article of articleRows) {
        if (!article.storyId) {
          continue;
        }
        const bucket = storyTopicMap.get(article.storyId) ?? new Set<string>();
        for (const topicId of topicIdsByArticle.get(article.id) ?? []) {
          bucket.add(topicId);
        }
        storyTopicMap.set(article.storyId, bucket);
      }

      for (const article of articleRows.filter((entry) => !entry.storyId)) {
        const normalized = normalizeTitle(article.title);
        const fingerprint = storyFingerprint(article.title);
        const articleTopicsForRow = new Set(topicIdsByArticle.get(article.id) ?? []);
        let matched = storyRows.find((story) => {
          const overlap = [...(storyTopicMap.get(story.id) ?? new Set<string>())].some((topicId) =>
            articleTopicsForRow.has(topicId),
          );
          return story.fingerprint === fingerprint || (overlap && diceCoefficient(story.normalizedHeadline, normalized) >= 0.72);
        });

        if (!matched) {
          const inserted = await db
            .insert(stories)
            .values({
              canonicalHeadline: article.title,
              canonicalSummary: article.summary,
              normalizedHeadline: normalized,
              fingerprint,
              firstPublishedAt: article.publishedAt,
              lastUpdatedAt: article.publishedAt,
              importanceScore: article.score * 10,
              updateCount: 1,
              sourceCount: 1,
              representativeArticleId: article.id,
              searchDocument: `${article.title} ${article.summary} ${article.contentText}`,
              updatedAt: new Date(),
            })
            .returning();
          matched = inserted[0];
          storyRows.push(matched);
          storyTopicMap.set(matched.id, articleTopicsForRow);
        }

        await db.update(articles).set({ storyId: matched.id }).where(eq(articles.id, article.id));
        await db
          .insert(storyArticles)
          .values({ storyId: matched.id, articleId: article.id })
          .onConflictDoNothing();
      }

      await recomputeDbStoryRollups();
    },
    async () => {
      await ensureMemorySeeded();
    },
  );
}

async function recomputeDbStoryRollups() {
  const db = getDb();
  if (!db) {
    return;
  }

  const [storyRows, articleRows] = await Promise.all([
    db.select().from(stories),
    db.select().from(articles).where(isNotNull(articles.storyId)),
  ]);

  for (const story of storyRows) {
    const storyArticlesForStory = articleRows
      .filter((article) => article.storyId === story.id)
      .sort((left, right) => +new Date(right.publishedAt) - +new Date(left.publishedAt));
    if (storyArticlesForStory.length === 0) {
      continue;
    }
    const representative = [...storyArticlesForStory].sort(
      (left, right) =>
        right.score - left.score || +new Date(right.publishedAt) - +new Date(left.publishedAt),
    )[0];
    const sourceCount = new Set(storyArticlesForStory.map((article) => article.sourceId)).size;
    const updateCount = storyArticlesForStory.filter(
      (article) => +new Date(article.publishedAt) >= Date.now() - 48 * 60 * 60 * 1000,
    ).length;
    const searchDocument = storyArticlesForStory
      .map((article) => `${article.title} ${article.summary} ${article.contentText}`)
      .join(" ");

    await db
      .update(stories)
      .set({
        canonicalHeadline: representative.title,
        canonicalSummary: representative.summary,
        normalizedHeadline: normalizeTitle(representative.title),
        fingerprint: storyFingerprint(representative.title),
        firstPublishedAt: storyArticlesForStory.at(-1)!.publishedAt,
        lastUpdatedAt: storyArticlesForStory[0].publishedAt,
        importanceScore: Math.max(...storyArticlesForStory.map((article) => article.score * 10)),
        updateCount,
        sourceCount,
        representativeArticleId: representative.id,
        searchDocument,
        updatedAt: new Date(),
      })
      .where(eq(stories.id, story.id));
  }
}

async function ensureFeedRunForDate(feedDate: string, options: GenerateDailyFeedOptions = {}) {
  await ensureStoriesBackfilled();
  const forceRefresh = options.forceRefresh ?? false;
  const referenceDate = feedReferenceDate(feedDate);

  return withStore(
    async () => {
      const db = getDb();
      if (!db) {
        throw new Error("Database unavailable");
      }

      const existing = await db.select().from(dailyFeedRuns).where(eq(dailyFeedRuns.feedDate, feedDate));
      const eligible = (await loadDbRankableStories())
        .filter((story) => +new Date(story.lastUpdatedAt) <= referenceDate.getTime())
        .map((story) => ({ story, score: scoreStory(story, referenceDate) }))
        .sort((left, right) => right.score - left.score);
      const rows = buildRunItemSeeds(eligible, feedDate, referenceDate);

      let run = existing[0];
      if (run && !forceRefresh) {
        return {
          id: run.id,
          feedDate: run.feedDate,
          generatedAt: run.generatedAt.toISOString(),
          algorithmVersion: run.algorithmVersion,
          notes: run.notes,
        } satisfies FeedRunRecord;
      }

      if (!run) {
        const insertedRun = await db
          .insert(dailyFeedRuns)
          .values({
            feedDate,
            generatedAt: new Date(),
            algorithmVersion: ALGORITHM_VERSION,
          })
          .returning();
        run = insertedRun[0];
      } else {
        await db.delete(dailyFeedItems).where(eq(dailyFeedItems.feedRunId, run.id));
        const staleUserFeeds = await db.select().from(userDailyFeeds).where(eq(userDailyFeeds.feedDate, feedDate));
        if (staleUserFeeds.length > 0) {
          await db
            .delete(userDailyFeedItems)
            .where(inArray(userDailyFeedItems.userDailyFeedId, staleUserFeeds.map((row) => row.id)));
          await db.delete(userDailyFeeds).where(eq(userDailyFeeds.feedDate, feedDate));
        }
        const refreshed = await db
          .update(dailyFeedRuns)
          .set({
            generatedAt: new Date(),
            algorithmVersion: ALGORITHM_VERSION,
            notes: forceRefresh ? "refreshed" : null,
          })
          .where(eq(dailyFeedRuns.id, run.id))
          .returning();
        run = refreshed[0];
      }

      if (rows.length > 0) {
        await db.insert(dailyFeedItems).values(
          rows.map((row) => ({
            feedRunId: run.id,
            storyId: row.storyId,
            section: row.section,
            rankPosition: row.rankPosition,
            rankScore: row.rankScore,
            compactSummary: row.compactSummary,
          })),
        );
      }

      return {
        id: run.id,
        feedDate: run.feedDate,
        generatedAt: run.generatedAt.toISOString(),
        algorithmVersion: run.algorithmVersion,
        notes: run.notes,
      } satisfies FeedRunRecord;
    },
    async () => {
      await ensureMemorySeeded();
      const store = memoryStore();
      const existing = store.runs.find((entry) => entry.feedDate === feedDate);
      if (existing && !forceRefresh) {
        return existing;
      }
      const eligible = loadMemoryRankableStories()
        .filter((story) => +new Date(story.lastUpdatedAt) <= referenceDate.getTime())
        .map((story) => ({ story, score: scoreStory(story, referenceDate) }))
        .sort((left, right) => right.score - left.score);
      const rows = buildRunItemSeeds(eligible, feedDate, referenceDate);
      let run = existing;
      if (!run) {
        run = {
          id: uuid(),
          feedDate,
          generatedAt: new Date().toISOString(),
          algorithmVersion: ALGORITHM_VERSION,
          notes: null,
        };
        store.runs.push(run);
      } else {
        run.generatedAt = new Date().toISOString();
        run.algorithmVersion = ALGORITHM_VERSION;
        run.notes = "refreshed";
        store.runItems = store.runItems.filter((entry) => entry.feedRunId !== run!.id);
        store.userDailyFeedItems = store.userDailyFeedItems.filter((entry) => {
          const feed = store.userDailyFeeds.find((candidate) => candidate.id === entry.userDailyFeedId);
          return feed?.feedDate !== feedDate;
        });
        store.userDailyFeeds = store.userDailyFeeds.filter((entry) => entry.feedDate !== feedDate);
      }
      for (const row of rows) {
        store.runItems.push({
          id: uuid(),
          feedRunId: run.id,
          storyId: row.storyId,
          section: row.section,
          rankScore: row.rankScore,
          rankPosition: row.rankPosition,
          compactSummary: row.compactSummary,
          reasonJson: null,
          feedDate,
        });
      }
      return run;
    },
  );
}

async function ensureUserDailyFeed(viewerId: string, feedDate: string) {
  return withStore(
    async () => {
      const db = getDb();
      if (!db) {
        throw new Error("Database unavailable");
      }
      const run = await ensureFeedRunForDate(feedDate);
      const existing = await db
        .select()
        .from(userDailyFeeds)
        .where(and(eq(userDailyFeeds.userId, viewerId), eq(userDailyFeeds.feedDate, feedDate)));
      if (existing[0]) {
        return {
          id: existing[0].id,
          userId: existing[0].userId,
          feedDate: existing[0].feedDate,
          generatedFromFeedRunId: existing[0].generatedFromFeedRunId,
          createdAt: existing[0].createdAt.toISOString(),
          clearedAt: existing[0].clearedAt?.toISOString() ?? null,
          status: existing[0].status,
        } satisfies UserDailyFeedRecord;
      }

      const [stateRows, todayItems, sourcePrefs, topicPrefs, prefs] = await Promise.all([
        db.select().from(userStoryState).where(eq(userStoryState.userId, viewerId)),
        db.select().from(dailyFeedItems).where(eq(dailyFeedItems.feedRunId, run.id)),
        db.select().from(userSourcePreferences).where(eq(userSourcePreferences.userId, viewerId)),
        db.select().from(userTopicPreferences).where(eq(userTopicPreferences.userId, viewerId)),
        db.select().from(userPreferences).where(eq(userPreferences.userId, viewerId)),
      ]);

      const hiddenSourceIds = new Set(sourcePrefs.filter((row) => row.isHidden).map((row) => row.sourceId));
      const mutedTopicIds = new Set(topicPrefs.filter((row) => row.isMuted).map((row) => row.topicId));
      const stateMap = new Map(stateRows.map((row) => [row.storyId, row]));
      const catchupDays = prefs[0]?.catchupDays ?? 3;
      const candidateCards = await hydrateStoriesByIds(todayItems.map((row) => row.storyId), viewerId);
      const filteredToday = todayItems.filter((item) => {
        const card = candidateCards.find((entry) => entry.id === item.storyId);
        if (!card) {
          return false;
        }
        const storyState = stateMap.get(item.storyId);
        if (storyState?.isArchived) {
          return false;
        }
        if (hiddenSourceIds.has(card.representativeArticle.source.id)) {
          return false;
        }
        if (card.topics.some((topic) => mutedTopicIds.has(topic.id))) {
          return false;
        }
        return item.section !== "catchup_candidate";
      });

      const inserted = await db
        .insert(userDailyFeeds)
        .values({
          userId: viewerId,
          feedDate,
          generatedFromFeedRunId: run.id,
        })
        .returning();
      const userFeed = inserted[0];

      if (filteredToday.length > 0) {
        await db.insert(userDailyFeedItems).values(
          filteredToday.map((item) => {
            const storyState = stateMap.get(item.storyId);
            return {
              userDailyFeedId: userFeed.id,
              storyId: item.storyId,
              tab: "today",
              section: item.section === "today_important" ? "important" : "other",
              rankPosition: item.rankPosition,
              isRead: storyState?.isRead ?? false,
              isDismissed: storyState?.isDismissed ?? false,
              isArchived: storyState?.isArchived ?? false,
            };
          }),
        );
      }

      const priorDates = Array.from({ length: catchupDays }, (_, index) => addDays(feedDate, -(index + 1)));
      const priorRuns = await db.select().from(dailyFeedRuns).where(inArray(dailyFeedRuns.feedDate, priorDates));
      const priorItems = priorRuns.length
        ? await db.select().from(dailyFeedItems).where(inArray(dailyFeedItems.feedRunId, priorRuns.map((row) => row.id)))
        : [];
      const grouped = new Map<string, number>();
      let catchupCount = 0;
      const catchupRows: Array<{
        userDailyFeedId: string;
        storyId: string;
        tab: string;
        section: string;
        rankPosition: number;
        isRead: boolean;
        isDismissed: boolean;
        isArchived: boolean;
        summaryOverride: string | null;
      }> = [];

      for (const item of priorItems
        .filter((row) => row.section !== "catchup_candidate")
        .sort((left, right) => {
          const leftDate = priorRuns.find((runRow) => runRow.id === left.feedRunId)?.feedDate ?? "";
          const rightDate = priorRuns.find((runRow) => runRow.id === right.feedRunId)?.feedDate ?? "";
          return rightDate.localeCompare(leftDate) || left.rankPosition - right.rankPosition;
        })) {
        if (catchupCount >= CATCHUP_TOTAL_LIMIT) {
          break;
        }
        const dateKey = priorRuns.find((row) => row.id === item.feedRunId)?.feedDate;
        if (!dateKey) {
          continue;
        }
        const seenForDay = grouped.get(dateKey) ?? 0;
        if (seenForDay >= CATCHUP_PER_DAY_LIMIT) {
          continue;
        }
        const storyState = stateMap.get(item.storyId);
        if (!storyState || storyState.isRead || storyState.isArchived || storyState.isDismissed || storyState.carryoverCount >= MAX_CARRYOVERS) {
          continue;
        }
        if (filteredToday.some((row) => row.storyId === item.storyId)) {
          continue;
        }
        catchupRows.push({
          userDailyFeedId: userFeed.id,
          storyId: item.storyId,
          tab: "catchup",
          section: "compact",
          rankPosition: seenForDay + 1,
          isRead: storyState.isRead,
          isDismissed: storyState.isDismissed,
          isArchived: storyState.isArchived,
          summaryOverride: item.compactSummary,
        });
        grouped.set(dateKey, seenForDay + 1);
        catchupCount += 1;
      }

      if (catchupRows.length > 0) {
        await db.insert(userDailyFeedItems).values(catchupRows);
      }

      return {
        id: userFeed.id,
        userId: userFeed.userId,
        feedDate: userFeed.feedDate,
        generatedFromFeedRunId: userFeed.generatedFromFeedRunId,
        createdAt: userFeed.createdAt.toISOString(),
        clearedAt: userFeed.clearedAt?.toISOString() ?? null,
        status: userFeed.status,
      } satisfies UserDailyFeedRecord;
    },
    async () => {
      await ensureMemorySeeded();
      const store = memoryStore();
      const run = await ensureFeedRunForDate(feedDate);
      const existing = store.userDailyFeeds.find((entry) => entry.userId === viewerId && entry.feedDate === feedDate);
      if (existing) {
        return existing;
      }
      const prefs = store.prefs.find((entry) => entry.userId === viewerId);
      const userFeed = {
        id: uuid(),
        userId: viewerId,
        feedDate,
        generatedFromFeedRunId: run.id,
        createdAt: new Date().toISOString(),
        clearedAt: null,
        status: "active",
      };
      store.userDailyFeeds.push(userFeed);
      const stateMap = new Map(store.state.filter((entry) => entry.userId === viewerId).map((entry) => [entry.storyId, entry]));
      const todayItems = store.runItems.filter((entry) => entry.feedRunId === run.id && entry.section !== "catchup_candidate");
      for (const item of todayItems) {
        const state = stateMap.get(item.storyId);
        if (state?.isArchived) {
          continue;
        }
        store.userDailyFeedItems.push({
          id: uuid(),
          userDailyFeedId: userFeed.id,
          storyId: item.storyId,
          tab: "today",
          section: item.section === "today_important" ? "important" : "other",
          rankPosition: item.rankPosition,
          isRead: state?.isRead ?? false,
          isDismissed: state?.isDismissed ?? false,
          isArchived: state?.isArchived ?? false,
          summaryOverride: null,
        });
      }
      const priorDates = Array.from({ length: prefs?.catchupDays ?? 3 }, (_, index) => addDays(feedDate, -(index + 1)));
      let total = 0;
      for (const dateKey of priorDates) {
        const runForDay = store.runs.find((entry) => entry.feedDate === dateKey);
        if (!runForDay) {
          continue;
        }
        const dayItems = store.runItems
          .filter((entry) => entry.feedRunId === runForDay.id && entry.section !== "catchup_candidate")
          .slice(0, CATCHUP_PER_DAY_LIMIT);
        for (const item of dayItems) {
          if (total >= CATCHUP_TOTAL_LIMIT) {
            break;
          }
          const state = stateMap.get(item.storyId);
          if (!state || state.isRead || state.isArchived || state.isDismissed || state.carryoverCount >= MAX_CARRYOVERS) {
            continue;
          }
          store.userDailyFeedItems.push({
            id: uuid(),
            userDailyFeedId: userFeed.id,
            storyId: item.storyId,
            tab: "catchup",
            section: "compact",
            rankPosition: total + 1,
            isRead: state.isRead,
            isDismissed: state.isDismissed,
            isArchived: state.isArchived,
            summaryOverride: item.compactSummary,
          });
          total += 1;
        }
      }
      return userFeed;
    },
  );
}

function withCompact(card: HydratedStory, summaryOverride: string | null) {
  return {
    ...card,
    compactSummary: summaryOverride ?? card.compactSummary,
  };
}

export async function getTodayFeed(): Promise<TodayFeedResponse> {
  const viewer = await getViewer();
  await upsertUser(viewer);
  const feedDate = currentFeedDate();

  if (!viewer.id) {
    const run = await ensureFeedRunForDate(feedDate);
    const items = await withStore(
      async () => {
        const db = getDb();
        if (!db) {
          return [];
        }
        return db.select().from(dailyFeedItems).where(eq(dailyFeedItems.feedRunId, run.id));
      },
      async () => memoryStore().runItems.filter((entry) => entry.feedRunId === run.id),
    );
    const cards = await hydrateStoriesByIds(
      items.filter((item) => item.section !== "catchup_candidate").map((item) => item.storyId),
      null,
    );
    return {
      date: feedDate,
      important: cards.filter((card) => items.find((item) => item.storyId === card.id)?.section === "today_important"),
      other: cards.filter((card) => items.find((item) => item.storyId === card.id)?.section === "today_other"),
      cleared: false,
    };
  }

  const userFeed = await ensureUserDailyFeed(viewer.id, feedDate);
  const rows = await withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return [];
      }
      return db
        .select()
        .from(userDailyFeedItems)
        .where(and(eq(userDailyFeedItems.userDailyFeedId, userFeed.id), eq(userDailyFeedItems.tab, "today")))
        .orderBy(asc(userDailyFeedItems.rankPosition));
    },
    async () =>
      memoryStore().userDailyFeedItems.filter(
        (entry) => entry.userDailyFeedId === userFeed.id && entry.tab === "today",
      ),
  );
  const cards = await hydrateStoriesByIds(rows.map((row) => row.storyId), viewer.id);
  const hydrated = rows.map((row) => withCompact(cards.find((card) => card.id === row.storyId)!, row.summaryOverride ?? null));
  return {
    date: feedDate,
    important: hydrated.filter((card) => rows.find((row) => row.storyId === card.id)?.section === "important"),
    other: hydrated.filter((card) => rows.find((row) => row.storyId === card.id)?.section === "other"),
    cleared: hydrated.every((card) => card.viewerState.isRead || card.viewerState.isArchived || card.viewerState.isDismissed),
  };
}

function catchupLabel(dateKey: string, index: number) {
  if (index === 0) {
    return "Yesterday";
  }
  return `${index + 1} days ago`;
}

export async function getCatchupFeed(): Promise<CatchupFeedResponse> {
  const viewer = await getViewer();
  await upsertUser(viewer);
  const feedDate = currentFeedDate();

  if (!viewer.id) {
    const dates = [addDays(feedDate, -1), addDays(feedDate, -2), addDays(feedDate, -3)];
    const runs = await Promise.all(dates.map((dateKey) => ensureFeedRunForDate(dateKey)));
    const groups: CatchupGroup[] = [];
    for (const [index, run] of runs.entries()) {
      const items = await withStore(
        async () => {
          const db = getDb();
          if (!db) {
            return [];
          }
          return db.select().from(dailyFeedItems).where(eq(dailyFeedItems.feedRunId, run.id));
        },
        async () => memoryStore().runItems.filter((entry) => entry.feedRunId === run.id),
      );
      const cards = await hydrateStoriesByIds(items.slice(0, 2).map((item) => item.storyId), null);
      groups.push({
        label: catchupLabel(dates[index], index),
        date: dates[index],
        items: cards,
      });
    }
    return { date: feedDate, groups: groups.filter((group) => group.items.length > 0) };
  }

  const userFeed = await ensureUserDailyFeed(viewer.id, feedDate);
  const rows = await withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return [];
      }
      return db
        .select()
        .from(userDailyFeedItems)
        .where(and(eq(userDailyFeedItems.userDailyFeedId, userFeed.id), eq(userDailyFeedItems.tab, "catchup")))
        .orderBy(asc(userDailyFeedItems.rankPosition));
    },
    async () =>
      memoryStore().userDailyFeedItems.filter(
        (entry) => entry.userDailyFeedId === userFeed.id && entry.tab === "catchup",
      ),
  );
  const cards = await hydrateStoriesByIds(rows.map((row) => row.storyId), viewer.id);
  const groupsMap = new Map<string, StoryCard[]>();

  for (const row of rows) {
    const card = cards.find((entry) => entry.id === row.storyId);
    if (!card) {
      continue;
    }
    const dateKey = addDays(feedDate, -Math.min(Math.max(row.rankPosition, 1), 3));
    const group = groupsMap.get(dateKey) ?? [];
    group.push(withCompact(card, row.summaryOverride ?? null));
    groupsMap.set(dateKey, group);
  }

  const groups = [...groupsMap.entries()].map(([dateKey, items], index) => ({
    label: catchupLabel(dateKey, index),
    date: dateKey,
    items,
  }));
  return { date: feedDate, groups };
}

export async function getSavedFeed(): Promise<SavedFeedResponse> {
  const viewer = await getViewer();
  await upsertUser(viewer);
  if (!viewer.id) {
    return { items: [] };
  }
  const viewerId = viewer.id;
  const storyIds = await withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return [];
      }
      const rows = await db
        .select()
        .from(userStoryState)
        .where(and(eq(userStoryState.userId, viewerId), eq(userStoryState.isSaved, true)));
      return rows.map((row) => row.storyId);
    },
    async () =>
      memoryStore().state
        .filter((entry) => entry.userId === viewerId && entry.isSaved)
        .map((entry) => entry.storyId),
  );
  return { items: await hydrateStoriesByIds(storyIds, viewerId) };
}

export async function getArchivedFeed(): Promise<ArchivedFeedResponse> {
  const viewer = await getViewer();
  await upsertUser(viewer);
  if (!viewer.id) {
    return { items: [] };
  }
  const viewerId = viewer.id;
  const storyIds = await withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return [];
      }
      const rows = await db
        .select()
        .from(userStoryState)
        .where(and(eq(userStoryState.userId, viewerId), eq(userStoryState.isArchived, true)));
      return rows.map((row) => row.storyId);
    },
    async () =>
      memoryStore().state
        .filter((entry) => entry.userId === viewerId && entry.isArchived)
        .map((entry) => entry.storyId),
  );
  return { items: await hydrateStoriesByIds(storyIds, viewerId) };
}

export async function getStory(storyId: string): Promise<StoryDetail | null> {
  const viewer = await getViewer();
  await upsertUser(viewer);
  return (await hydrateStoriesByIds([storyId], viewer.id))[0] ?? null;
}

export async function getStoryIdForArticle(articleId: string) {
  return withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return null;
      }
      const row = await db.select().from(articles).where(eq(articles.id, articleId));
      return row[0]?.storyId ?? null;
    },
    async () => memoryStore().articles.find((entry) => entry.id === articleId)?.storyId ?? null,
  );
}

export async function searchStories(query: string) {
  const viewer = await getViewer();
  await upsertUser(viewer);
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return { total: 0, query, items: [] as StoryCard[] };
  }
  const allStories = await withStore<Array<{ id: string; canonicalHeadline: string; canonicalSummary: string; searchDocument: string }>>(
    async () => {
      const db = getDb();
      if (!db) {
        return [];
      }
      const rows = await db.select().from(stories).orderBy(desc(stories.lastUpdatedAt));
      return rows.map((story) => ({
        id: story.id,
        canonicalHeadline: story.canonicalHeadline,
        canonicalSummary: story.canonicalSummary,
        searchDocument: story.searchDocument,
      }));
    },
    async () =>
      memoryStore().stories.map((story) => ({
        id: story.id,
        canonicalHeadline: story.canonicalHeadline,
        canonicalSummary: story.canonicalSummary,
        searchDocument: story.searchDocument,
      })),
  );
  const filteredIds = allStories
    .filter((story) =>
      [story.canonicalHeadline, story.canonicalSummary, story.searchDocument].join(" ").toLowerCase().includes(needle),
    )
    .map((story) => story.id);
  const items = await hydrateStoriesByIds(filteredIds, viewer.id);
  return { total: items.length, query, items };
}

export async function getShellData(): Promise<ShellData> {
  const viewer = await getViewer();
  await upsertUser(viewer);
  const [sourceRows, topicRows, sourcePrefs, topicPrefs, savedRows] = await withStore<
    [
      Array<{ id: string; slug: string; name: string; homepageUrl: string | null; iconUrl: string | null }>,
      Array<{ id: string; slug: string; name: string }>,
      Array<{ sourceId: string; isHidden: boolean }>,
      Array<{ topicId: string; isMuted: boolean }>,
      Array<{ storyId: string }>
    ]
  >(
    async () => {
      const db = getDb();
      if (!db) {
        throw new Error("Database unavailable");
      }
      const [dbSources, dbTopics, dbSourcePrefs, dbTopicPrefs, dbSavedRows] = await Promise.all([
        db.select().from(sources).orderBy(asc(sources.name)),
        db.select().from(topics).orderBy(asc(topics.name)),
        viewer.id ? db.select().from(userSourcePreferences).where(eq(userSourcePreferences.userId, viewer.id)) : Promise.resolve([]),
        viewer.id ? db.select().from(userTopicPreferences).where(eq(userTopicPreferences.userId, viewer.id)) : Promise.resolve([]),
        viewer.id ? db.select().from(userStoryState).where(and(eq(userStoryState.userId, viewer.id), eq(userStoryState.isSaved, true))) : Promise.resolve([]),
      ]);
      return [
        dbSources.map((source) => ({
          id: source.id,
          slug: source.slug,
          name: source.name,
          homepageUrl: source.homepageUrl,
          iconUrl: source.iconUrl,
        })),
        dbTopics.map((topic) => ({ id: topic.id, slug: topic.slug, name: topic.name })),
        dbSourcePrefs.map((row) => ({ sourceId: row.sourceId, isHidden: row.isHidden })),
        dbTopicPrefs.map((row) => ({ topicId: row.topicId, isMuted: row.isMuted })),
        dbSavedRows.map((row) => ({ storyId: row.storyId })),
      ];
    },
    async () => {
      await ensureMemorySeeded();
      const store = memoryStore();
      return [
        store.sources.map((source) => ({
          id: source.id,
          slug: source.slug,
          name: source.name,
          homepageUrl: source.homepageUrl,
          iconUrl: source.iconUrl,
        })),
        store.topics.map((topic) => ({ id: topic.id, slug: topic.slug, name: topic.name })),
        viewer.id ? store.sourcePrefs.filter((entry) => entry.userId === viewer.id).map((entry) => ({ sourceId: entry.sourceId, isHidden: entry.isHidden })) : [],
        viewer.id ? store.topicPrefs.filter((entry) => entry.userId === viewer.id).map((entry) => ({ topicId: entry.topicId, isMuted: entry.isMuted })) : [],
        viewer.id ? store.state.filter((entry) => entry.userId === viewer.id && entry.isSaved).map((entry) => ({ storyId: entry.storyId })) : [],
      ] as const;
    },
  );

  const storyCards = await hydrateStoriesByIds(
    await withStore(
      async () => {
        const db = getDb();
        if (!db) {
          return [];
        }
        const rows = await db.select().from(stories);
        return rows.map((row) => row.id);
      },
      async () => memoryStore().stories.map((row) => row.id),
    ),
    viewer.id,
  );

  const hiddenSourceIds = new Set(sourcePrefs.filter((row) => row.isHidden).map((row) => row.sourceId));
  const mutedTopicIds = new Set(topicPrefs.filter((row) => row.isMuted).map((row) => row.topicId));

  return {
    sources: sourceRows.map((source) => ({
      id: source.id,
      slug: source.slug,
      name: source.name,
      homepageUrl: source.homepageUrl,
      iconUrl: source.iconUrl,
      hidden: hiddenSourceIds.has(source.id),
    })),
    topics: topicRows.map((topic) => ({
      id: topic.id,
      slug: topic.slug,
      name: topic.name,
      muted: mutedTopicIds.has(topic.id),
      storyCount: storyCards.filter((story) => story.topics.some((entry) => entry.id === topic.id)).length,
    })),
    savedCount: savedRows.length,
    user: viewer,
  };
}

export async function getPreferences(): Promise<AppPreferences> {
  const viewer = await getViewer();
  await upsertUser(viewer);
  if (!viewer.id) {
    return mockAppPreferences;
  }
  const viewerId = viewer.id;

  return withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return mockAppPreferences;
      }
      const row = await db.select().from(userPreferences).where(eq(userPreferences.userId, viewerId));
      if (!row[0]) {
        return mockAppPreferences;
      }
      return {
        theme: row[0].theme as AppPreferences["theme"],
        feedDensity: row[0].feedDensity as AppPreferences["feedDensity"],
        openOriginalInNewTab: row[0].openOriginalInNewTab,
      };
    },
    async () => {
      const row = memoryStore().prefs.find((entry) => entry.userId === viewerId);
      return row
        ? {
            theme: row.theme,
            feedDensity: row.feedDensity,
            openOriginalInNewTab: row.openOriginalInNewTab,
          }
        : mockAppPreferences;
    },
  );
}

export async function updatePreferences(input: AppPreferences) {
  const viewer = await getViewer();
  await upsertUser(viewer);
  if (!viewer.id) {
    return input;
  }
  const viewerId = viewer.id;

  return withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return input;
      }
      await db
        .insert(userPreferences)
        .values({
          userId: viewerId,
          theme: input.theme,
          feedDensity: input.feedDensity,
          openOriginalInNewTab: input.openOriginalInNewTab,
          timezone: APP_TIMEZONE,
          dailyResetHour: APP_DAILY_RESET_HOUR,
          catchupDays: 3,
          updatedAt: new Date(),
        })
        .onConflictDoUpdate({
          target: userPreferences.userId,
          set: {
            theme: input.theme,
            feedDensity: input.feedDensity,
            openOriginalInNewTab: input.openOriginalInNewTab,
            updatedAt: new Date(),
          },
        });
      return input;
    },
    async () => {
      const store = memoryStore();
      const existing = store.prefs.find((entry) => entry.userId === viewerId);
      if (existing) {
        existing.theme = input.theme;
        existing.feedDensity = input.feedDensity;
        existing.openOriginalInNewTab = input.openOriginalInNewTab;
      } else {
        store.prefs.push({
          userId: viewerId,
          theme: input.theme,
          feedDensity: input.feedDensity,
          openOriginalInNewTab: input.openOriginalInNewTab,
          timezone: APP_TIMEZONE,
          dailyResetHour: APP_DAILY_RESET_HOUR,
          catchupDays: 3,
        });
      }
      return input;
    },
  );
}

async function upsertStoryState(viewerId: string, storyId: string, patch: Partial<typeof userStoryState.$inferInsert>) {
  return withStore(
    async () => {
      const db = getDb();
      if (!db) {
        throw new Error("Database unavailable");
      }
      const existing = await db
        .select()
        .from(userStoryState)
        .where(and(eq(userStoryState.userId, viewerId), eq(userStoryState.storyId, storyId)));
      const base = existing[0] ?? {
        userId: viewerId,
        storyId,
        firstSeenAt: new Date(),
        lastSeenAt: new Date(),
        lastReadAt: null,
        isRead: false,
        isSaved: false,
        isArchived: false,
        isDismissed: false,
        isHidden: false,
        carryoverCount: 0,
        archivedAt: null,
      };
      await db
        .insert(userStoryState)
        .values({
          ...base,
          ...patch,
          userId: viewerId,
          storyId,
          lastSeenAt: new Date(),
        })
        .onConflictDoUpdate({
          target: [userStoryState.userId, userStoryState.storyId],
          set: {
            ...patch,
            lastSeenAt: new Date(),
          },
        });
    },
    async () => {
      const store = memoryStore();
      let existing = store.state.find((entry) => entry.userId === viewerId && entry.storyId === storyId);
      if (!existing) {
        existing = {
          userId: viewerId,
          storyId,
          firstSeenAt: new Date().toISOString(),
          lastSeenAt: new Date().toISOString(),
          lastReadAt: null,
          isRead: false,
          isSaved: false,
          isArchived: false,
          isDismissed: false,
          carryoverCount: 0,
          archivedAt: null,
        };
        store.state.push(existing);
      }
      Object.assign(existing, patch);
      existing.lastSeenAt = new Date().toISOString();
    },
  );
}

export async function setStoryRead(storyId: string, read: boolean) {
  const viewer = await getViewer();
  if (!viewer.id) {
    return defaultViewerState(storyId);
  }
  const viewerId = viewer.id;
  await upsertUser(viewer);
  await upsertStoryState(viewerId, storyId, {
    isRead: read,
    lastReadAt: read ? new Date() : null,
    isDismissed: read ? false : undefined,
  });
  return {
    storyId,
    isRead: read,
    lastReadAt: read ? new Date().toISOString() : null,
    isSaved: false,
    isArchived: false,
    isDismissed: false,
  };
}

export async function setStorySaved(storyId: string, saved: boolean) {
  const viewer = await getViewer();
  if (!viewer.id) {
    return defaultViewerState(storyId);
  }
  const viewerId = viewer.id;
  await upsertUser(viewer);
  await upsertStoryState(viewerId, storyId, { isSaved: saved });
  return {
    ...defaultViewerState(storyId),
    isSaved: saved,
  };
}

export async function setStoryArchived(storyId: string, archived: boolean) {
  const viewer = await getViewer();
  if (!viewer.id) {
    return defaultViewerState(storyId);
  }
  const viewerId = viewer.id;
  await upsertUser(viewer);
  await upsertStoryState(viewerId, storyId, {
    isArchived: archived,
    archivedAt: archived ? new Date() : null,
    isDismissed: archived,
  });
  return {
    ...defaultViewerState(storyId),
    isArchived: archived,
    isDismissed: archived,
  };
}

export async function clearToday() {
  const viewer = await getViewer();
  if (!viewer.id) {
    return { cleared: false };
  }
  const viewerId = viewer.id;
  const feed = await getTodayFeed();
  for (const item of [...feed.important, ...feed.other].filter((entry) => !entry.viewerState.isSaved)) {
    await setStoryArchived(item.id, true);
  }
  await withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return;
      }
      await db
        .update(userDailyFeeds)
        .set({ clearedAt: new Date() })
        .where(and(eq(userDailyFeeds.userId, viewerId), eq(userDailyFeeds.feedDate, currentFeedDate())));
    },
    async () => {
      const row = memoryStore().userDailyFeeds.find(
        (entry) => entry.userId === viewerId && entry.feedDate === currentFeedDate(),
      );
      if (row) {
        row.clearedAt = new Date().toISOString();
      }
    },
  );
  return { cleared: true };
}

export async function setSourceHidden(sourceId: string, hidden: boolean) {
  const viewer = await getViewer();
  if (!viewer.id) {
    return { sourceId, isHidden: hidden };
  }
  const viewerId = viewer.id;
  await upsertUser(viewer);
  return withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return { sourceId, isHidden: hidden };
      }
      await db
        .insert(userSourcePreferences)
        .values({ userId: viewerId, sourceId, isHidden: hidden, updatedAt: new Date() })
        .onConflictDoUpdate({
          target: [userSourcePreferences.userId, userSourcePreferences.sourceId],
          set: { isHidden: hidden, updatedAt: new Date() },
        });
      return { sourceId, isHidden: hidden };
    },
    async () => {
      const store = memoryStore();
      const row = store.sourcePrefs.find((entry) => entry.userId === viewerId && entry.sourceId === sourceId);
      if (row) {
        row.isHidden = hidden;
      } else {
        store.sourcePrefs.push({ userId: viewerId, sourceId, isHidden: hidden });
      }
      return { sourceId, isHidden: hidden };
    },
  );
}

export async function setTopicMuted(topicId: string, muted: boolean) {
  const viewer = await getViewer();
  if (!viewer.id) {
    return { topicId, isMuted: muted };
  }
  const viewerId = viewer.id;
  await upsertUser(viewer);
  return withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return { topicId, isMuted: muted };
      }
      await db
        .insert(userTopicPreferences)
        .values({ userId: viewerId, topicId, isMuted: muted, updatedAt: new Date() })
        .onConflictDoUpdate({
          target: [userTopicPreferences.userId, userTopicPreferences.topicId],
          set: { isMuted: muted, updatedAt: new Date() },
        });
      return { topicId, isMuted: muted };
    },
    async () => {
      const store = memoryStore();
      const row = store.topicPrefs.find((entry) => entry.userId === viewerId && entry.topicId === topicId);
      if (row) {
        row.isMuted = muted;
      } else {
        store.topicPrefs.push({ userId: viewerId, topicId, isMuted: muted });
      }
      return { topicId, isMuted: muted };
    },
  );
}

export async function mergeLocalState(input: LocalStoryStateInput) {
  const viewer = await getViewer();
  if (!viewer.id) {
    return { merged: 0 };
  }
  const viewerId = viewer.id;
  await upsertUser(viewer);
  const storyIds = new Set([...input.readStoryIds, ...input.archivedStoryIds, ...input.dismissedStoryIds]);
  for (const storyId of storyIds) {
    await upsertStoryState(viewerId, storyId, {
      isRead: input.readStoryIds.includes(storyId),
      lastReadAt: input.readStoryIds.includes(storyId) ? new Date() : null,
      isArchived: input.archivedStoryIds.includes(storyId),
      archivedAt: input.archivedStoryIds.includes(storyId) ? new Date() : null,
      isDismissed: input.dismissedStoryIds.includes(storyId),
    });
  }
  return { merged: storyIds.size };
}

export async function cleanupAgedStories() {
  const cutoff = addDays(currentFeedDate(), -4);
  return withStore(
    async () => {
      const db = getDb();
      if (!db) {
        return { archived: 0 };
      }
      const staleFeeds = await db.select().from(userDailyFeeds).where(lt(userDailyFeeds.feedDate, cutoff));
      if (staleFeeds.length === 0) {
        return { archived: 0 };
      }
      const staleItems = await db
        .select()
        .from(userDailyFeedItems)
        .where(inArray(userDailyFeedItems.userDailyFeedId, staleFeeds.map((row) => row.id)));
      for (const item of staleItems) {
        const feed = staleFeeds.find((row) => row.id === item.userDailyFeedId);
        if (!feed) {
          continue;
        }
        await upsertStoryState(feed.userId, item.storyId, {
          isArchived: true,
          archivedAt: new Date(),
        });
      }
      return { archived: staleItems.length };
    },
    async () => ({ archived: 0 }),
  );
}

export async function generateDailyFeed(options: GenerateDailyFeedOptions = {}) {
  const feedDate = options.feedDate ?? currentFeedDate();
  const run = await ensureFeedRunForDate(feedDate, options);
  return {
    feedDate: "feedDate" in run ? run.feedDate : feedDate,
    generatedAt: "generatedAt" in run ? run.generatedAt : new Date().toISOString(),
  };
}

export async function syncArticles(items: SyncArticleInput[]) {
  return withStore(
    async () => {
      const db = getDb();
      if (!db) {
        throw new Error("Database unavailable");
      }

      let inserted = 0;
      let updated = 0;
      await db.transaction(async (tx) => {
        for (const item of items) {
          const score = incomingArticleScore(item);
          await tx
            .insert(sources)
            .values({
              slug: item.source.slug,
              name: item.source.name,
              homepageUrl: item.source.homepage_url ?? null,
              iconUrl: item.source.icon_url ?? null,
              domain: (() => {
                try {
                  return new URL(item.url).hostname;
                } catch {
                  return null;
                }
              })(),
              updatedAt: new Date(),
            })
            .onConflictDoUpdate({
              target: sources.slug,
              set: {
                name: item.source.name,
                homepageUrl: item.source.homepage_url ?? null,
                iconUrl: item.source.icon_url ?? null,
                updatedAt: new Date(),
              },
            });
          const source = (await tx.select().from(sources).where(eq(sources.slug, item.source.slug)))[0];
          const existingByExternalId = (
            await tx
              .select()
              .from(articles)
              .where(and(eq(articles.sourceId, source.id), eq(articles.externalId, item.external_id)))
          )[0];
          const existingByUrl =
            existingByExternalId ??
            (
              await tx
                .select()
                .from(articles)
                .where(eq(articles.url, item.url))
            )[0];
          const existing = existingByExternalId ?? existingByUrl;

          let articleId = existing?.id ?? uuid();
          if (existing) {
            await tx
              .update(articles)
              .set({
                sourceId: source.id,
                externalId: item.external_id,
                title: item.title,
                summary: item.summary,
                author: item.author ?? null,
                url: item.url,
                imageUrl: item.image_url ?? null,
                publishedAt: new Date(item.published_at),
                contentText: item.content_text,
                score,
                payloadJson: item.payload_json ?? null,
                updatedAt: new Date(),
              })
              .where(eq(articles.id, existing.id));
            updated += 1;
          } else {
            const insertedRow = await tx
              .insert(articles)
              .values({
                id: articleId,
                sourceId: source.id,
                externalId: item.external_id,
                title: item.title,
                summary: item.summary,
                author: item.author ?? null,
                url: item.url,
                imageUrl: item.image_url ?? null,
                publishedAt: new Date(item.published_at),
                ingestedAt: new Date(),
                contentText: item.content_text,
                score,
                payloadJson: item.payload_json ?? null,
                updatedAt: new Date(),
              })
              .returning();
            articleId = insertedRow[0].id;
            inserted += 1;
          }

          for (const topic of item.topics) {
            await tx
              .insert(topics)
              .values({ slug: topic.slug, name: topic.name, updatedAt: new Date() })
              .onConflictDoUpdate({
                target: topics.slug,
                set: { name: topic.name, updatedAt: new Date() },
              });
          }
          const topicRows = item.topics.length
            ? await tx.select().from(topics).where(inArray(topics.slug, item.topics.map((topic) => topic.slug)))
            : [];
          await tx.delete(articleTopics).where(eq(articleTopics.articleId, articleId));
          if (topicRows.length > 0) {
            await tx.insert(articleTopics).values(
              topicRows.map((topic) => ({ articleId, topicId: topic.id })),
            );
          }
        }
      });

      await ensureStoriesBackfilled();
      await ensureFeedRunForDate(currentFeedDate());
      return { received: items.length, inserted, updated };
    },
    async () => {
      await ensureMemorySeeded();
      const store = memoryStore();
      let inserted = 0;
      let updated = 0;
      for (const item of items) {
        const score = incomingArticleScore(item);
        let source = store.sources.find((entry) => entry.slug === item.source.slug);
        if (!source) {
          source = {
            id: uuid(),
            slug: item.source.slug,
            name: item.source.name,
            homepageUrl: item.source.homepage_url ?? null,
            iconUrl: item.source.icon_url ?? null,
          };
          store.sources.push(source);
        } else {
          source.name = item.source.name;
          source.homepageUrl = item.source.homepage_url ?? null;
          source.iconUrl = item.source.icon_url ?? null;
        }

        for (const topic of item.topics) {
          const existingTopic = store.topics.find((entry) => entry.slug === topic.slug);
          if (existingTopic) {
            existingTopic.name = topic.name;
            continue;
          }
          store.topics.push({
            id: uuid(),
            slug: topic.slug,
            name: topic.name,
          });
        }

        const now = new Date().toISOString();
        const existingArticle =
          store.articles.find((entry) => entry.sourceId === source.id && entry.externalId === item.external_id) ??
          store.articles.find((entry) => entry.url === item.url);
        const articleId = existingArticle?.id ?? uuid();
        if (existingArticle) {
          existingArticle.sourceId = source.id;
          existingArticle.externalId = item.external_id;
          existingArticle.title = item.title;
          existingArticle.summary = item.summary;
          existingArticle.author = item.author ?? null;
          existingArticle.url = item.url;
          existingArticle.imageUrl = item.image_url ?? null;
          existingArticle.publishedAt = item.published_at;
          existingArticle.contentText = item.content_text;
          existingArticle.score = score;
          existingArticle.payloadJson = item.payload_json ?? null;
          updated += 1;
        } else {
          store.articles.push({
            id: articleId,
            sourceId: source.id,
            storyId: "",
            externalId: item.external_id,
            title: item.title,
            summary: item.summary,
            author: item.author ?? null,
            url: item.url,
            imageUrl: item.image_url ?? null,
            publishedAt: item.published_at,
            ingestedAt: now,
            contentText: item.content_text,
            score,
            payloadJson: item.payload_json ?? null,
          });
          inserted += 1;
        }

        const article = store.articles.find((entry) => entry.id === articleId)!;
        store.articleTopics = store.articleTopics.filter((entry) => entry.articleId !== articleId);
        for (const topic of item.topics) {
          const topicId = store.topics.find((entry) => entry.slug === topic.slug)?.id;
          if (topicId) {
            store.articleTopics.push({ articleId, topicId });
          }
        }
        if (!article.storyId) {
          article.storyId = "";
        }
      }

      store.stories = [];
      for (const article of [...store.articles].sort((left, right) => +new Date(left.publishedAt) - +new Date(right.publishedAt))) {
        const normalized = normalizeTitle(article.title);
        const fingerprint = storyFingerprint(article.title);
        const articleTopicIds = new Set(
          store.articleTopics.filter((entry) => entry.articleId === article.id).map((entry) => entry.topicId),
        );
        let matchedStory = store.stories.find((story) => {
          const overlap = store.articleTopics
            .filter((entry) => store.articles.find((candidate) => candidate.id === entry.articleId)?.storyId === story.id)
            .some((entry) => articleTopicIds.has(entry.topicId));
          return story.fingerprint === fingerprint || (overlap && diceCoefficient(story.normalizedHeadline, normalized) >= 0.72);
        });

        if (!matchedStory) {
          matchedStory = {
            id: uuid(),
            canonicalHeadline: article.title,
            canonicalSummary: article.summary,
            normalizedHeadline: normalized,
            fingerprint,
            status: "active",
            firstPublishedAt: article.publishedAt,
            lastUpdatedAt: article.publishedAt,
            importanceScore: article.score * 10,
            updateCount: 1,
            sourceCount: 1,
            representativeArticleId: article.id,
            searchDocument: `${article.title} ${article.summary} ${article.contentText}`,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          };
          store.stories.push(matchedStory);
        }
        article.storyId = matchedStory.id;
      }
      recomputeMemoryStoryRollups();
      store.runs = [];
      store.runItems = [];
      store.userDailyFeeds = [];
      store.userDailyFeedItems = [];
      store.initialized = true;

      return { received: items.length, inserted, updated };
    },
  );
}
