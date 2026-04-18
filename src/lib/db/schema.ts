import {
  boolean,
  date,
  index,
  integer,
  jsonb,
  pgTable,
  primaryKey,
  real,
  smallint,
  text,
  timestamp,
  unique,
  uuid,
  varchar,
} from "drizzle-orm/pg-core";

export const users = pgTable("users", {
  id: text("id").primaryKey(),
  name: text("name"),
  email: text("email").unique(),
  emailVerified: timestamp("email_verified", { withTimezone: true }),
  image: text("image"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
  isActive: boolean("is_active").default(true).notNull(),
  lastLoginAt: timestamp("last_login_at", { withTimezone: true }),
});

export const accounts = pgTable(
  "accounts",
  {
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    type: text("type").notNull(),
    provider: text("provider").notNull(),
    providerAccountId: text("provider_account_id").notNull(),
    refreshToken: text("refresh_token"),
    accessToken: text("access_token"),
    expiresAt: integer("expires_at"),
    tokenType: text("token_type"),
    scope: text("scope"),
    idToken: text("id_token"),
    sessionState: text("session_state"),
  },
  (table) => [
    primaryKey({ columns: [table.provider, table.providerAccountId] }),
    index("accounts_user_id_idx").on(table.userId),
  ],
);

export const sessions = pgTable(
  "sessions",
  {
    sessionToken: text("session_token").primaryKey(),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    expires: timestamp("expires", { withTimezone: true }).notNull(),
  },
  (table) => [index("sessions_user_id_idx").on(table.userId)],
);

export const verificationTokens = pgTable(
  "verification_tokens",
  {
    identifier: text("identifier").notNull(),
    token: text("token").notNull(),
    expires: timestamp("expires", { withTimezone: true }).notNull(),
  },
  (table) => [primaryKey({ columns: [table.identifier, table.token] })],
);

export const sources = pgTable("sources", {
  id: uuid("id").defaultRandom().primaryKey(),
  slug: varchar("slug", { length: 120 }).notNull().unique(),
  name: text("name").notNull(),
  domain: text("domain"),
  homepageUrl: text("homepage_url"),
  iconUrl: text("icon_url"),
  isActive: boolean("is_active").default(true).notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const topics = pgTable("topics", {
  id: uuid("id").defaultRandom().primaryKey(),
  slug: varchar("slug", { length: 120 }).notNull().unique(),
  name: text("name").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const stories = pgTable(
  "stories",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    canonicalHeadline: text("canonical_headline").notNull(),
    canonicalSummary: text("canonical_summary").notNull(),
    normalizedHeadline: text("normalized_headline").notNull(),
    fingerprint: varchar("fingerprint", { length: 255 }).notNull(),
    status: varchar("status", { length: 24 }).default("active").notNull(),
    firstPublishedAt: timestamp("first_published_at", { withTimezone: true }).notNull(),
    lastUpdatedAt: timestamp("last_updated_at", { withTimezone: true }).notNull(),
    importanceScore: real("importance_score").default(0).notNull(),
    updateCount: integer("update_count").default(0).notNull(),
    sourceCount: integer("source_count").default(0).notNull(),
    representativeArticleId: uuid("representative_article_id"),
    searchDocument: text("search_document").default("").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => [
    index("stories_last_updated_at_idx").on(table.lastUpdatedAt),
    index("stories_importance_score_idx").on(table.importanceScore),
    index("stories_fingerprint_idx").on(table.fingerprint),
  ],
);

export const articles = pgTable(
  "articles",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    sourceId: uuid("source_id")
      .notNull()
      .references(() => sources.id, { onDelete: "cascade" }),
    storyId: uuid("story_id").references(() => stories.id, { onDelete: "set null" }),
    externalId: text("external_id").notNull(),
    title: text("title").notNull(),
    summary: text("summary").notNull(),
    author: text("author"),
    url: text("url").notNull().unique(),
    imageUrl: text("image_url"),
    publishedAt: timestamp("published_at", { withTimezone: true }).notNull(),
    ingestedAt: timestamp("ingested_at", { withTimezone: true }).defaultNow().notNull(),
    contentText: text("content_text").notNull(),
    score: real("score").default(0).notNull(),
    payloadJson: jsonb("payload_json"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => [
    unique("articles_source_external_unique").on(table.sourceId, table.externalId),
    index("articles_published_at_idx").on(table.publishedAt),
    index("articles_story_id_idx").on(table.storyId),
    index("articles_source_idx").on(table.sourceId),
  ],
);

export const storyArticles = pgTable(
  "story_articles",
  {
    storyId: uuid("story_id")
      .notNull()
      .references(() => stories.id, { onDelete: "cascade" }),
    articleId: uuid("article_id")
      .notNull()
      .references(() => articles.id, { onDelete: "cascade" }),
  },
  (table) => [primaryKey({ columns: [table.storyId, table.articleId] })],
);

export const articleTopics = pgTable(
  "article_topics",
  {
    articleId: uuid("article_id")
      .notNull()
      .references(() => articles.id, { onDelete: "cascade" }),
    topicId: uuid("topic_id")
      .notNull()
      .references(() => topics.id, { onDelete: "cascade" }),
  },
  (table) => [primaryKey({ columns: [table.articleId, table.topicId] })],
);

export const dailyFeedRuns = pgTable(
  "daily_feed_runs",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    feedDate: date("feed_date").notNull().unique(),
    generatedAt: timestamp("generated_at", { withTimezone: true }).defaultNow().notNull(),
    algorithmVersion: varchar("algorithm_version", { length: 64 }).notNull(),
    notes: text("notes"),
  },
  (table) => [index("daily_feed_runs_date_idx").on(table.feedDate)],
);

export const dailyFeedItems = pgTable(
  "daily_feed_items",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    feedRunId: uuid("feed_run_id")
      .notNull()
      .references(() => dailyFeedRuns.id, { onDelete: "cascade" }),
    storyId: uuid("story_id")
      .notNull()
      .references(() => stories.id, { onDelete: "cascade" }),
    section: varchar("section", { length: 32 }).notNull(),
    rankScore: real("rank_score").notNull(),
    rankPosition: integer("rank_position").notNull(),
    compactSummary: text("compact_summary"),
    reasonJson: jsonb("reason_json"),
  },
  (table) => [
    unique("daily_feed_items_unique").on(table.feedRunId, table.storyId, table.section),
    index("daily_feed_items_section_rank_idx").on(table.feedRunId, table.section, table.rankPosition),
  ],
);

export const userDailyFeeds = pgTable(
  "user_daily_feeds",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    feedDate: date("feed_date").notNull(),
    generatedFromFeedRunId: uuid("generated_from_feed_run_id")
      .notNull()
      .references(() => dailyFeedRuns.id, { onDelete: "cascade" }),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
    clearedAt: timestamp("cleared_at", { withTimezone: true }),
    status: varchar("status", { length: 24 }).default("active").notNull(),
  },
  (table) => [
    unique("user_daily_feeds_unique").on(table.userId, table.feedDate),
    index("user_daily_feeds_user_date_idx").on(table.userId, table.feedDate),
  ],
);

export const userDailyFeedItems = pgTable(
  "user_daily_feed_items",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userDailyFeedId: uuid("user_daily_feed_id")
      .notNull()
      .references(() => userDailyFeeds.id, { onDelete: "cascade" }),
    storyId: uuid("story_id")
      .notNull()
      .references(() => stories.id, { onDelete: "cascade" }),
    tab: varchar("tab", { length: 24 }).notNull(),
    section: varchar("section", { length: 24 }).notNull(),
    rankPosition: integer("rank_position").notNull(),
    isRead: boolean("is_read").default(false).notNull(),
    isDismissed: boolean("is_dismissed").default(false).notNull(),
    isArchived: boolean("is_archived").default(false).notNull(),
    surfacedReason: text("surfaced_reason"),
    summaryOverride: text("summary_override"),
  },
  (table) => [
    unique("user_daily_feed_items_unique").on(table.userDailyFeedId, table.storyId, table.tab),
    index("user_daily_feed_items_tab_rank_idx").on(table.userDailyFeedId, table.tab, table.section, table.rankPosition),
  ],
);

export const userStoryState = pgTable(
  "user_story_state",
  {
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    storyId: uuid("story_id")
      .notNull()
      .references(() => stories.id, { onDelete: "cascade" }),
    firstSeenAt: timestamp("first_seen_at", { withTimezone: true }).defaultNow().notNull(),
    lastSeenAt: timestamp("last_seen_at", { withTimezone: true }).defaultNow().notNull(),
    lastReadAt: timestamp("last_read_at", { withTimezone: true }),
    isRead: boolean("is_read").default(false).notNull(),
    isSaved: boolean("is_saved").default(false).notNull(),
    isArchived: boolean("is_archived").default(false).notNull(),
    isDismissed: boolean("is_dismissed").default(false).notNull(),
    isHidden: boolean("is_hidden").default(false).notNull(),
    archivedAt: timestamp("archived_at", { withTimezone: true }),
    carryoverCount: integer("carryover_count").default(0).notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.userId, table.storyId] }),
    index("user_story_state_user_flags_idx").on(
      table.userId,
      table.isRead,
      table.isArchived,
      table.isSaved,
    ),
    index("user_story_state_user_seen_idx").on(table.userId, table.lastSeenAt),
  ],
);

