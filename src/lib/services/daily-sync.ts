import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const COLLECTOR_CWD = path.join(process.cwd(), "scripts", "news_collector");

const PYTHON_MODULES = {
  collect: "news_collector.jobs.collect",
  digest: "news_collector.jobs.digest",
  publish: "news_collector.jobs.publish",
} as const;

type PythonJobName = keyof typeof PYTHON_MODULES;

type StepStatus = "ok" | "failed";

export type DailySyncCommandStep = {
  name: string;
  status: StepStatus;
  command: string;
  startedAt: string;
  finishedAt: string;
  durationMs: number;
  stdout: string;
  stderr: string;
  json: Record<string, unknown> | null;
};

export type DailySyncAppStep = {
  name: string;
  status: StepStatus;
  startedAt: string;
  finishedAt: string;
  durationMs: number;
  result: unknown;
};

export type OptionalCollectorSkip = {
  collector: string;
  status: string;
  reason: string | null;
};

export type DailySyncJobResult = {
  status: "ok" | "failed";
  startedAt: string;
  finishedAt: string;
  durationMs: number;
  steps: {
    collect?: DailySyncCommandStep;
    digest?: DailySyncCommandStep;
    publish?: DailySyncCommandStep;
    cleanup?: DailySyncAppStep;
    feedRefresh?: DailySyncAppStep;
  };
  optionalCollectorSkips: OptionalCollectorSkip[];
};

type DailySyncDeps = {
  runPythonJob: (name: PythonJobName) => Promise<DailySyncCommandStep>;
  cleanupFeed: () => Promise<unknown>;
  refreshFeed: () => Promise<unknown>;
  now: () => Date;
};

function resolvePythonBin() {
  return process.env.PYTHON_BIN || "python3";
}

export class DailySyncJobError extends Error {
  constructor(public readonly result: DailySyncJobResult, message = "Daily sync job failed") {
    super(message);
  }
}

function formatCommand(name: PythonJobName) {
  return `${resolvePythonBin()} -m ${PYTHON_MODULES[name]}`;
}

function tryParseJson(stdout: string) {
  const trimmed = stdout.trim();
  if (!trimmed) {
    return null;
  }

  try {
    return JSON.parse(trimmed) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function extractOptionalCollectorSkips(step?: DailySyncCommandStep): OptionalCollectorSkip[] {
  const sources = step?.json?.sources;
  if (!Array.isArray(sources)) {
    return [];
  }

  return sources
    .filter(
      (source): source is Record<string, unknown> =>
        typeof source === "object" &&
        source !== null &&
        typeof source.collector === "string" &&
        typeof source.status === "string" &&
        ("reason" in source ? source.reason === null || typeof source.reason === "string" : true),
    )
    .filter((source) => /missing persistent/i.test(String(source.reason ?? "")))
    .map((source) => ({
      collector: String(source.collector),
      status: String(source.status),
      reason: source.reason === null ? null : String(source.reason ?? ""),
    }));
}

async function runPythonJob(name: PythonJobName): Promise<DailySyncCommandStep> {
  const startedAt = new Date();
  const pythonBin = resolvePythonBin();
  const command = formatCommand(name);

  try {
    const { stdout, stderr } = await execFileAsync(pythonBin, ["-m", PYTHON_MODULES[name]], {
      cwd: COLLECTOR_CWD,
      env: process.env,
    });
    const finishedAt = new Date();
    return {
      name,
      status: "ok",
      command,
      startedAt: startedAt.toISOString(),
      finishedAt: finishedAt.toISOString(),
      durationMs: finishedAt.getTime() - startedAt.getTime(),
      stdout,
      stderr,
      json: tryParseJson(stdout),
    };
  } catch (error) {
    const finishedAt = new Date();
    const failed = error as { stdout?: string; stderr?: string };
    return {
      name,
      status: "failed",
      command,
      startedAt: startedAt.toISOString(),
      finishedAt: finishedAt.toISOString(),
      durationMs: finishedAt.getTime() - startedAt.getTime(),
      stdout: failed.stdout ?? "",
      stderr: failed.stderr ?? "",
      json: tryParseJson(failed.stdout ?? ""),
    };
  }
}

async function runAppStep(name: DailySyncAppStep["name"], action: () => Promise<unknown>): Promise<DailySyncAppStep> {
  const startedAt = new Date();
  const result = await action();
  const finishedAt = new Date();
  return {
    name,
    status: "ok",
    startedAt: startedAt.toISOString(),
    finishedAt: finishedAt.toISOString(),
    durationMs: finishedAt.getTime() - startedAt.getTime(),
    result,
  };
}

const defaultDeps: DailySyncDeps = {
  runPythonJob,
  cleanupFeed: async () => {
    const { cleanupAgedStories } = await import("@/lib/services/news-service");
    return cleanupAgedStories();
  },
  refreshFeed: async () => {
    const { generateDailyFeed } = await import("@/lib/services/news-service");
    return generateDailyFeed({ forceRefresh: true });
  },
  now: () => new Date(),
};

export async function runDailySyncJob(deps: DailySyncDeps = defaultDeps): Promise<DailySyncJobResult> {
  const startedAt = deps.now();
  const steps: DailySyncJobResult["steps"] = {};

  const collect = await deps.runPythonJob("collect");
  steps.collect = collect;
  const optionalCollectorSkips = extractOptionalCollectorSkips(collect);
  if (collect.status === "failed") {
    throw new DailySyncJobError({
      status: "failed",
      startedAt: startedAt.toISOString(),
      finishedAt: deps.now().toISOString(),
      durationMs: deps.now().getTime() - startedAt.getTime(),
      steps,
      optionalCollectorSkips,
    });
  }

  const digest = await deps.runPythonJob("digest");
  steps.digest = digest;
  if (digest.status === "failed") {
    throw new DailySyncJobError({
      status: "failed",
      startedAt: startedAt.toISOString(),
      finishedAt: deps.now().toISOString(),
      durationMs: deps.now().getTime() - startedAt.getTime(),
      steps,
      optionalCollectorSkips,
    });
  }

  const publish = await deps.runPythonJob("publish");
  steps.publish = publish;
  if (publish.status === "failed") {
    throw new DailySyncJobError({
      status: "failed",
      startedAt: startedAt.toISOString(),
      finishedAt: deps.now().toISOString(),
      durationMs: deps.now().getTime() - startedAt.getTime(),
      steps,
      optionalCollectorSkips,
    });
  }

  steps.cleanup = await runAppStep("cleanup", deps.cleanupFeed);
  steps.feedRefresh = await runAppStep("feedRefresh", deps.refreshFeed);

  const finishedAt = deps.now();
  return {
    status: "ok",
    startedAt: startedAt.toISOString(),
    finishedAt: finishedAt.toISOString(),
    durationMs: finishedAt.getTime() - startedAt.getTime(),
    steps,
    optionalCollectorSkips,
  };
}
