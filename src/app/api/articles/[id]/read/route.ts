import { NextResponse } from "next/server";
import { getStoryIdForArticle, setStoryRead } from "@/lib/services/news-service";
import { parseJsonBody } from "@/lib/utils/request";
import { storyReadSchema } from "@/lib/validators/articles";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const payload = await parseJsonBody(request);
  const parsed = storyReadSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid payload" }, { status: 400 });
  }

  const storyId = await getStoryIdForArticle((await params).id);
  if (!storyId) {
    return NextResponse.json({ error: "Article not found" }, { status: 404 });
  }

  return NextResponse.json(await setStoryRead(storyId, parsed.data.read));
}
