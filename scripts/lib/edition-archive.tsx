/* eslint-disable @next/next/no-html-link-for-pages -- Standalone HTML has no Next router. */
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { mkdir, readFile, writeFile, readdir, rename } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { NewsEdition } from "../../src/components/edition/news-edition";
import { editionSchema, type EditionData } from "../../src/lib/edition";
import { themeBootstrap } from "../../src/lib/edition-themes";

export const escapeHtml = (value: string) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
export function embeddedEdition(html: string) {
  const json = html.match(/<script type="application\/json" id="edition-data">([\s\S]*?)<\/script>/)?.[1];
  if (!json) throw new Error("Edition data missing from HTML");
  return editionSchema.parse(JSON.parse(json));
}

export async function archiveEdition(bundle: string, edition: EditionData, assetKey: string, revise = false, refreshDesign = false) {
  edition = editionSchema.parse(edition);
  if (!edition.editorialReviewedAt) throw new Error("Cannot archive an unreviewed edition");
  if (!/^[a-zA-Z0-9]+$/.test(assetKey) || edition.stories.some(story => !/^[a-f0-9]{20}$/.test(story.id))) throw new Error("Unsafe archive identifier");
  const directory = path.join(bundle, "editions", edition.date);
  try {
    const existing = editionSchema.parse(JSON.parse(await readFile(path.join(directory, "edition.json"), "utf8")));
    if (JSON.stringify(existing) === JSON.stringify(edition)) {
      if (!refreshDesign) return;
    } else {
      if (refreshDesign) throw new Error("Cannot refresh archive design with different edition data");
      if (!revise) throw new Error(`Published edition ${edition.date} is immutable; use an explicit current-day revision to preserve and supersede it`);
      const revision = createHash("sha256").update(JSON.stringify(existing)).digest("hex").slice(0, 12);
      await rename(directory, `${directory}-r${revision}`);
    }
  } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
  await mkdir(directory, { recursive: true });
  const data = JSON.stringify(edition).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
  for (const story of [null, ...edition.stories]) {
    const body = renderToString(createElement(NewsEdition, { edition, staticMode: true, archivedEdition: true, initialStory: story?.id || null }));
    const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><script>${themeBootstrap}</script><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(story?.title || `News 4 u - ${edition.date}`)}</title><link rel="icon" href="/news-mark.svg" type="image/svg+xml" sizes="any"><link rel="stylesheet" href="../../reader-${assetKey}.css"></head><body><div id="edition-root" data-archive="true"${story ? ` data-story="${escapeHtml(story.id)}"` : ""}>${body}</div><script type="application/json" id="edition-data">${data}</script><script src="../../reader-${assetKey}.js"></script></body></html>`;
    await writeFile(path.join(directory, story ? `report-${story.id}.html` : "index.html"), html);
  }
  // Written last: incomplete staging is retried rather than treated as a frozen edition.
  await writeFile(path.join(directory, "edition.json"), JSON.stringify(edition));
}

export async function archiveIndex(bundle: string, assetKey: string) {
  const editions: EditionData[] = [];
  const names = await readdir(path.join(bundle, "editions"));
  for (const date of names) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) continue;
    editions.push(editionSchema.parse(JSON.parse(await readFile(path.join(bundle, "editions", date, "edition.json"), "utf8"))));
  }
  editions.sort((a, b) => b.date.localeCompare(a.date));
  const body = renderToString(<main className="edition-archive"><a href="/">News 4 u. / Latest edition</a><h1>Past editions</h1>{editions.map(edition => <article key={edition.date}><div><time dateTime={edition.date}>{edition.date}</time><br /><small>{edition.stories.length} stories</small></div><div><h2><a href={`./${edition.date}/`}>{new Intl.DateTimeFormat("en-US", { dateStyle: "long", timeZone: "UTC" }).format(new Date(`${edition.date}T12:00:00Z`))}</a></h2><p>{edition.stories.slice(0, 3).map(s => s.title).join(" / ")}</p>{names.filter(name => new RegExp(`^${edition.date}-r[a-f0-9]{12}$`).test(name)).map((name, i) => <p key={name}><a href={`./${name}/`}>Earlier version {i + 1}</a></p>)}</div></article>)}</main>);
  await writeFile(path.join(bundle, "editions/index.html"), `<!doctype html><html lang="en"><head><meta charset="utf-8"><script>${themeBootstrap}</script><meta name="viewport" content="width=device-width,initial-scale=1"><title>Past editions | News 4 u</title><link rel="icon" href="/news-mark.svg" type="image/svg+xml" sizes="any"><link rel="stylesheet" href="../reader-${assetKey}.css"></head><body>${body}</body></html>`);
  return editions.map(edition => ({ date: edition.date, stories: edition.stories.length }));
}
