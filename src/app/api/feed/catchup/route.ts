import { NextResponse } from "next/server";
import { getCatchupFeed } from "@/lib/services/news-service";

export async function GET() {
  return NextResponse.json(await getCatchupFeed());
}
