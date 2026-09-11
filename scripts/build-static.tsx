import { build } from "esbuild";
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { readFile, writeFile, mkdir, rename, open, unlink, chmod } from "node:fs/promises";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { NewsEdition } from "../src/components/edition/news-edition";
import { editionSchema, dateInZone, validateBuildFreshness } from "../src/lib/edition";
import { prepareMedia } from "./lib/static-media";
import { verifyDesignOnly } from "./lib/design-only";
import { themeBootstrap } from "../src/lib/edition-themes";

async function main() {
  await mkdir("data", { recursive: true });
  const lock = await open("data/static-build.lock", "wx").catch(() => { throw new Error("Another static build is running (data/static-build.lock)."); });
  try {
    const designOnly = process.argv.includes("--design-only");
    const dateIndex = process.argv.indexOf("--edition-date");
    const editionDate = dateIndex >= 0 ? process.argv[dateIndex + 1] : undefined;
    if (dateIndex >= 0 && (!editionDate || editionDate.startsWith("--") || designOnly)) throw new Error("--edition-date requires an explicit date and cannot be design-only");
    if (designOnly && process.argv.some(arg => ["--collect", "--review-file", "--prepare-review", "--prepare-sports", "--sports-review-file"].includes(arg))) throw new Error("Design-only builds cannot collect or review news");
    const reviewIndex = process.argv.indexOf("--review-file");
    const reviewFile = reviewIndex >= 0 ? process.argv[reviewIndex + 1] : undefined;
    const sportsIndex = process.argv.indexOf("--sports-review-file");
    const sportsFile = sportsIndex >= 0 ? process.argv[sportsIndex + 1] : undefined;
    const prepareSports = process.argv.includes("--prepare-sports");
    if (sportsIndex >= 0 && (!sportsFile || sportsFile.startsWith("--"))) throw new Error("--sports-review-file requires a reviewed JSON file");
    if (reviewIndex >= 0 && (!reviewFile || reviewFile.startsWith("--"))) throw new Error("--review-file requires a reviewed JSON file");
    if (process.argv.includes("--collect") || reviewFile || prepareSports || sportsFile) {
      const cwd = path.resolve("scripts/news_collector");
      const configuredPython = process.env.PYTHON_BIN;
      const python = configuredPython ? configuredPython.includes("/") ? path.resolve(configuredPython) : configuredPython : path.join(cwd, ".venv/bin/python");
      if (prepareSports || sportsFile) {
        execFileSync(python, ["-m", "news_collector.jobs.sports", ...(prepareSports ? ["--prepare-review"] : ["--review-file", path.resolve(sportsFile!)])], { cwd, stdio: "inherit", timeout: 30 * 60_000 });
        if (prepareSports) return;
      }
      if (process.argv.includes("--collect")) {
        const result = execFileSync(python, ["-m", "news_collector.jobs.collect"], { cwd, encoding: "utf8", timeout: 20 * 60_000, maxBuffer: 10 * 1024 * 1024 });
        await writeFile("data/collection-run.json", result);
        console.log(result);
      }
      const reviewArgs = process.argv.includes("--prepare-review") ? ["--prepare-review"] : reviewFile ? ["--review-file", path.resolve(reviewFile)] : [];
      if (!sportsFile) execFileSync(python, ["-m", "news_collector.jobs.editorial", ...reviewArgs], { cwd, stdio: "inherit", timeout: 90 * 60_000 });
      if (process.argv.includes("--prepare-review")) { console.log("Review request prepared. No new paper was published."); return; }
      if (process.argv.includes("--collect")) execFileSync(python, ["-m", "news_collector.jobs.sports"], { cwd, stdio: "inherit", timeout: 30 * 60_000 });
      execFileSync(python, ["-m", "news_collector.jobs.export_edition", ...(editionDate ? ["--edition-date", editionDate] : [])], { cwd, stdio: "inherit", timeout: 60_000 });
    }
    const edition = editionSchema.parse(JSON.parse(await readFile("data/edition.json", "utf8")));
    const today = designOnly ? await verifyDesignOnly(process.cwd(), edition) : validateBuildFreshness(edition, new Date(), editionDate);
    if (!designOnly) {
      await prepareMedia(process.cwd(), edition);
      await writeFile("data/edition.json.tmp", JSON.stringify(edition, null, 2));
      await rename("data/edition.json.tmp", "data/edition.json");
    }
    const todayStories = edition.stories.filter(s => dateInZone(s.publishedAt, edition.timezone) === today);
    const icon = await readFile("src/app/icon.svg", "utf8");
    let css = await readFile("src/components/edition/edition.css", "utf8");
    for (const name of ["newsreader", "newsreader-500", "newsreader-600", "caslon"]) css = css.replace(`/fonts/${name}.ttf`, `data:font/ttf;base64,${(await readFile(`public/fonts/${name}.ttf`)).toString("base64")}`);
    const bundle = await build({ entryPoints: ["scripts/static-client.tsx"], bundle: true, minify: true, write: false, format: "iife", platform: "browser", jsx: "automatic", define: { "process.env.NODE_ENV": '"production"' } });
    const data = JSON.stringify(edition).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
    const body = renderToString(createElement(NewsEdition, { edition, staticMode: true }));
    const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><script>${themeBootstrap}</script><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>News 4 u - ${today}</title><link rel="icon" href="/news-mark.svg" type="image/svg+xml" sizes="any"><style>${css}</style></head><body><div id="edition-root">${body}</div><script type="application/json" id="edition-data">${data}</script><script>${bundle.outputFiles[0].text.replace(/<\/script/gi, "<\\/script")}</script></body></html>`;
    const warnings = edition.sources.filter(s => s.status !== "disabled" && (s.status !== "ok" || s.reason)).map(s => `${s.name}: ${s.reason || s.status}`);
    const review = { builtAt: new Date().toISOString(), editionDate: today, generatedAt: edition.generatedAt, stories: edition.stories.length, publishedToday: todayStories.length, photos: edition.stories.filter(s => s.image).length, warnings, rendering: "Server-rendered HTML with embedded React, CSS, fonts, and data. Publisher images remain remote.", state: "Browser-local. No credentials, account data, or full article bodies exported." };
    await mkdir("out", { recursive: true });
    await writeFile("out/news-mark.svg", icon, { mode: 0o644 });
    // Reports share the edition's assets; the index remains self-contained.
    const assetKey = createHash("sha256").update(css).update(bundle.outputFiles[0].text).digest("hex");
    await writeFile(`out/reader-${assetKey}.css`, css, { mode: 0o644 });
    await writeFile(`out/reader-${assetKey}.js`, bundle.outputFiles[0].text, { mode: 0o644 });
    for (const story of edition.stories) {
      const reportBody = renderToString(createElement(NewsEdition, { edition, staticMode: true, initialStory: story.id }));
      const escaped = (value: string) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
      const report = `<!doctype html><html lang="en"><head><meta charset="utf-8"><script>${themeBootstrap}</script><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escaped(story.title)} | News 4 u</title><link rel="icon" href="/news-mark.svg" type="image/svg+xml" sizes="any"><link rel="stylesheet" href="./reader-${assetKey}.css"></head><body><div id="edition-root" data-story="${escaped(story.id)}">${reportBody}</div><script type="application/json" id="edition-data">${data}</script><script src="./reader-${assetKey}.js"></script></body></html>`;
      const reportPath = `out/report-${encodeURIComponent(story.id)}.html`;
      await writeFile(`${reportPath}.tmp`, report, { mode: 0o644 });
      await rename(`${reportPath}.tmp`, reportPath);
    }
    await writeFile("out/index.html.tmp", html);
    await writeFile("out/reader-assets.json.tmp", JSON.stringify({ generatedAt: edition.generatedAt, key: assetKey }));
    await writeFile("out/build-review.json.tmp", JSON.stringify(review, null, 2));
    await chmod("out/index.html.tmp", 0o644);
    await chmod("out/build-review.json.tmp", 0o644);
    await rename("out/build-review.json.tmp", "out/build-review.json");
    await rename("out/reader-assets.json.tmp", "out/reader-assets.json");
    await rename("out/index.html.tmp", "out/index.html");
    console.log(JSON.stringify(review, null, 2));
  } finally { await lock.close(); await unlink("data/static-build.lock"); }
}
main().catch(error => { console.error(error instanceof Error ? error.message : error); process.exitCode = 1; });
