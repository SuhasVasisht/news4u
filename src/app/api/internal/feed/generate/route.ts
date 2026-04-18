import { NextResponse } from "next/server";
import { generateDailyFeed } from "@/lib/services/news-service";
import { parseJsonBody } from "@/lib/utils/request";

function isAuthorized(request: Request) {
  const authHeader = request.headers.get("authorization");
  const candidates = [process.env.INTERNAL_API_KEY, process.env.SYNC_API_KEY].filter(Boolean);
  return candidates.some((value) => authHeader === `Bearer ${value}`);
}

export async function POST(request: Request) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = (await parseJsonBody(request)) as { feed_date?: string; force_refresh?: boolean } | null;
  return NextResponse.json(
    await generateDailyFeed({
      feedDate: body?.feed_date,
      forceRefresh: body?.force_refresh ?? false,
    }),
  );
}
