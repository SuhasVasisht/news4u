import { z } from "zod";

export const storyReadSchema = z.object({
  read: z.boolean(),
});

export const storySaveSchema = z.object({
  saved: z.boolean(),
});

export const storyArchiveSchema = z.object({
  archived: z.boolean(),
});

export const sourceMutationSchema = z.object({
  hidden: z.boolean(),
});

export const topicMutationSchema = z.object({
  muted: z.boolean(),
});

export const preferencesSchema = z.object({
  theme: z.enum(["light", "dark", "system"]),
  feedDensity: z.enum(["comfortable", "compact"]),
  openOriginalInNewTab: z.boolean(),
});

export const mergeLocalStateSchema = z.object({
  readStoryIds: z.array(z.uuid()).default([]),
  archivedStoryIds: z.array(z.uuid()).default([]),
  dismissedStoryIds: z.array(z.uuid()).default([]),
});

export const syncArticleSchema = z.object({
  external_id: z.string().min(1),
  title: z.string().min(1),
  summary: z.string().min(1),
  author: z.string().nullable().optional(),
  url: z.url(),
  image_url: z.url().nullable().optional(),
  published_at: z.iso.datetime(),
  content_text: z.string().min(1),
  score: z.number().nullable().optional(),
  payload_json: z.record(z.string(), z.unknown()).nullable().optional(),
  source: z.object({
    slug: z.string().min(1),
    name: z.string().min(1),
    homepage_url: z.url().nullable().optional(),
    icon_url: z.url().nullable().optional(),
  }),
  topics: z.array(
    z.object({
      slug: z.string().min(1),
      name: z.string().min(1),
    }),
  ),
});

export const syncPayloadSchema = z.object({
  articles: z.array(syncArticleSchema).min(1).max(500),
});
