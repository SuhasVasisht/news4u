import { expect, it, vi } from "vitest";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { backupRelease } from "../scripts/lib/release-backup";

it("backs up public artifacts outside the repo and rejects an in-repo backup directory", async () => {
  const temporary = await mkdtemp(path.join(tmpdir(), "news-backup-test-"));
  const root = path.join(temporary, "workspace");
  try {
    await mkdir(path.join(root, "data/cloudflare-bundle"), { recursive: true });
    await writeFile(path.join(root, "data/cloudflare-bundle/edition-manifest.json"), "{}");
    await writeFile(path.join(root, "data/cloudflare-bundle/index.html"), "Reviewed paper");
    await writeFile(path.join(root, ".env"), "PRIVATE=value");
    vi.stubEnv("NEWS_BACKUP_DIR", path.join(temporary, "backups"));
    const backup = await backupRelease(root, "published");
    const contents = execFileSync("tar", ["-tzf", backup!], { encoding: "utf8" });
    expect(contents).toContain("index.html");
    expect(contents).not.toContain(".env");
    vi.stubEnv("NEWS_BACKUP_DIR", path.join(root, "backups"));
    await expect(backupRelease(root, "before")).rejects.toThrow("outside");
  } finally { vi.unstubAllEnvs(); await rm(temporary, { recursive: true, force: true }); }
});
