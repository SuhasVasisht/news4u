import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { publicFile } from "./static-release";
import { verifyStaticSite } from "../verify-static-site";

export async function verifyLocalRelease(root: string, bundle: string) {
  const server = createServer(async (request, response) => {
    try {
      let name = decodeURIComponent(new URL(request.url || "/", "http://localhost").pathname).slice(1);
      if (!name || name.endsWith("/")) name += "index.html";
      if (!publicFile(name) || name === "_headers") { response.writeHead(404).end(); return; }
      const body = await readFile(path.join(bundle, name));
      const contentType = name.endsWith(".html") ? "text/html; charset=utf-8" : name.endsWith(".css") ? "text/css" : name.endsWith(".js") ? "text/javascript" : name.endsWith(".webp") ? "image/webp" : "application/json";
      response.writeHead(200, { "Content-Type": contentType }); response.end(body);
    } catch { response.writeHead(404).end(); }
  });
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  try {
    const address = server.address();
    if (!address || typeof address === "string") throw new Error("Local verifier failed to start");
    await verifyStaticSite(`http://127.0.0.1:${address.port}`, root);
  } finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }
}