export const userSourcePreferences = pgTable(
  "user_source_preferences",
  {
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    sourceId: uuid("source_id")
      .notNull()
      .references(() => sources.id, { onDelete: "cascade" }),
    isHidden: boolean("is_hidden").default(false).notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => [primaryKey({ columns: [table.userId, table.sourceId] })],
);

export const userTopicPreferences = pgTable(
  "user_topic_preferences",
  {
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    topicId: uuid("topic_id")
      .notNull()
      .references(() => topics.id, { onDelete: "cascade" }),
    isMuted: boolean("is_muted").default(false).notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => [primaryKey({ columns: [table.userId, table.topicId] })],
);

export const userPreferences = pgTable("user_preferences", {
  userId: text("user_id")
    .primaryKey()
    .references(() => users.id, { onDelete: "cascade" }),
  theme: varchar("theme", { length: 20 }).default("system").notNull(),
  feedDensity: varchar("feed_density", { length: 20 }).default("comfortable").notNull(),
  openOriginalInNewTab: boolean("open_original_in_new_tab").default(true).notNull(),
  timezone: varchar("timezone", { length: 64 }).default("America/Los_Angeles").notNull(),
  dailyResetHour: smallint("daily_reset_hour").default(5).notNull(),
  catchupDays: smallint("catchup_days").default(3).notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});
