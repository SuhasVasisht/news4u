import { NextResponse } from "next/server";
import { hasDatabase } from "@/lib/db/client";

export async function GET() {
  return NextResponse.json({
    status: "ok",
    databaseConfigured: hasDatabase,
    version: "0.1.0",
  });
}
