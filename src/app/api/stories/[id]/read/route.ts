import { NextResponse } from "next/server";
import { setStoryRead } from "@/lib/services/news-service";
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

  return NextResponse.json(await setStoryRead((await params).id, parsed.data.read));
}
