import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

export const stages = ["collect", "editorial", "sports", "export", "build", "deploy"] as const;
export type Stage = typeof stages[number];
export type RunState = {
  date: string; revision: string; history: string; startedAt: string; updatedAt: string;
  completed: Stage[]; status: "running" | "failed" | "published"; active?: Stage; artifacts?: string;
};
export async function atomicJson(file: string, value: unknown) {
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(`${file}.tmp`, JSON.stringify(value, null, 2), { mode: 0o600 });
  await rename(`${file}.tmp`, file);
}
export async function readJson<T>(file: string): Promise<T | undefined> {
  try { return JSON.parse(await readFile(file, "utf8")); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return; throw error; }
}
export function reusable(state: RunState | undefined, date: string, revision: string, history: string, now: Date) {
  return Boolean(state && state.date === date && state.revision === revision && state.history === history
    && now.getTime() - Date.parse(state.startedAt) >= 0 && now.getTime() - Date.parse(state.startedAt) < 6 * 3600_000);
}
// Small injectable state machine: a failed phase is never marked complete.
export async function runStages(state: RunState, run: (stage: Stage) => Promise<void>, save: (state: RunState) => Promise<void>, today: () => string) {
  for (const stage of stages) {
    if (today() !== state.date) throw new Error("Publication crossed midnight; retry with today's fresh collection.");
    if (state.completed.includes(stage)) continue;
    state.active = stage;
    state.status = "running";
    state.updatedAt = new Date().toISOString();
    await save(state);
    try { await run(stage); }
    catch (error) { state.status = "failed"; await save(state); throw error; }
    state.completed.push(stage);
    state.updatedAt = new Date().toISOString();
    await save(state);
  }
  state.status = "published";
  delete state.active;
  await save(state);
}
