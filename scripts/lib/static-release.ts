import { createHash } from "node:crypto";
import { readFile, writeFile, mkdir, readdir, lstat, mkdtemp, rename, rm, cp } from "node:fs/promises";
import path from "node:path";
import { editionSchema, validateBuildFreshness, type EditionData } from "../../src/lib/edition";
import { archiveEdition, archiveIndex, embeddedEdition } from "./edition-archive";
import { verifyDesignOnly } from "./design-only";

export const hash = (body: string | Buffer) => createHash("sha256").update(body).digest("hex");

export function assertNewEdition(edition: EditionData, previous: EditionData) {
  if (previous.date >= edition.date) return;
  const canonical = (value: string) => {
    const url = new URL(value);
    url.hash = "";
    for (const key of [...url.searchParams.keys()]) {
      if (/^(utm_|at_|fbclid$|gclid$)/i.test(key)) url.searchParams.delete(key);
    }
    url.searchParams.sort();
    return url.toString().replace(/\/$/, "");
  };
  const ids = new Set(previous.stories.map(story => story.id));
  const urls = new Set(previous.stories.flatMap(story => [story.url, ...story.coverage.map(item => item.url)]).map(canonical));
  for (const story of edition.stories) {
    if (ids.has(story.id) || urls.has(canonical(story.url))) {
      throw new Error(`Previously published story from ${previous.date}: ${story.title}. Re-run editorial review.`);
    }
  }
}
export const publicFile = (name: string) => /^(index\.html|news-mark\.svg|report-[a-f0-9]{20}\.html|reader-[a-zA-Z0-9]+\.(css|js)|404\.html|_headers|edition-manifest\.json|media\/[a-f0-9]{64}\.webp|editions\/index\.html|editions\/\d{4}-\d{2}-\d{2}(-r[a-f0-9]{12})?\/(index\.html|edition\.json|report-[a-f0-9]{20}\.html))$/.test(name);

export async function releaseFiles(directory: string, prefix = ""): Promise<string[]> {
  const files: string[] = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const name = `${prefix}${entry.name}`;
    if (entry.isDirectory() && /^(media|editions|editions\/\d{4}-\d{2}-\d{2}(-r[a-f0-9]{12})?)$/.test(name)) files.push(...await releaseFiles(path.join(directory, entry.name), `${name}/`));
    else if (entry.isFile()) files.push(name);
    else throw new Error(`Unexpected directory or non-file in release: ${name}`);
  }
  return files;
}

