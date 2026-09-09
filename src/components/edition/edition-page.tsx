import { NewsEdition } from "@/components/edition/news-edition";
import { getEdition } from "@/lib/services/edition-service";
import type { EditionView } from "@/lib/edition";

export async function EditionPage({ view, query, sector, story }: { view?: EditionView; query?: string; sector?: string; story?: string }) {
  return <NewsEdition edition={await getEdition()} initialView={view} initialQuery={query} initialSector={sector} initialStory={story} />;
}
