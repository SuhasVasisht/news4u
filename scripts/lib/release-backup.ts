import { mkdir, stat } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

export async function backupRelease(root: string, phase: "before" | "published") {
  const bundle = path.join(root, "data/cloudflare-bundle");
  try { await stat(path.join(bundle, "edition-manifest.json")); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return; throw error; }
  const directory = path.resolve(process.env.NEWS_BACKUP_DIR || path.join(homedir(), "news4u-backups"));
  const relative = path.relative(root, directory);
  if (!relative || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative))) throw new Error("NEWS_BACKUP_DIR must be outside the project workspace");
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const file = path.join(directory, `${new Date().toISOString().replace(/[:.]/g, "-")}-${phase}.tar.gz`);
  execFileSync("tar", ["-czf", file, "-C", bundle, "."], { timeout: 120000 });
  console.log(`Release backup: ${file}`);
  return file;
}
