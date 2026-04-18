import { NextResponse } from "next/server";
import { syncArticles } from "@/lib/services/news-service";
import { parseJsonBody } from "@/lib/utils/request";
import { syncPayloadSchema } from "@/lib/validators/articles";

export async function POST(request: Request) {
  const authHeader = request.headers.get("authorization");
  const expected = process.env.SYNC_API_KEY;

  if (!expected || authHeader !== `Bearer ${expected}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await parseJsonBody(request);
  const parsed = syncPayloadSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid payload" }, { status: 400 });
  }
  return NextResponse.json(await syncArticles(parsed.data.articles));
}
