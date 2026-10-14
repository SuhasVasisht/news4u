import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

export const stages = ["collect", "editorial", "sports", "export", "build", "deploy"] as const;
export type Stage = typeof stages[number];
export type RunState = {
  date: string; revision: string; history: string; startedAt: string; updatedAt: string;
  completed: Stage[]; status: "running" | "failed" | "published" | "validated"; active?: Stage; artifacts?: string;
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
export async function runStages(state: RunState, run: (stage: Stage) => Promise<void>, save: (state: RunState) => Promise<void>, today: () => string, options: { noUpload?: boolean } = {}) {
  for (const stage of stages) {
    if (today() !== state.date) throw new Error("Publication crossed midnight; retry with today's fresh collection.");
    if (state.completed.includes(stage)) continue;
    state.active = stage;
    state.status = "running";
    state.updatedAt = new Date().toISOString();
    await save(state);
    const started = Date.now();
    console.log(JSON.stringify({ event: "stage_start", stage, date: state.date, at: new Date().toISOString() }));
    try { await run(stage); }
    catch (error) {
      console.error(JSON.stringify({ event: "stage_failed", stage, date: state.date, elapsedMs: Date.now() - started,
        error: error instanceof Error ? error.message : String(error), at: new Date().toISOString() }));
      state.status = "failed"; await save(state); throw error;
    }
    console.log(JSON.stringify({ event: "stage_complete", stage, date: state.date, elapsedMs: Date.now() - started,
      at: new Date().toISOString(), ...(stage === "deploy" && options.noUpload ? { noUpload: true } : {}) }));
    if (stage === "deploy" && options.noUpload) {
      state.status = "validated";
      delete state.active;
      state.updatedAt = new Date().toISOString();
      await save(state);
      return;
    }
    state.completed.push(stage);
    state.updatedAt = new Date().toISOString();
    await save(state);
  }
  state.status = "published";
  delete state.active;
  await save(state);
}

// Match the sixteen 07:05..22:05 recovery slots instead of abandoning the day
// after three transient failures. The cooldown still prevents rapid model loops.
export const dailyAttemptLimit = 16;
export const retryCooldownMs = 55 * 60_000;
export type AttemptBudget = { date: string; revision: string; attempts: number; lastStartedAt: string };
export function reserveAttempt(prior: AttemptBudget | undefined, date: string, revision: string, now: Date): AttemptBudget {
  const current = prior?.date === date && prior.revision === revision ? prior : undefined;
  if (current && current.attempts >= dailyAttemptLimit) throw new Error(`Daily attempt budget exhausted (${dailyAttemptLimit} attempts). Inspect the journal; retry requires a code/configuration change or --retry-editor.`);
  if (current && now.getTime() - Date.parse(current.lastStartedAt) < retryCooldownMs) throw new Error("Publisher retry cooling down for 55 minutes after the previous start.");
  return { date, revision, attempts: (current?.attempts || 0) + 1, lastStartedAt: now.toISOString() };
}
