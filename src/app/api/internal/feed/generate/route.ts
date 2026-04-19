import { NextResponse } from "next/server";
import { generateDailyFeed } from "@/lib/services/news-service";
import { parseJsonBody } from "@/lib/utils/request";

function isAuthorized(request: Request) {
  const authHeader = request.headers.get("authorization");
  const expected = process.env.SYNC_API_KEY;
  return Boolean(expected && authHeader === `Bearer ${expected}`);
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
