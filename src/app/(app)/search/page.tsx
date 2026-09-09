import { EditionPage } from "@/components/edition/edition-page";
export const dynamic = "force-dynamic";
export default async function Page({ searchParams }: { searchParams: Promise<{ q?: string }> }) { return <EditionPage query={(await searchParams).q || ""} />; }
