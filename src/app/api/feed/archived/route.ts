import { NextResponse } from "next/server";
import { getArchivedFeed } from "@/lib/services/news-service";

export async function GET() {
  return NextResponse.json(await getArchivedFeed());
}
