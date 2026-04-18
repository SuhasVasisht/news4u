import fs from "node:fs";
import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "@/lib/db/schema";

const databaseUrl = process.env.DATABASE_URL;
const isRunningInDocker = fs.existsSync("/.dockerenv");

function canUseConfiguredDatabase() {
  if (!databaseUrl) {
    return false;
  }

  try {
    const url = new URL(databaseUrl);
    if (url.hostname === "db" && !isRunningInDocker) {
      return false;
    }
  } catch {
    return false;
  }

  return true;
}

declare global {
  var __sqlClient__: postgres.Sql | undefined;
}

export const hasDatabase = canUseConfiguredDatabase();

export function getSqlClient() {
  if (!hasDatabase || !databaseUrl) {
    return null;
  }

  if (!globalThis.__sqlClient__) {
    globalThis.__sqlClient__ = postgres(databaseUrl, {
      prepare: false,
      max: 5,
    });
  }

  return globalThis.__sqlClient__;
}

export function getDb() {
  const client = getSqlClient();

  if (!client) {
    return null;
  }

  return drizzle(client, { schema });
}
