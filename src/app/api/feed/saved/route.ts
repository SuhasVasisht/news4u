import { NextResponse } from "next/server";
import { getSavedFeed } from "@/lib/services/news-service";

export async function GET() {
  return NextResponse.json(await getSavedFeed());
}
