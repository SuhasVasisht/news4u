import { NextResponse } from "next/server";
import { setTopicMuted } from "@/lib/services/news-service";
import { parseJsonBody } from "@/lib/utils/request";
import { topicMutationSchema } from "@/lib/validators/articles";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const payload = await parseJsonBody(request);
  const parsed = topicMutationSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid payload" }, { status: 400 });
  }
  const result = await setTopicMuted((await params).id, parsed.data.muted);
  return NextResponse.json(result);
}
