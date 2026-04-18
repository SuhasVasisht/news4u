import { auth } from "@/auth";
import { AnonymousFeedFilter } from "@/components/article/anonymous-feed-filter";
import { ArticleList } from "@/components/article/article-list";
import { ClearTodayButton } from "@/components/article/clear-today-button";
import { getTodayFeed } from "@/lib/services/news-service";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const session = await auth();
  const feed = await getTodayFeed();
  const isAuthenticated = Boolean(session?.user?.id);

  return (
    <div className="space-y-6">
      <section className="surface rounded-[28px] px-5 py-6 md:rounded-[32px] md:px-8 md:py-8">
        <p className="text-xs uppercase tracking-[0.28em] text-muted">Today</p>
        <div className="mt-3 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <h1 className="headline text-3xl leading-tight text-ink md:text-5xl">
              Today is finite, stable, and meant to actually clear.
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-muted">
              Important stories stay prominent. Everything else fits in a single day-sized queue.
            </p>
          </div>
          <ClearTodayButton disabled={!isAuthenticated} initialCleared={feed.cleared} />
        </div>
      </section>

      {feed.important.length > 0 ? (
        <section className="space-y-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-muted">Important</p>
            <h2 className="headline mt-2 text-3xl text-ink">Major stories for the current day.</h2>
          </div>
          {isAuthenticated ? (
            <ArticleList
              items={feed.important}
              emptyTitle="No important stories right now."
              emptyCopy="The day is quiet, or the ranking model pushed everything into the lighter queue."
            />
          ) : (
            <AnonymousFeedFilter
              items={feed.important}
              emptyTitle="No visible important stories."
              emptyCopy="Anonymous read/archive state can hide stories locally in this browser."
              storageKey="anonymous"
            />
          )}
        </section>
      ) : null}

      <section className="space-y-4">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-muted">Other</p>
          <h2 className="headline mt-2 text-3xl text-ink">The rest of today’s queue.</h2>
        </div>
        {isAuthenticated ? (
          <ArticleList
            items={feed.other}
            emptyTitle="Nothing else is queued for today."
            emptyCopy="The daily snapshot is empty or your current state already cleared it."
          />
        ) : (
          <AnonymousFeedFilter
            items={feed.other}
            emptyTitle="Nothing else is visible right now."
            emptyCopy="Anonymous read/archive state can hide stories locally in this browser."
            storageKey="anonymous"
          />
        )}
      </section>
    </div>
  );
}
