import { publisherStdio } from "./lib/publisher-stdio";
import { execFileSync } from "node:child_process";
import { loadEnvFile } from "node:process";
import { readFile, readdir, stat } from "node:fs/promises";
import path from "node:path";
import { dateInZone, editionSchema, validateBuildFreshness } from "../src/lib/edition";
import { atomicJson, readJson, reusable, runStages, type RunState, type Stage } from "./lib/daily-publisher";
import { fetchPublic, restorePublication } from "./lib/restore-publication";
import { hash, releaseFiles, prepareRelease } from "./lib/static-release";
import { verifyLocalRelease } from "./lib/verify-local-release";

async function checkpointArtifacts(state: RunState) {
  const files: string[] = [];
  if (state.completed.includes("collect")) files.push("data/collection-run.json");
  if (state.completed.includes("editorial")) files.push("data/editorial/latest.json");
  if (state.completed.includes("sports")) files.push("data/sports/latest.json");
  if (state.completed.includes("export")) files.push("data/edition.json", "data/edition-audit.json", "data/source-audit.json");
  try {
    if (state.completed.includes("build")) files.push(...(await releaseFiles("out")).map(file => `out/${file}`));
    const db = state.completed.includes("collect") ? await stat(process.env.NEWS_COLLECTOR_DB_PATH || "scripts/news_collector/data/news_collector.db") : undefined;
    return hash(JSON.stringify(db ? [db.size, db.mtimeMs] : []) + (await Promise.all(files.sort().map(async file => `${file}:${hash(await readFile(file))}`))).join("\n"));
  } catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined; throw error; }
}

