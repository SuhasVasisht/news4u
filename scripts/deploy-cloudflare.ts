import { publisherStdio } from "./lib/publisher-stdio";
import { loadEnvFile } from "node:process";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { prepareRelease, retainPublishedRelease } from "./lib/static-release";
import { verifyStaticSite } from "./verify-static-site";
import { backupRelease } from "./lib/release-backup";
import { verifyLocalRelease } from "./lib/verify-local-release";

async function main() {
  const root = process.cwd();
  const revisionIndex = process.argv.indexOf("--revise-edition");
  const editionDate = revisionIndex >= 0 ? process.argv[revisionIndex + 1] : undefined;
  if (revisionIndex >= 0 && (!editionDate || editionDate.startsWith("--") || process.argv.includes("--design-only"))) throw new Error("--revise-edition requires an explicit date and cannot be design-only");
  try { loadEnvFile(path.join(root, ".env")); } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
  const token = process.env.CLOUDFLARE_API_TOKEN || process.env.CLOUFLARE_API_KEY;
  const account = process.env.CLOUDFLARE_ACCOUNT_ID || process.env.CLOUFLARE_ACCOUNT;
  if (!token || !account) throw new Error("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are required (existing CLOUFLARE aliases also work)");
  const config = JSON.parse(await readFile(path.join(root, "cloudflare-pages.json"), "utf8")) as { project: string; domain: string; zone: string; productionBranch: string };
  if (!/^[a-z0-9-]+$/.test(config.project) || !config.domain.endsWith(`.${config.zone}`)) throw new Error("Invalid Cloudflare project/domain configuration");
  await mkdir(path.join(root, "data"), { recursive: true });
  {
    async function api<T>(route: string, method = "GET", body?: unknown): Promise<T> {
      const response = await fetch(`https://api.cloudflare.com/client/v4${route}`, {
        method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(30000),
      });
      const result = await response.json() as { success: boolean; result: T; errors: { message: string }[] };
      if (!response.ok || !result.success) throw new Error(`Cloudflare ${method} ${route}: HTTP ${response.status}: ${result.errors.map(error => error.message).join("; ")}`);
      return result.result;
    }
    const projectsPath = `/accounts/${account}/pages/projects`;
    const projects = await api<{ name: string; subdomain: string; production_branch: string }[]>(projectsPath);
    let project = projects.find(project => project.name === config.project);
    if (!project) project = await api(projectsPath, "POST", { name: config.project, production_branch: config.productionBranch });
    if (!project || project.production_branch !== config.productionBranch) throw new Error("Unexpected production branch; refusing to deploy to a different environment");
    const secrets = Object.entries(process.env).filter(([key]) => /KEY|TOKEN|SECRET|PASSWORD/i.test(key)).flatMap(([, value]) => value ? [value] : []);
    if (!process.argv.includes("--skip-upload")) await backupRelease(root, "before");
    // Domain-only retries verify the already uploaded release, even after its publication day.
    const { bundle, manifest } = process.argv.includes("--skip-upload")
      ? { bundle: path.join(root, "data/cloudflare-bundle"), manifest: JSON.parse(await readFile(path.join(root, "data/cloudflare-bundle/edition-manifest.json"), "utf8")) as { date: string; generatedAt: string; stories: number } }
      : await prepareRelease(root, secrets, { reviseToday: process.argv.includes("--revise-today") || Boolean(editionDate), designOnly: process.argv.includes("--design-only"), editionDate });
    if (!process.argv.includes("--skip-upload")) {
      await verifyLocalRelease(root, bundle);
      console.log(`Deploying ${manifest.stories} stories for ${manifest.date} to ${config.project}`);
      execFileSync(process.execPath, [path.join(root, "node_modules/wrangler/bin/wrangler.js"), "pages", "deploy", bundle,
        "--project-name", config.project, "--branch", config.productionBranch, "--commit-dirty=true"], {
        cwd: bundle, stdio: publisherStdio(), timeout: 600000,
        env: { NODE_ENV: "production", PATH: process.env.PATH, HOME: process.env.HOME, TMPDIR: process.env.TMPDIR,
          CLOUDFLARE_API_TOKEN: token, CLOUDFLARE_ACCOUNT_ID: account, CLOUDFLARE_SEND_METRICS: "false", CI: "true" },
      });
    }
    const pagesUrl = `https://${project.subdomain}`;
    // Wait for the new Pages deployment to be served before touching DNS.
    let verified = false;
    for (let attempt = 0; attempt < 12; attempt++) {
      try { await verifyStaticSite(pagesUrl, root); verified = true; break; }
      catch (error) { console.log(`Pages verification attempt ${attempt + 1}: ${(error as Error).message}`); if (attempt < 11) await new Promise(resolve => setTimeout(resolve, 10000)); }
    }
    if (!verified) throw new Error("Pages verification failed; DNS was not changed");
    if (process.argv.includes("--connect-domain")) {
      const zones = await api<{ id: string; name: string }[]>(`/zones?name=${encodeURIComponent(config.zone)}`);
      if (zones.length !== 1) throw new Error("Expected exactly one matching DNS zone");
      const dnsPath = `/zones/${zones[0].id}/dns_records`;
      const records = await api<{ id: string; type: string; name: string; content: string; proxied: boolean; ttl: number }[]>(`${dnsPath}?name=${encodeURIComponent(config.domain)}`);
      if (records.length > 1 || records.some(record => record.type !== "CNAME" || (record.content !== project.subdomain && !record.content.endsWith(".cfargotunnel.com")))) throw new Error("Unexpected DNS target; refusing to replace unrelated records");
      const domainsPath = `${projectsPath}/${config.project}/domains`;
      const domains = await api<{ name: string }[]>(domainsPath);
      if (!domains.some(domain => domain.name === config.domain)) await api(domainsPath, "POST", { name: config.domain });
      const record = records[0];
      if (!record || record.content !== project.subdomain) {
        await writeFile(path.join(root, `data/cloudflare-dns-before-${Date.now()}.json`), JSON.stringify({ zoneId: zones[0].id, records }, null, 2), { mode: 0o600 });
        await api(record ? `${dnsPath}/${record.id}` : dnsPath, record ? "PATCH" : "POST", { type: "CNAME", name: config.domain, content: project.subdomain, proxied: true, ttl: 1 });
        console.log(`Disconnected ${config.domain} from the tunnel; CNAME now points to ${project.subdomain}`);
      }
    }
    if (!process.argv.includes("--pages-only")) {
      let domainVerified = false;
      for (let attempt = 0; attempt < 20; attempt++) {
        try { await verifyStaticSite(`https://${config.domain}`, root); domainVerified = true; break; }
        catch (error) { console.log(`Custom-domain verification attempt ${attempt + 1}: ${(error as Error).message}`); if (attempt < 19) await new Promise(resolve => setTimeout(resolve, 15000)); }
      }
      if (!domainVerified) throw new Error("Custom domain is not verified. Check DNS and Pages certificate status before calling this deployment complete.");
    }
    await writeFile(path.join(root, "data/cloudflare-deployment.json"), JSON.stringify({ project: config.project, pagesUrl, domain: config.domain, date: manifest.date, generatedAt: manifest.generatedAt, deployedAt: new Date().toISOString(), domainVerified: !process.argv.includes("--pages-only") }, null, 2));
    await retainPublishedRelease(root);
    await backupRelease(root, "published");
    console.log(process.argv.includes("--pages-only") ? `Pages verified: ${pagesUrl}. Custom domain still pending.` : `Deployment verified: https://${config.domain}`);
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
