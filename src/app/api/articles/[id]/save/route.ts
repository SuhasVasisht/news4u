import { NextResponse } from "next/server";
import { getStoryIdForArticle, setStorySaved } from "@/lib/services/news-service";
import { parseJsonBody } from "@/lib/utils/request";
import { storySaveSchema } from "@/lib/validators/articles";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const payload = await parseJsonBody(request);
  const parsed = storySaveSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid payload" }, { status: 400 });
  }

  const storyId = await getStoryIdForArticle((await params).id);
  if (!storyId) {
    return NextResponse.json({ error: "Article not found" }, { status: 404 });
  }

  return NextResponse.json(await setStorySaved(storyId, parsed.data.saved));
}
