import { sampleSyncPayload } from "@/lib/mock-data";
import { syncArticles } from "@/lib/services/news-service";

async function main() {
  const result = await syncArticles(sampleSyncPayload);
  console.log(result);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
