import { ArticleList } from "@/components/article/article-list";
import { getSavedFeed } from "@/lib/services/news-service";

export const dynamic = "force-dynamic";

export default async function SavedPage() {
  const page = await getSavedFeed();

  return (
    <div className="space-y-6">
      <section className="surface rounded-[32px] px-6 py-8 md:px-8">
        <p className="text-xs uppercase tracking-[0.28em] text-muted">Saved</p>
        <h1 className="headline mt-3 text-4xl text-ink">Stories held outside the daily queue.</h1>
        <p className="mt-3 max-w-2xl text-base leading-7 text-muted">
          Saved stories never age out automatically. When signed out, this tab stays empty by design.
        </p>
      </section>

      <ArticleList
        items={page.items}
        emptyTitle="Nothing saved yet."
        emptyCopy="Save a story while signed in to keep it pinned beyond Today and Catch up."
      />
    </div>
  );
}
