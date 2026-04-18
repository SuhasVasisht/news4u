import { NextResponse } from "next/server";
import { setSourceHidden } from "@/lib/services/news-service";
import { parseJsonBody } from "@/lib/utils/request";
import { sourceMutationSchema } from "@/lib/validators/articles";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const payload = await parseJsonBody(request);
  const parsed = sourceMutationSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid payload" }, { status: 400 });
  }
  const result = await setSourceHidden((await params).id, parsed.data.hidden);
  return NextResponse.json(result);
}
