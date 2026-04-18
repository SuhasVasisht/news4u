export type Source = {
  id: string;
  slug: string;
  name: string;
  homepageUrl: string | null;
  iconUrl: string | null;
};

export type Topic = {
  id: string;
  slug: string;
  name: string;
};

export type StoryArticle = {
  id: string;
  externalId: string;
  title: string;
  summary: string;
  author: string | null;
  url: string;
  imageUrl: string | null;
  publishedAt: string;
  contentText: string;
  score: number;
  source: Source;
};

export type ViewerStoryState = {
  storyId: string;
  isRead: boolean;
  lastReadAt: string | null;
  isSaved: boolean;
  isArchived: boolean;
  isDismissed: boolean;
};

export type StoryCard = {
  id: string;
  canonicalHeadline: string;
  canonicalSummary: string;
  compactSummary: string | null;
  importanceScore: number;
  updatedAt: string;
  sourceCount: number;
  topics: Topic[];
  representativeArticle: StoryArticle;
  articles: StoryArticle[];
  viewerState: ViewerStoryState;
  dayLabel?: string;
};

export type TodayFeedResponse = {
  date: string;
  important: StoryCard[];
  other: StoryCard[];
  cleared: boolean;
};

export type CatchupGroup = {
  label: string;
  date: string;
  items: StoryCard[];
};

export type CatchupFeedResponse = {
  date: string;
  groups: CatchupGroup[];
};

export type SavedFeedResponse = {
  items: StoryCard[];
};

export type ArchivedFeedResponse = {
  items: StoryCard[];
};

export type StoryDetail = StoryCard;

export type SourcePreference = {
  sourceId: string;
  isHidden: boolean;
};

export type TopicPreference = {
  topicId: string;
  isMuted: boolean;
};

export type AppPreferences = {
  theme: "light" | "dark" | "system";
  feedDensity: "comfortable" | "compact";
  openOriginalInNewTab: boolean;
};

export type UserPreferences = AppPreferences & {
  timezone: string;
  dailyResetHour: number;
  catchupDays: number;
};

export type ShellData = {
  sources: Array<Source & { hidden: boolean }>;
  topics: Array<Topic & { muted: boolean; storyCount: number }>;
  savedCount: number;
  user: {
    name: string | null;
    email: string | null;
    image: string | null;
    isAuthenticated: boolean;
  };
};

export type SyncArticleInput = {
  external_id: string;
  title: string;
  summary: string;
  author?: string | null;
  url: string;
  image_url?: string | null;
  published_at: string;
  content_text: string;
  score?: number | null;
  payload_json?: Record<string, unknown> | null;
  source: {
    slug: string;
    name: string;
    homepage_url?: string | null;
    icon_url?: string | null;
  };
  topics: Array<{
    slug: string;
    name: string;
  }>;
};

export type LocalStoryStateInput = {
  readStoryIds: string[];
  archivedStoryIds: string[];
  dismissedStoryIds: string[];
};
