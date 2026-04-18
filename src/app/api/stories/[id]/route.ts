import { NextResponse } from "next/server";
import { getStory } from "@/lib/services/news-service";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const story = await getStory((await params).id);
  if (!story) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  return NextResponse.json(story);
}
