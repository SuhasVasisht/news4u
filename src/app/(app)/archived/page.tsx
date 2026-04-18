import { ArticleList } from "@/components/article/article-list";
import { getArchivedFeed } from "@/lib/services/news-service";

export const dynamic = "force-dynamic";

export default async function ArchivedPage() {
  const page = await getArchivedFeed();

  return (
    <div className="space-y-6">
      <section className="surface rounded-[32px] px-6 py-8 md:px-8">
        <p className="text-xs uppercase tracking-[0.28em] text-muted">Archived</p>
        <h1 className="headline mt-3 text-4xl text-ink">Handled, aged out, or deliberately shelved.</h1>
        <p className="mt-3 max-w-2xl text-base leading-7 text-muted">
          Archive stays queryable, but archived stories do not re-enter Today unless a future resurfacing rule is added.
        </p>
      </section>

      <ArticleList
        items={page.items}
        emptyTitle="No archived stories yet."
        emptyCopy="Archive a story while signed in to move it out of the active tabs."
      />
    </div>
  );
}
