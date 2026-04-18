import { getStartupCatchupState } from "@/lib/services/startup-catchup";

async function main() {
  const state = await getStartupCatchupState();
  console.log(
    JSON.stringify(
      {
        startupCatchup: state,
      },
      null,
      2,
    ),
  );

  if (!state.enabled || !state.needed) {
    return;
  }

  const token = process.env.INTERNAL_API_KEY ?? process.env.SYNC_API_KEY;
  if (!token) {
    throw new Error("INTERNAL_API_KEY or SYNC_API_KEY is required for startup catch-up.");
  }

  const endpoint = process.env.STARTUP_CATCHUP_URL ?? "http://127.0.0.1:3000/api/internal/jobs/daily-sync";
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  const text = await response.text();
  if (response.ok || response.status === 409) {
    console.log(text);
    return;
  }

  throw new Error(`Startup catch-up failed with ${response.status}: ${text}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
