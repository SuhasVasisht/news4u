import { notFound } from "next/navigation";
import { ArrowUpRight } from "lucide-react";
import { ArchiveButton } from "@/components/article/archive-button";
import { ReaderTracker } from "@/components/article/reader-tracker";
import { ReadButton } from "@/components/article/read-button";
import { SaveButton } from "@/components/article/save-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/utils";
import { getStory } from "@/lib/services/news-service";

export const dynamic = "force-dynamic";

export default async function StoryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const story = await getStory(id);

  if (!story) {
    notFound();
  }

  return (
    <div className="space-y-6">
      <ReaderTracker storyId={story.id} initialRead={story.viewerState.isRead} />
      <section className="surface rounded-[32px] px-6 py-8 md:px-8">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{story.representativeArticle.source.name}</Badge>
          {story.topics.map((topic) => (
            <Badge key={topic.id} className="bg-panel-strong text-muted">
              {topic.name}
            </Badge>
          ))}
        </div>
        <h1 className="headline mt-5 max-w-4xl text-4xl leading-tight text-ink md:text-5xl">
          {story.canonicalHeadline}
        </h1>
        <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-muted">
          <span>{formatDateTime(story.updatedAt)}</span>
          <span>Importance {story.importanceScore.toFixed(1)}</span>
          <span>{story.sourceCount} sources</span>
        </div>
        <p className="mt-5 max-w-3xl text-lg leading-8 text-muted">{story.canonicalSummary}</p>
        <div className="mt-6 flex flex-wrap gap-3">
          <SaveButton storyId={story.id} initialSaved={story.viewerState.isSaved} />
          <ReadButton storyId={story.id} initialRead={story.viewerState.isRead} />
          <ArchiveButton storyId={story.id} initialArchived={story.viewerState.isArchived} />
          <a href={story.representativeArticle.url} target="_blank" rel="noreferrer">
            <Button className="gap-2">
              Open lead source
              <ArrowUpRight className="h-4 w-4" />
            </Button>
          </a>
        </div>
      </section>

      <section className="surface rounded-[32px] px-6 py-8 md:px-10">
        <p className="text-xs uppercase tracking-[0.28em] text-muted">Story cluster</p>
        <div className="mt-6 space-y-5">
          {story.articles.map((article) => (
            <article key={article.id} className="surface-strong rounded-[24px] p-5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge>{article.source.name}</Badge>
                <span className="text-sm text-muted">{formatDateTime(article.publishedAt)}</span>
              </div>
              <h2 className="headline mt-3 text-2xl text-ink">{article.title}</h2>
              <p className="mt-3 max-w-3xl text-base leading-7 text-muted">{article.summary}</p>
              <p className="mt-4 max-w-3xl text-base leading-8 text-muted">{article.contentText}</p>
              <div className="mt-4">
                <a href={article.url} target="_blank" rel="noreferrer">
                  <Button variant="secondary" className="gap-2">
                    Open original article
                    <ArrowUpRight className="h-4 w-4" />
                  </Button>
                </a>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
