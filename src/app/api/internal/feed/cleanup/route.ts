import { NextResponse } from "next/server";
import { cleanupAgedStories } from "@/lib/services/news-service";

function isAuthorized(request: Request) {
  const authHeader = request.headers.get("authorization");
  const candidates = [process.env.INTERNAL_API_KEY, process.env.SYNC_API_KEY].filter(Boolean);
  return candidates.some((value) => authHeader === `Bearer ${value}`);
}

export async function POST(request: Request) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  return NextResponse.json(await cleanupAgedStories());
}
