// No credentials, network calls, or publication. Run inside the built Linux image.
import { execFileSync } from "node:child_process";
import { chromium } from "@playwright/test";

execFileSync("codex", ["--version"], { stdio: "inherit" });
execFileSync("scripts/news_collector/.venv/bin/python", ["-c", "from news_collector.settings import get_settings; from playwright.sync_api import sync_playwright; assert str(get_settings().project_root) == '/app/scripts/news_collector'; p=sync_playwright().start(); b=p.chromium.launch(); b.close(); p.stop()"], { stdio: "inherit" });
async function main() {
  const browser = await chromium.launch();
  await browser.close();
  console.log("Publisher runtime and both browser installations are ready.");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
