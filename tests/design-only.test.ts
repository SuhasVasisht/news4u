import { expect, test } from "vitest";
import { assertUnchangedEdition } from "../scripts/lib/design-only";
import { editionSchema, validateBuildFreshness } from "../src/lib/edition";

const edition = editionSchema.parse({ date: "2026-09-08", generatedAt: "2026-09-08T12:00:00Z", timezone: "America/Los_Angeles", windowHours: 24, stories: [], sources: [] });
test("design-only accepts unchanged published data without weakening daily freshness", () => {
  expect(() => assertUnchangedEdition(edition, structuredClone(edition))).not.toThrow();
  expect(() => validateBuildFreshness(edition, new Date("2026-09-10T12:00:00Z"))).toThrow();
});
test("design-only rejects changed news, sources, and publication dates", () => {
  for (const update of [
    { date: "2026-09-10" },
    { generatedAt: "2026-09-10T12:00:00Z" },
    { windowHours: 48 },
    { sources: [{ name: "new", status: "ok", count: 0, latest: null, reason: null }] },
  ]) expect(() => assertUnchangedEdition({ ...edition, ...update }, edition)).toThrow("exactly match");
});
