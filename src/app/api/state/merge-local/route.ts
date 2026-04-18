import { NextResponse } from "next/server";
import { mergeLocalState } from "@/lib/services/news-service";
import { parseJsonBody } from "@/lib/utils/request";
import { mergeLocalStateSchema } from "@/lib/validators/articles";

export async function POST(request: Request) {
  const payload = await parseJsonBody(request);
  const parsed = mergeLocalStateSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid payload" }, { status: 400 });
  }

  return NextResponse.json(await mergeLocalState(parsed.data));
}
