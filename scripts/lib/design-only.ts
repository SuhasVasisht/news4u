import { readFile } from "node:fs/promises";
import path from "node:path";
import { editionSchema, type EditionData } from "../../src/lib/edition";

export function assertUnchangedEdition(edition: EditionData, published: EditionData) {
  if (JSON.stringify(edition) !== JSON.stringify(published)) {
    throw new Error("Design-only release must exactly match the published edition. No news, dates, sources, or images may change.");
  }
}

export async function verifyDesignOnly(root: string, edition: EditionData) {
  const html = await readFile(path.join(root, "data/cloudflare-published/index.html"), "utf8");
  const data = html.match(/<script type="application\/json" id="edition-data">([\s\S]*?)<\/script>/)?.[1];
  if (!data) throw new Error("Design-only release requires a verified published edition");
  assertUnchangedEdition(edition, editionSchema.parse(JSON.parse(data)));
  return edition.date;
}
