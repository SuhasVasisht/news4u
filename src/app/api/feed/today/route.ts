import { NextResponse } from "next/server";
import { getTodayFeed } from "@/lib/services/news-service";

export async function GET() {
  return NextResponse.json(await getTodayFeed());
}
