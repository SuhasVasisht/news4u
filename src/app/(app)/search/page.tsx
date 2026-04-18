import { ArticleList } from "@/components/article/article-list";
import { searchStories } from "@/lib/services/news-service";

export const dynamic = "force-dynamic";

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const params = await searchParams;
  const query = params.q?.trim() ?? "";
  const results = await searchStories(query);

  return (
    <div className="space-y-6">
      <section className="surface rounded-[32px] px-6 py-8 md:px-8">
        <p className="text-xs uppercase tracking-[0.28em] text-muted">Search</p>
        <h1 className="headline mt-3 text-4xl text-ink">Find the story, not the tab.</h1>
        <p className="mt-3 max-w-2xl text-base leading-7 text-muted">
          Search scans story rollups built from canonical headlines, summaries, and article bodies.
        </p>
        {query ? (
          <p className="mt-4 text-sm text-muted">
            Showing {results.total} result{results.total === 1 ? "" : "s"} for <span className="text-ink">{query}</span>.
          </p>
        ) : null}
      </section>

      <ArticleList
        items={results.items}
        emptyTitle={query ? "No matches found." : "Start with a search query."}
        emptyCopy={
          query
            ? "Try a topic, source, headline fragment, or phrase from the underlying article text."
            : "Use the top search bar or add ?q=term to the URL."
        }
      />
    </div>
  );
}
