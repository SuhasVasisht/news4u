import { SourceVisibilityList } from "@/components/settings/source-visibility-list";
import { TopicMutedList } from "@/components/settings/topic-muted-list";
import { getShellData } from "@/lib/services/news-service";

export const dynamic = "force-dynamic";

export default async function SourcesPage() {
  const shellData = await getShellData();

  return (
    <div className="space-y-6">
      <SourceVisibilityList items={shellData.sources} />
      <TopicMutedList items={shellData.topics} />
    </div>
  );
}
