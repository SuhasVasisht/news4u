import { EditionPage } from "@/components/edition/edition-page";
import { getEdition } from "@/lib/services/edition-service";
import { getStory } from "@/lib/services/news-service";
import { notFound, redirect } from "next/navigation";
export const dynamic = "force-dynamic";
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if ((await getEdition()).stories.some(story => story.id === id)) return <EditionPage story={id} />;
  const legacy = await getStory(id);
  if (legacy && /^https?:\/\//i.test(legacy.representativeArticle.url)) redirect(legacy.representativeArticle.url);
  notFound();
}
