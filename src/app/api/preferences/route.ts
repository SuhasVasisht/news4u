import { NextResponse } from "next/server";
import { getPreferences, updatePreferences } from "@/lib/services/news-service";
import { parseJsonBody } from "@/lib/utils/request";
import { preferencesSchema } from "@/lib/validators/articles";

export async function GET() {
  return NextResponse.json(await getPreferences());
}

export async function POST(request: Request) {
  const payload = await parseJsonBody(request);
  const parsed = preferencesSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid payload" }, { status: 400 });
  }
  return NextResponse.json(await updatePreferences(parsed.data));
}
