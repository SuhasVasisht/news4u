import { NextResponse } from "next/server";
import { DailySyncJobError, runDailySyncJob } from "@/lib/services/daily-sync";

type DailySyncRouteState = {
  running: boolean;
  startedAt: string | null;
};

declare global {
  // eslint-disable-next-line no-var
  var __dailySyncRouteState__: DailySyncRouteState | undefined;
}

function routeState(): DailySyncRouteState {
  if (!globalThis.__dailySyncRouteState__) {
    globalThis.__dailySyncRouteState__ = {
      running: false,
      startedAt: null,
    };
  }

  return globalThis.__dailySyncRouteState__;
}

function isAuthorized(request: Request) {
  const authHeader = request.headers.get("authorization");
  const expected = process.env.INTERNAL_API_KEY ?? process.env.SYNC_API_KEY;
  return Boolean(expected && authHeader === `Bearer ${expected}`);
}

export async function POST(request: Request) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const state = routeState();
  if (state.running) {
    return NextResponse.json(
      {
        error: "Daily sync already running",
        startedAt: state.startedAt,
      },
      { status: 409 },
    );
  }

  state.running = true;
  state.startedAt = new Date().toISOString();

  try {
    return NextResponse.json(await runDailySyncJob());
  } catch (error) {
    if (error instanceof DailySyncJobError) {
      return NextResponse.json(error.result, { status: 500 });
    }

    return NextResponse.json({ error: "Daily sync failed" }, { status: 500 });
  } finally {
    state.running = false;
    state.startedAt = null;
  }
}
