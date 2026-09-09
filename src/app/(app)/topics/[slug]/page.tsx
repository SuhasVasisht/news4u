import { EditionPage } from "@/components/edition/edition-page";
export const dynamic = "force-dynamic";
export default async function Page({ params }: { params: Promise<{ slug: string }> }) { const { slug } = await params; const names: Record<string,string> = { tech: "Technology", technology: "Technology", finance: "Markets", markets: "Markets", world: "World", politics: "Policy", policy: "Policy" }; return <EditionPage sector={names[slug] || "All sectors"} />; }