async function codeRevision(root: string) {
  const files: string[] = ["package.json", "package-lock.json", "cloudflare-pages.json", "Dockerfile.publisher"];
  async function walk(directory: string) {
    for (const entry of await readdir(path.join(root, directory), { withFileTypes: true })) {
      if (entry.name.startsWith(".") || ["data", "output", "__pycache__", "node_modules"].includes(entry.name) || entry.name.endsWith(".egg-info")) continue;
      const name = `${directory}/${entry.name}`;
      if (entry.isDirectory()) await walk(name);
      else if (/\.(py|tsx?|json|ya?ml|md|css|svg|lock|toml|ttf)$/.test(name)) files.push(name);
    }
  }
  await walk("scripts"); await walk("src"); await walk("public");
  return hash((await Promise.all(files.sort().map(async file => `${file}:${hash(await readFile(path.join(root, file)))}`))).join("\n") + (process.env.NEWS_EDITOR_MODEL || "default") + (process.env.NEWS_EDITOR_REASONING_EFFORT || "default"));
}
async function main() {
  const root = process.cwd();
  const noUpload = process.argv.includes("--no-upload");
  for (const file of [".env", ".env.newsletters"]) {
    try { loadEnvFile(path.join(root, file)); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
  }
  const config = JSON.parse(await readFile("cloudflare-pages.json", "utf8"));
  const profile = JSON.parse(await readFile("scripts/news_collector/config/editorial-profile.json", "utf8"));
  const today = () => dateInZone(new Date().toISOString(), profile.timezone);
  const date = today();
  const file = path.join(root, "data/publisher-state.json");
  const statusFile = path.join(root, "data/publisher-status.json");
  try {
    console.log(`Daily publisher: ${date} (${profile.timezone})`);
    const restored = await restorePublication(root, `https://${config.domain}`);
    if (restored.manifest.date > date) throw new Error("Production is ahead of this machine's date; check its clock.");
    const prior = await readJson<RunState>(file);
    if (restored.manifest.date === date) {
      // An upload can succeed even when its process loses the response. Finish browser
      // verification of our exact bundle before declaring that attempt successful.
      if (prior?.date === date && prior.active === "deploy" && prior.status !== "published") {
        const bundle = await readFile("data/cloudflare-bundle/edition-manifest.json");
        if (hash(bundle) !== restored.fingerprint) throw new Error("Another release is live; inspect the interrupted deployment before continuing.");
        script("scripts/deploy-cloudflare.ts", ["--skip-upload"], 15 * 60_000);
        prior.status = "published"; delete prior.active;
        await atomicJson(file, prior);
      }
      await atomicJson(statusFile, { date, status: "published", checkedAt: new Date().toISOString(), generatedAt: restored.manifest.generatedAt });
      console.log(`${date} is already published. No duplicate edition generated.`);
      return;
    }
    if (process.argv.includes("--check")) throw new Error(`Today's edition is missing (live: ${restored.manifest.date}).`);
    const revision = await codeRevision(root);
    const canResume = reusable(prior, date, revision, restored.fingerprint, new Date()) && prior?.artifacts && prior.artifacts === await checkpointArtifacts(prior);
    const state: RunState = canResume ? prior! : {
      date, revision, history: restored.fingerprint, startedAt: new Date().toISOString(), updatedAt: new Date().toISOString(), completed: [], status: "running",
    };
    const python = process.env.PYTHON_BIN || path.join(root, "scripts/news_collector/.venv/bin/python");
    const cwd = path.join(root, "scripts/news_collector");
    // Fail before spending time collecting if deployment/editor authentication is missing.
    if (!(process.env.CLOUDFLARE_API_TOKEN || process.env.CLOUFLARE_API_KEY) || !(process.env.CLOUDFLARE_ACCOUNT_ID || process.env.CLOUFLARE_ACCOUNT)) throw new Error("Cloudflare credentials are missing");
    if (process.env.NEWS_MAIL_ENABLED !== "1" || !process.env.NEWS_MAIL_USERNAME || !process.env.NEWS_MAIL_PASSWORD) throw new Error("Enable NEWS_MAIL_ENABLED=1 and configure the newsletter mailbox credentials");
    execFileSync(process.env.NEWS_EDITOR_CODEX_BIN || "codex", ["login", "status"], { stdio: publisherStdio(), timeout: 30_000 });
    await runStages(state, async (stage: Stage) => {
      console.log(`Starting ${stage}`);
      if (stage === "collect") {
        const output = execFileSync(python, ["-m", "news_collector.jobs.collect"], {
          cwd, stdio: publisherStdio("pipe"), encoding: "utf8", timeout: 20 * 60_000, maxBuffer: 10 * 1024 * 1024,
          // A fresh edition checks sources now, while respecting upstream cooldowns.
          env: { ...process.env, NEWS_COLLECTOR_CHECK_NOW: "1", NEWS_COLLECTOR_FORCE_RUN: "0" },
        });
        const collection = JSON.parse(output);
        if (!collection.sources?.some((source: { status: string; collected: number }) => ["ok", "partial"].includes(source.status) && source.collected > 0)) throw new Error("Collection produced no usable sources");
        await atomicJson(path.join(root, "data/collection-run.json"), collection);
        console.log(`Collection complete; ${collection.errors?.length || 0} source errors recorded in collection-run.json`);
      } else if (["editorial", "sports", "export"].includes(stage)) {
        execFileSync(python, ["-m", `news_collector.jobs.${stage === "export" ? "export_edition" : stage}`], {
          cwd, stdio: publisherStdio(), timeout: (stage === "editorial" ? 90 : stage === "sports" ? 30 : 2) * 60_000,
          env: { ...process.env, NEWS_EDITORIAL_RUN_KEY: hash(JSON.stringify([state.date, state.revision, state.history, state.startedAt])) },
        });
      } else if (stage === "build") script("scripts/build-static.tsx", [], 20 * 60_000);
      else {
        const edition = editionSchema.parse(await readJson(path.join(root, "data/edition.json")));
        validateBuildFreshness(edition);
        if (edition.date !== date) throw new Error("Generated edition does not match the run date");
        if (hash(await fetchPublic(`https://${config.domain}/edition-manifest.json`)) !== state.history) throw new Error("Production changed during this run; retry to refresh publication history");
        if (noUpload) {
          const secrets = Object.entries(process.env).filter(([key]) => /KEY|TOKEN|SECRET|PASSWORD/i.test(key)).flatMap(([, value]) => value ? [value] : []);
          const { bundle } = await prepareRelease(root, secrets);
          await verifyLocalRelease(root, bundle);
          console.log("Full rehearsal passed local release verification. Nothing was uploaded.");
        } else script("scripts/deploy-cloudflare.ts", [], 30 * 60_000);
      }
    }, async state => {
      state.artifacts = await checkpointArtifacts(state);
      await atomicJson(file, state);
      await atomicJson(statusFile, { date, status: state.status, stage: state.active, checkedAt: new Date().toISOString() });
    }, today, { noUpload });
  } catch (error) {
    // Detailed errors go to the private journal. Keep the health file credential-free.
    await atomicJson(statusFile, { date, status: "failed", checkedAt: new Date().toISOString(), detail: "See publisher journal and publisher-state.json" });
    throw error;
  }
}
function script(file: string, args: string[], timeout: number) {
  execFileSync(process.execPath, ["--import", "tsx", file, ...args], { stdio: publisherStdio(), timeout });
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
