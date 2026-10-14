import { describe, it, expect } from "vitest";
import { reusable, runStages, reserveAttempt, dailyAttemptLimit, type RunState, type Stage } from "../scripts/lib/daily-publisher";

const state = (): RunState => ({ date: "2026-10-04", revision: "code", history: "history", startedAt: "2026-10-04T14:00:00Z", updatedAt: "2026-10-04T14:00:00Z", completed: [], status: "running" });
describe("daily publishing recovery", () => {
  it("marks a rehearsal validated, but still runs deployment on a later publish", async () => {
    const run = state();
    const calls: Stage[] = [];
    await runStages(run, async stage => { calls.push(stage); }, async () => {}, () => run.date, { noUpload: true });
    expect(run.status).toBe("validated");
    expect(run.completed).not.toContain("deploy");
    calls.length = 0;
    await runStages(run, async stage => { calls.push(stage); }, async () => {}, () => run.date);
    expect(calls).toEqual(["deploy"]);
    expect(run.status).toBe("published");
  });
  it("resumes only current, unchanged, bounded checkpoints", () => {
    const now = new Date("2026-10-04T15:00:00Z");
    expect(reusable(state(), "2026-10-04", "code", "history", now)).toBe(true);
    expect(reusable(state(), "2026-10-05", "code", "history", now)).toBe(false);
    expect(reusable(state(), "2026-10-04", "new-code", "history", now)).toBe(false);
    expect(reusable(state(), "2026-10-04", "code", "new-history", now)).toBe(false);
    expect(reusable(state(), "2026-10-04", "code", "history", new Date("2026-10-04T20:00:00Z"))).toBe(false);
    expect(reusable(state(), "2026-10-04", "code", "history", new Date("2026-10-04T13:00:00Z"))).toBe(false);
  });
  it("blocks deployment on a failed audit, then resumes without recollecting", async () => {
    const run = state();
    const calls: Stage[] = [];
    const persisted: RunState[] = [];
    const save = async (value: RunState) => { persisted.push(structuredClone(value)); };
    await expect(runStages(run, async stage => { calls.push(stage); if (stage === "editorial") throw new Error("Audit blocked"); }, save, () => run.date)).rejects.toThrow("Audit blocked");
    expect(calls).toEqual(["collect", "editorial"]);
    expect(persisted.at(-1)).toMatchObject({ status: "failed", completed: ["collect"], active: "editorial" });
    calls.length = 0;
    await runStages(run, async stage => { calls.push(stage); }, save, () => run.date);
    expect(calls).toEqual(["editorial", "sports", "export", "build", "deploy"]);
    expect(run.status).toBe("published");
    calls.length = 0;
    await runStages(run, async stage => { calls.push(stage); }, save, () => run.date);
    expect(calls).toEqual([]);
  });
  it("does not upload an edition after crossing midnight", async () => {
    const run = state();
    run.completed = ["collect", "editorial", "sports", "export", "build"];
    const calls: Stage[] = [];
    await expect(runStages(run, async stage => { calls.push(stage); }, async () => {}, () => "2026-10-05")).rejects.toThrow("midnight");
    expect(calls).toEqual([]);
  });
});


it("bounds daily retries independently of checkpoint restarts and resets on the next date", () => {
  const first = reserveAttempt(undefined, "2026-10-06", "revision", new Date("2026-10-06T14:00:00Z"));
  expect(() => reserveAttempt(first, first.date, first.revision, new Date("2026-10-06T14:30:00Z"))).toThrow("cooling down");
  const second = reserveAttempt(first, first.date, first.revision, new Date("2026-10-06T15:00:00Z"));
  let last = second;
  for (let i = 2; i < dailyAttemptLimit; i++) last = reserveAttempt(last, first.date, first.revision, new Date(Date.parse(first.lastStartedAt) + i * 3600_000));
  expect(() => reserveAttempt(last, first.date, first.revision, new Date(Date.parse(last.lastStartedAt) + 3600_000))).toThrow("budget exhausted");
  expect(reserveAttempt(last, "2026-10-07", first.revision, new Date("2026-10-07T14:00:00Z")).attempts).toBe(1);
  expect(reserveAttempt(last, first.date, "fixed-revision", new Date("2026-10-06T17:00:00Z")).attempts).toBe(1);
});

it("accepts real hourly timer jitter and allows afternoon recovery after morning failures", () => {
  let budget = reserveAttempt(undefined, "2026-10-13", "code", new Date("2026-10-13T14:05:23.604Z"));
  budget = reserveAttempt(budget, budget.date, budget.revision, new Date("2026-10-13T15:05:23.400Z"));
  expect(budget.attempts).toBe(2);
  for (let hour = 16; hour <= 23; hour++) budget = reserveAttempt(budget, budget.date, budget.revision, new Date(`2026-10-13T${hour}:05:24Z`));
  expect(budget.attempts).toBe(10);
});
