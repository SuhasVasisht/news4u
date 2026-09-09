import { readFile } from "node:fs/promises";
import path from "node:path";
import { editionSchema, type EditionData, dateInZone } from "@/lib/edition";

export async function getEdition(): Promise<EditionData> {
  try {
    return editionSchema.parse(JSON.parse(await readFile(path.join(process.cwd(), "data/edition.json"), "utf8")));
  } catch (error) {
    if (!(error instanceof Error && "code" in error && error.code === "ENOENT")) throw error;
    const generatedAt = new Date().toISOString();
    return { date: dateInZone(generatedAt, "America/Los_Angeles"), generatedAt, timezone: "America/Los_Angeles", windowHours: 48, stories: [], sources: [] };
  }
}
