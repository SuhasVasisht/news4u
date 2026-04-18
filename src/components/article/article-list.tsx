import type { StoryCard } from "@/lib/types";
import { ArticleCard } from "@/components/article/article-card";

export function ArticleList({
  items,
  emptyTitle,
  emptyCopy,
  anonymousStateKey,
}: {
  items: StoryCard[];
  emptyTitle: string;
  emptyCopy: string;
  anonymousStateKey?: string;
}) {
  if (items.length === 0) {
    return (
      <div className="surface rounded-[28px] p-8">
        <h2 className="headline text-3xl text-ink">{emptyTitle}</h2>
        <p className="mt-3 max-w-xl text-sm leading-7 text-muted">{emptyCopy}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {items.map((story) => (
        <ArticleCard key={story.id} story={story} anonymousStateKey={anonymousStateKey} />
      ))}
    </div>
  );
}
