import { NextResponse } from "next/server";
import { clearToday } from "@/lib/services/news-service";

export async function POST() {
  return NextResponse.json(await clearToday());
}
