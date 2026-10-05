import { mkdir, mkdtemp, readFile, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import { hash, publicFile } from "./static-release";
import { embeddedEdition } from "./edition-archive";

export const headersFile = "/*\n  Cache-Control: public, max-age=0, must-revalidate\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: no-referrer\n  X-Frame-Options: DENY\n";
export const manifestSchema = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/), generatedAt: z.string().datetime({ offset: true }),
  stories: z.number().int().positive(), files: z.record(z.string(), z.string().regex(/^[a-f0-9]{64}$/)),
}).passthrough();
export async function fetchPublic(url: string) {
  const origin = new URL(url).origin;
  for (let attempt = 0; attempt < 5; attempt++) {
    const response = await fetch(url, { cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(60_000) });
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const location = response.headers.get("location");
      await response.body?.cancel();
      if (!location) throw new Error("Archive redirect has no location");
      const next = new URL(location, url);
      if (next.origin !== origin) throw new Error("Archive redirect left the publication origin");
      url = next.href;
      continue;
    }
    if (!response.ok) throw new Error(`Public archive download failed: ${url} (${response.status})`);
    const body = Buffer.from(await response.arrayBuffer());
    if (body.length > 25 * 1024 * 1024) throw new Error("Public archive file exceeds size limit");
    return body;
  }
  throw new Error("Too many public archive redirects");
}
// Restore only public, hash-verified files. Private DB/mail/auth never belong in Git.
export async function restorePublication(root: string, base: string, fetchFile = fetchPublic) {
  const raw = await fetchFile(new URL("/edition-manifest.json", base).href);
  const manifest = manifestSchema.parse(JSON.parse(raw.toString()));
  const names = Object.keys(manifest.files);
  if (!names.length || names.length >= 20000 || names.some(name => !publicFile(name) || name === "edition-manifest.json")) throw new Error("Unsafe publication manifest");
  for (const required of ["index.html", "editions/index.html", `editions/${manifest.date}/edition.json`]) {
    if (!manifest.files[required]) throw new Error(`Publication manifest is missing ${required}`);
  }
  const destination = path.join(root, "data/cloudflare-published");
  await mkdir(path.dirname(destination), { recursive: true });
  const stage = await mkdtemp(`${destination}-restore-`);
  try {
    let cursor = 0;
    const downloads = await Promise.allSettled(Array.from({ length: 6 }, async () => {
      while (cursor < names.length) {
        const name = names[cursor++];
        let body: Buffer | undefined;
        try { body = await readFile(path.join(destination, name)); }
        catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
        if (!body || hash(body) !== manifest.files[name]) {
          // Cloudflare consumes _headers instead of serving it. Reconstruct and verify it.
          body = name === "_headers" ? Buffer.from(headersFile) : await fetchFile(new URL(`/${name}`, base).href);
        }
        if (hash(body) !== manifest.files[name]) throw new Error(`Archive hash mismatch: ${name}`);
        await mkdir(path.dirname(path.join(stage, name)), { recursive: true });
        await writeFile(path.join(stage, name), body);
      }
    }));
    for (const result of downloads) if (result.status === "rejected") throw result.reason;
    const edition = embeddedEdition(await readFile(path.join(stage, "index.html"), "utf8"));
    if (edition.date !== manifest.date || edition.generatedAt !== manifest.generatedAt || edition.stories.length !== manifest.stories) throw new Error("Live edition disagrees with manifest");
    // Detect another publisher changing production while recovery is in flight.
    if (hash(await fetchFile(new URL("/edition-manifest.json", base).href)) !== hash(raw)) throw new Error("Live publication changed during recovery; retry");
    await writeFile(path.join(stage, "edition-manifest.json"), raw);
    const previous = `${destination}.previous`;
    await rm(previous, { recursive: true, force: true });
    try { await rename(destination, previous); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
    await rename(stage, destination);
    return { manifest, fingerprint: hash(raw) };
  } finally { await rm(stage, { recursive: true, force: true }); }
}
