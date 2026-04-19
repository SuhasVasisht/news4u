import { DailySyncJobError, runDailySyncJob } from "@/lib/services/daily-sync";
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

  try {
    const result = await runDailySyncJob();
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    if (error instanceof DailySyncJobError) {
      console.error(JSON.stringify(error.result, null, 2));
      throw error;
    }
    throw error;
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
