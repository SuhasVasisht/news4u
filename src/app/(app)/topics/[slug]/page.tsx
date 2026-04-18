import { notFound } from "next/navigation";
import { ArticleList } from "@/components/article/article-list";
import { getShellData, searchStories } from "@/lib/services/news-service";

export const dynamic = "force-dynamic";

export default async function TopicPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const shellData = await getShellData();
  const topic = shellData.topics.find((item) => item.slug === slug);

  if (!topic) {
    notFound();
  }

  const page = await searchStories(topic.name);
  const items = page.items.filter((item) => item.topics.some((entry) => entry.slug === slug));

  return (
    <div className="space-y-6">
      <section className="surface rounded-[32px] px-6 py-8 md:px-8">
        <p className="text-xs uppercase tracking-[0.28em] text-muted">Topic feed</p>
        <h1 className="headline mt-3 text-4xl text-ink">{topic.name}</h1>
        <p className="mt-3 max-w-2xl text-base leading-7 text-muted">
          Topic lanes now roll up clustered stories instead of listing raw articles one by one.
        </p>
      </section>
      <ArticleList
        items={items}
        emptyTitle="No visible stories in this topic."
        emptyCopy="The topic may be muted, empty, or filtered by your current preferences."
      />
    </div>
  );
}
