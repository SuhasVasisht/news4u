import Link from "next/link";
import { ArrowUpRight, Clock3, Layers3 } from "lucide-react";
import type { StoryCard as StoryCardType } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatRelativeTime } from "@/lib/utils";
import { ArchiveButton } from "@/components/article/archive-button";
import { AnonymousStoryActions } from "@/components/article/anonymous-story-actions";
import { ReadButton } from "@/components/article/read-button";
import { SaveButton } from "@/components/article/save-button";

export function ArticleCard({
  story,
  anonymousStateKey,
}: {
  story: StoryCardType;
  anonymousStateKey?: string;
}) {
  const isAnonymous = !story.viewerState.storyId || anonymousStateKey === "anonymous";

  return (
    <article className="surface rounded-[24px] p-4 md:rounded-[28px] md:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge>{story.representativeArticle.source.name}</Badge>
        {story.topics.map((topic) => (
          <Badge key={topic.id} className="bg-panel-strong text-muted">
            {topic.name}
          </Badge>
        ))}
        {story.sourceCount > 1 ? (
          <Badge className="bg-panel-strong text-muted">
            <Layers3 className="mr-1 h-3.5 w-3.5" />
            {story.sourceCount} sources
          </Badge>
        ) : null}
      </div>

      <div className="mt-4 flex flex-col gap-4">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3 text-sm text-muted">
            <span className="flex items-center gap-1.5">
              <Clock3 className="h-4 w-4" />
              {formatRelativeTime(story.updatedAt)}
            </span>
            <span>{story.representativeArticle.author ?? "Staff"}</span>
            {story.viewerState.isRead ? <span className="text-success">Read</span> : null}
            {story.viewerState.isSaved ? <span>Saved</span> : null}
          </div>
          <Link href={`/story/${story.id}`} className="block">
            <h2 className="headline text-2xl leading-tight text-ink hover:text-accent md:text-3xl">
              {story.canonicalHeadline}
            </h2>
          </Link>
          <p className="max-w-3xl text-base leading-7 text-muted">
            {story.compactSummary ?? story.canonicalSummary}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Link href={`/story/${story.id}`}>
            <Button className="gap-2">
              Open story
              <ArrowUpRight className="h-4 w-4" />
            </Button>
          </Link>
          {isAnonymous ? (
            <AnonymousStoryActions storyId={story.id} />
          ) : (
            <>
              <SaveButton storyId={story.id} initialSaved={story.viewerState.isSaved} />
              <ReadButton storyId={story.id} initialRead={story.viewerState.isRead} />
              <ArchiveButton storyId={story.id} initialArchived={story.viewerState.isArchived} />
            </>
          )}
          <a
            href={story.representativeArticle.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 text-sm text-muted hover:text-ink"
          >
            <ArrowUpRight className="h-4 w-4" />
            Source
          </a>
        </div>
      </div>
    </article>
  );
}
