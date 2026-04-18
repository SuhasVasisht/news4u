import { DailySyncJobError, runDailySyncJob } from "@/lib/services/daily-sync";

async function main() {
  try {
    const result = await runDailySyncJob();
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    if (error instanceof DailySyncJobError) {
      console.error(JSON.stringify(error.result, null, 2));
    } else {
      console.error(error);
    }
    process.exit(1);
  }
}

main();
