import { eq } from "drizzle-orm";
import { getDb, hasDatabase } from "@/lib/db/client";
import { dailyFeedRuns } from "@/lib/db/schema";
import { currentFeedDate } from "@/lib/services/news-service";

export async function getStartupCatchupState(now = new Date()) {
  const feedDate = currentFeedDate(now);

  if (!hasDatabase) {
    return {
      enabled: false,
      feedDate,
      needed: false,
      reason: "database unavailable",
    } as const;
  }

  const db = getDb();
  if (!db) {
    return {
      enabled: false,
      feedDate,
      needed: false,
      reason: "database unavailable",
    } as const;
  }

  const existing = await db
    .select({ id: dailyFeedRuns.id })
    .from(dailyFeedRuns)
    .where(eq(dailyFeedRuns.feedDate, feedDate))
    .limit(1);

  return {
    enabled: true,
    feedDate,
    needed: existing.length === 0,
    reason: existing.length === 0 ? "missing feed run" : "feed run already present",
  } as const;
}