export async function retainPublishedRelease(root: string) {
  const destination = path.join(root, "data/cloudflare-published");
  const next = await mkdtemp(path.join(root, "data/cloudflare-published-stage-"));
  try {
    await cp(path.join(root, "data/cloudflare-bundle"), next, { recursive: true });
    const previous = `${destination}.previous`;
    await rm(previous, { recursive: true, force: true });
    try { await rename(destination, previous); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
    await rename(next, destination);
  } finally { await rm(next, { recursive: true, force: true }); }
}
export function assertPublicFile(name: string, body: Buffer, secrets: string[]) {
  if (!publicFile(name)) throw new Error(`Unexpected public file: ${name}`);
  if (body.length > 25 * 1024 * 1024) throw new Error(`Cloudflare's 25 MiB file limit exceeded: ${name}`);
  if (secrets.some(value => value.length >= 12 && body.includes(value))) throw new Error(`Credential found in public file: ${name}`);
}

export async function prepareRelease(root: string, secrets: string[], options: { reviseToday?: boolean; designOnly?: boolean; editionDate?: string } = {}) {
  const edition = editionSchema.parse(JSON.parse(await readFile(path.join(root, "data/edition.json"), "utf8")));
  if (options.designOnly) await verifyDesignOnly(root, edition);
  else validateBuildFreshness(edition, new Date(), options.editionDate);
  if (!edition.editorialReviewedAt) throw new Error("Only editorially reviewed editions can be deployed");
  const index = await readFile(path.join(root, "out/index.html"), "utf8");
  const embedded = index.match(/<script type="application\/json" id="edition-data">([\s\S]*?)<\/script>/)?.[1];
  if (!embedded || JSON.stringify(editionSchema.parse(JSON.parse(embedded))) !== JSON.stringify(edition)) throw new Error("Static HTML differs from the reviewed snapshot; run npm run build:static");
  const destination = path.join(root, "data/cloudflare-bundle");
  await mkdir(destination, { recursive: true });
  let source = path.join(root, "data/cloudflare-published");
  try { await lstat(path.join(source, "edition-manifest.json")); }
  catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; source = destination; }
  const bundle = await mkdtemp(path.join(root, "data/cloudflare-stage-"));
  try {
  for (const name of await releaseFiles(source)) {
    const body = await readFile(path.join(source, name));
    assertPublicFile(name, body, secrets);
    await mkdir(path.dirname(path.join(bundle, name)), { recursive: true });
    await writeFile(path.join(bundle, name), body);
  }
  let previous;
  try { previous = embeddedEdition(await readFile(path.join(bundle, "index.html"), "utf8")); }
  catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
  if (options.editionDate && previous?.date !== edition.date) throw new Error("Explicit dated revisions must target the currently published edition");
  if (previous) assertNewEdition(edition, previous);
  for (const name of await releaseFiles(bundle)) {
    if (/^editions\/[^/]+\/edition\.json$/.test(name)) {
      assertNewEdition(edition, editionSchema.parse(JSON.parse(await readFile(path.join(bundle, name), "utf8"))));
    }
  }
  // This directory contains only releases we have explicitly staged, not arbitrary out/ files.
  let key = edition.generatedAt.replace(/[^a-zA-Z0-9]/g, "");
  try {
    const assets = JSON.parse(await readFile(path.join(root, "out/reader-assets.json"), "utf8")) as { generatedAt: string; key: string };
    if (assets.generatedAt !== edition.generatedAt || !/^[a-f0-9]{64}$/.test(assets.key)) throw new Error("Reader asset manifest does not match the edition");
    key = assets.key;
  } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
  const current = ["index.html", "news-mark.svg", `reader-${key}.css`, `reader-${key}.js`, ...edition.stories.map(s => `report-${s.id}.html`), ...new Set(edition.stories.flatMap(s => s.imageAsset ? [s.imageAsset.src.slice(1)] : []))];
  for (const name of current) {
    const file = path.join(root, "out", name);
    if (!(await lstat(file)).isFile()) throw new Error(`Not a regular file: ${name}`);
    const body = await readFile(file);
    assertPublicFile(name, body, secrets);
    await mkdir(path.dirname(path.join(bundle, name)), { recursive: true });
    await writeFile(path.join(bundle, name), body);
  }
  if (previous && previous.date !== edition.date) await archiveEdition(bundle, previous, key);
  await archiveEdition(bundle, edition, key, options.reviseToday, options.designOnly);
  const editions = await archiveIndex(bundle, key);
  const revisions = [];
  for (const name of await readdir(path.join(bundle, "editions"))) {
    if (!/^\d{4}-\d{2}-\d{2}-r[a-f0-9]{12}$/.test(name)) continue;
    const archived = editionSchema.parse(JSON.parse(await readFile(path.join(bundle, "editions", name, "edition.json"), "utf8")));
    revisions.push({ date: archived.date, path: name, stories: archived.stories.length });
  }
  await writeFile(path.join(bundle, "404.html"), '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Report not found | News 4 u</title><h1>Report not found</h1><p><a href="/">Read the current edition</a></p></html>');
  await writeFile(path.join(bundle, "_headers"), "/*\n  Cache-Control: public, max-age=0, must-revalidate\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: no-referrer\n  X-Frame-Options: DENY\n");
  const files: Record<string, string> = {};
  for (const name of await releaseFiles(bundle)) {
    if (name === "edition-manifest.json") continue;
    if (!(await lstat(path.join(bundle, name))).isFile()) throw new Error(`Non-file in release: ${name}`);
    const body = await readFile(path.join(bundle, name));
    assertPublicFile(name, body, secrets);
    files[name] = hash(body);
  }
  if (Object.keys(files).length + 1 > 20000) throw new Error("Cloudflare Free file limit exceeded; archive old releases before deployment");
  const manifest = { date: edition.date, generatedAt: edition.generatedAt, stories: edition.stories.length, editions, revisions, files };
  await writeFile(path.join(bundle, "edition-manifest.json"), JSON.stringify(manifest, null, 2));
  const previousBundle = `${destination}.previous`;
  await rm(previousBundle, { recursive: true, force: true });
  await rename(destination, previousBundle);
  try { await rename(bundle, destination); }
  catch (error) { await rename(previousBundle, destination); throw error; }
  return { bundle: destination, manifest, edition };
  } finally { await rm(bundle, { recursive: true, force: true }); }
}
