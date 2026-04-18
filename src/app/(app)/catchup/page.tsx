import { auth } from "@/auth";
import { AnonymousFeedFilter } from "@/components/article/anonymous-feed-filter";
import { ArticleList } from "@/components/article/article-list";
import { getCatchupFeed } from "@/lib/services/news-service";

export const dynamic = "force-dynamic";

export default async function CatchupPage() {
  const session = await auth();
  const feed = await getCatchupFeed();
  const isAuthenticated = Boolean(session?.user?.id);

  return (
    <div className="space-y-6">
      <section className="surface rounded-[32px] px-6 py-8 md:px-8">
        <p className="text-xs uppercase tracking-[0.28em] text-muted">Catch up</p>
        <h1 className="headline mt-3 text-4xl text-ink">Unread prior days, compressed.</h1>
        <p className="mt-3 max-w-2xl text-base leading-7 text-muted">
          Catch up is intentionally smaller than Today so it feels skimmable instead of punitive.
        </p>
      </section>

      {feed.groups.map((group) => (
        <section key={group.date} className="space-y-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-muted">{group.label}</p>
            <h2 className="headline mt-2 text-3xl text-ink">{group.date}</h2>
          </div>
          {isAuthenticated ? (
            <ArticleList
              items={group.items}
              emptyTitle="No stories in this group."
              emptyCopy="Everything here has already been handled or filtered out."
            />
          ) : (
            <AnonymousFeedFilter
              items={group.items}
              emptyTitle="No visible stories in this group."
              emptyCopy="Anonymous read/archive state can hide stories locally in this browser."
              storageKey="anonymous"
            />
          )}
        </section>
      ))}
    </div>
  );
}
