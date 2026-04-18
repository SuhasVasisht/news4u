import { notFound, redirect } from "next/navigation";
import { getStoryIdForArticle } from "@/lib/services/news-service";

export const dynamic = "force-dynamic";

export default async function ArticlePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const storyId = await getStoryIdForArticle(id);

  if (!storyId) {
    notFound();
  }

  redirect(`/story/${storyId}`);
}
