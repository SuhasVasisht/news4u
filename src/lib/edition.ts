import { z } from "zod";

const webUrl = z.string().url().refine((value) => /^https?:\/\//i.test(value), "HTTP(S) URL required");
export const editionStorySchema = z.object({
  id: z.string(), title: z.string(), summary: z.string(),
  sector: z.string(), url: webUrl, image: webUrl.nullable(),
  imageAsset: z.object({ src: z.string().regex(/^\/media\/[a-f0-9]{64}\.webp$/), width: z.number().int().positive(), height: z.number().int().positive(), credit: z.string(), licenseUrl: webUrl }).optional(),
  publishedAt: z.string().datetime({ offset: true }), score: z.number().min(0).max(10),
  publisher: z.string(), collectors: z.array(z.string()),
  kind: z.enum(["reporting", "analysis", "podcast", "announcement"]).optional(),
  points: z.array(z.string()).optional(),
  sections: z.array(z.object({ heading: z.string(), body: z.string() })).optional(),
  caveats: z.array(z.string()).optional(),
  contentBasis: z.string().optional(), editorialReason: z.string().optional(),
  audioUrl: webUrl.nullable().optional(), duration: z.number().nullable().optional(),
  quality: z.number().min(0).max(100).optional(), longform: z.boolean().optional(),
  importance: z.number().min(0).max(100).optional(), editorialRank: z.number().int().nonnegative().optional(),
  coverage: z.array(z.object({ title: z.string(), publisher: z.string(), url: webUrl })),
});
export const editionSchema = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/), generatedAt: z.string().datetime({ offset: true }),
  timezone: z.string(), windowHours: z.number(), stories: z.array(editionStorySchema),
  editorialReviewedAt: z.string().datetime({ offset: true }).optional(),
  sources: z.array(z.object({ name: z.string(), status: z.string(), count: z.number(), latest: z.string().nullable(), reason: z.string().nullable(),
    collected: z.number().optional(), eligible: z.number().optional(), candidates: z.number().optional(), reviewed: z.number().optional(), published: z.number().optional(), checkedAt: z.string().nullable().optional() })),
});
export type EditionData = z.infer<typeof editionSchema>;
export type EditionStory = z.infer<typeof editionStorySchema>;
export type EditionView = "Today" | "I do not have time" | "Catch up" | "Saved" | "Archived" | "Sources" | "Settings";
export type ReaderState = { saved: string[]; read: string[]; archived: string[]; hiddenSources: string[]; order: string[]; library: EditionStory[] };
export const emptyReaderState: ReaderState = { saved: [], read: [], archived: [], hiddenSources: [], order: [], library: [] };
export function parseReaderState(value: unknown): ReaderState {
  const parsed = z.object({ saved: z.array(z.string()).default([]), read: z.array(z.string()).default([]), archived: z.array(z.string()).default([]), hiddenSources: z.array(z.string()).default([]), order: z.array(z.string()).default([]), library: z.array(editionStorySchema).default([]) }).safeParse(value);
  return parsed.success ? parsed.data : { ...emptyReaderState };
}
export function sectorStories(stories: EditionStory[], sort: string, order: string[]) {
  const ranks = new Map(order.map((id, i) => [id, i]));
  return [...stories].sort((a, b) => sort === "latest" ? Date.parse(b.publishedAt) - Date.parse(a.publishedAt) : sort === "custom" ? (ranks.get(a.id) ?? 1e6) - (ranks.get(b.id) ?? 1e6) || b.score - a.score : (a.editorialRank ?? 1e6) - (b.editorialRank ?? 1e6) || b.score - a.score || Date.parse(b.publishedAt) - Date.parse(a.publishedAt));
}
export function dateInZone(value: string, timezone: string) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
}

export function briefingStories(stories: EditionStory[], limit = 8) {
  const priority = (s: EditionStory) => (s.importance === undefined ? s.score : s.importance / 10) - (/\b(stock unloaded|takes .* position|average rating|reaffirms|receives a buy rating|price target)\b/i.test(s.title) ? 4 : 0);
  const ranked = [...stories].sort((a, b) => priority(b) - priority(a) || Date.parse(b.publishedAt) - Date.parse(a.publishedAt) || a.id.localeCompare(b.id));
  const selected: EditionStory[] = [];
  const sectors = new Set<string>();
  for (const story of ranked) {
    if (!sectors.has(story.sector) && selected.length < limit) {
      selected.push(story);
      sectors.add(story.sector);
    }
  }
  for (const story of ranked) {
    if (selected.length >= limit) break;
    if (!selected.includes(story) && selected.filter(s => s.publisher === story.publisher).length < 2) selected.push(story);
  }
  return selected.sort((a, b) => priority(b) - priority(a) || Date.parse(b.publishedAt) - Date.parse(a.publishedAt));
}

export function validateBuildFreshness(edition: EditionData, now = new Date()) {
  const today = dateInZone(now.toISOString(), edition.timezone);
  const age = now.getTime() - Date.parse(edition.generatedAt);
  if (edition.date !== today || age > 24 * 3600_000 || age < -300_000) throw new Error("Refusing to publish a stale or future snapshot. Run npm run build:daily.");
  if (!edition.stories.some(s => dateInZone(s.publishedAt, edition.timezone) === today)) throw new Error("No stories published today. Previous static HTML was not replaced.");
  if (new Set(edition.stories.map(s => s.id)).size !== edition.stories.length) throw new Error("Duplicate story identifiers");
  if (edition.stories.some(s => Date.parse(s.publishedAt) > now.getTime() + 300_000)) throw new Error("Future-dated stories in edition");
  return today;
}
