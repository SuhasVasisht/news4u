import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { expect, it } from "vitest";
import { atomicJson, readJson, reserveAttempt, reusable, runStages, dailyAttemptLimit, type AttemptBudget, type RunState, type Stage } from "../scripts/lib/daily-publisher";

// Exercise durable scheduler boundaries without uploading or calling a model.
it.each([3, dailyAttemptLimit])("preserves the live paper through %i genuine coverage failures and recovers from disk", async failures => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "coverage-publisher-"));
  const checkpoint = path.join(directory, "state.json");
  const attempts = path.join(directory, "attempts.json");
  let live = "2026-10-13";
  const calls: Stage[] = [];
  const start = Date.parse("2026-10-14T14:05:00Z");
  try {
    for (let slot = 0; slot <= failures; slot++) {
      const nextDay = slot === dailyAttemptLimit;
      const date = nextDay ? "2026-10-15" : "2026-10-14";
      const now = new Date(start + slot * 3600_000 + (nextDay ? 8 * 3600_000 : 0));
      const budget = reserveAttempt(await readJson<AttemptBudget>(attempts), date, "code", now);
      await atomicJson(attempts, budget);
      if (nextDay) expect(budget.attempts).toBe(1);
      const prior = await readJson<RunState>(checkpoint);
      const run = reusable(prior, date, "code", live, now) ? prior! : {
        date, revision: "code", history: live, startedAt: now.toISOString(),
        updatedAt: now.toISOString(), completed: [], status: "running",
      } satisfies RunState;
      const publish = runStages(run, async stage => {
        calls.push(stage);
        if (stage === "editorial" && slot < failures) throw new Error("Must-cover event unresolved: verified new development missing");
        if (stage === "deploy") live = date;
      }, value => atomicJson(checkpoint, value), () => date);
      if (slot < failures) {
        await expect(publish).rejects.toThrow("Must-cover event unresolved");
        expect(live).toBe("2026-10-13");
        const saved = await readJson<RunState>(checkpoint);
        expect(saved).toMatchObject({ status: "failed", active: "editorial", completed: ["collect"] });
        expect(calls).not.toContain("deploy");
      } else {
        await publish;
        expect(live).toBe(date);
        expect((await readJson<RunState>(checkpoint))?.status).toBe("published");
        expect(calls.filter(stage => stage === "deploy")).toHaveLength(1);
        // No recollection during the short same-day coverage recovery window.
        if (!nextDay) expect(calls.filter(stage => stage === "collect")).toHaveLength(1);
      }
    }
  } finally { await rm(directory, { recursive: true, force: true }); }
});
