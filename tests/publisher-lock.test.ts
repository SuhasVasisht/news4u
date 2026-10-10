import { it, expect } from "vitest";
import { spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, mkdir, copyFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

it("blocks concurrent publishing and releases an OS lock after a killed child", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "news-lock-"));
  await mkdir(path.join(root, "scripts"));
  const wrapper = path.join(root, "scripts/with-publisher-lock.py");
  await copyFile("scripts/with-publisher-lock.py", wrapper);
  await mkdir(path.join(root, "scripts/lib"));
  await copyFile("scripts/lib/publisher_logging.py", path.join(root, "scripts/lib/publisher_logging.py"));
  const holder = spawn("python3", [wrapper, "python3", "-c", "import os,time; print(os.getpid(), flush=True); time.sleep(30)"], { stdio: ["ignore", "pipe", "pipe"] });
  try {
    const pids: number[] = [];
    await new Promise<void>((resolve, reject) => {
      holder.once("error", reject);
      let output = "";
      holder.stdout!.on("data", data => {
        output += data.toString();
        const lines = output.split("\n").filter(line => /^\d+$/.test(line));
        if (lines.length) { pids.push(Number(lines[0])); resolve(); }
      });
    });
    const child = pids[0];
    const blocked = spawnSync("python3", [wrapper, "python3", "-c", "print('unexpected')"], { encoding: "utf8" });
    expect(blocked.status).not.toBe(0);
    expect(blocked.stdout + blocked.stderr).toContain("Another publisher");
    const exited = once(holder, "exit");
    process.kill(child, "SIGKILL");
    await exited;
    const recovered = spawnSync("python3", [wrapper, "python3", "-c", "print('recovered')"], { encoding: "utf8" });
    expect(recovered.status).toBe(0);
    expect(recovered.stdout).toContain("recovered");
  } finally { holder.kill(); await rm(root, { recursive: true, force: true }); }
}, 10_000);

it("retains the lock in a running stage when its Node supervisor crashes", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "news-orphan-lock-"));
  await mkdir(path.join(root, "scripts"));
  const wrapper = path.join(root, "scripts/with-publisher-lock.py");
  await copyFile("scripts/with-publisher-lock.py", wrapper);
  await mkdir(path.join(root, "scripts/lib"));
  await copyFile("scripts/lib/publisher_logging.py", path.join(root, "scripts/lib/publisher_logging.py"));
  const helper = path.resolve("scripts/lib/publisher-stdio.ts");
  const code = `const {publisherStdio}=require(${JSON.stringify(helper)}); console.log(process.pid); require('node:child_process').execFileSync('python3', ['-c', 'import os,time; print(os.getpid(), flush=True); time.sleep(30)'], {stdio:publisherStdio()});`;
  const holder = spawn("python3", [wrapper, process.execPath, "--import", "tsx", "-e", code], { stdio: ["ignore", "pipe", "pipe"] });
  let child = 0;
  try {
    let output = "";
    await new Promise<void>((resolve, reject) => {
      holder.once("error", reject);
      holder.stdout!.on("data", data => { output += data.toString(); if (output.split("\n").filter(line => /^\d+$/.test(line)).length >= 2) resolve(); });
    });
    const [supervisor, stage] = output.split("\n").filter(line => /^\d+$/.test(line)).map(Number);
    child = stage;
    const exited = once(holder, "exit");
    process.kill(supervisor, "SIGKILL");
    await exited;
    const blocked = spawnSync("python3", [wrapper, "python3", "-c", "print('unexpected')"], { encoding: "utf8" });
    expect(blocked.status).not.toBe(0);
    expect(blocked.stdout + blocked.stderr).toContain("Another publisher");
  } finally {
    if (child) process.kill(child, "SIGKILL");
    holder.kill();
    await rm(root, { recursive: true, force: true });
  }
}, 10_000);
