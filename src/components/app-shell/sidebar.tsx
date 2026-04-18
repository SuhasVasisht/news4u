import Link from "next/link";
import { Archive, Bookmark, CalendarRange, House, Layers3, Settings2, Search } from "lucide-react";
import type { ShellData } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Today", icon: House },
  { href: "/catchup", label: "Catch up", icon: CalendarRange },
  { href: "/saved", label: "Saved", icon: Bookmark },
  { href: "/archived", label: "Archived", icon: Archive },
  { href: "/search", label: "Search", icon: Search },
  { href: "/settings", label: "Settings", icon: Settings2 },
];

export function AppSidebar({ shellData }: { shellData: ShellData }) {
  return (
    <aside className="surface fade-in flex w-full max-w-xs flex-col gap-6 rounded-[28px] p-5 lg:sticky lg:top-6 lg:h-[calc(100vh-3rem)]">
      <div className="space-y-2">
        <p className="text-xs uppercase tracking-[0.28em] text-muted">Signal Desk</p>
        <h1 className="headline text-3xl text-ink">Finite daily feed, not endless churn.</h1>
        <p className="text-sm leading-6 text-muted">
          Stories are grouped into Today, Catch up, Saved, and Archived so the queue can actually close.
        </p>
      </div>

      <nav className="space-y-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className="surface-strong flex items-center justify-between rounded-2xl px-4 py-3 text-sm text-muted hover:-translate-y-0.5 hover:text-ink"
            >
              <span className="flex items-center gap-3">
                <Icon className="h-4 w-4" />
                {item.label}
              </span>
              {item.href === "/saved" ? <Badge>{shellData.savedCount}</Badge> : null}
            </Link>
          );
        })}
      </nav>

      <section className="space-y-3">
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.28em] text-muted">
          <Layers3 className="h-3.5 w-3.5" />
          Topics
        </div>
        <div className="space-y-2">
          {shellData.topics.map((topic) => (
            <Link
              key={topic.id}
              href={`/topics/${topic.slug}`}
              className={cn(
                "flex items-center justify-between rounded-2xl border px-4 py-3 text-sm",
                topic.muted
                  ? "border-dashed text-muted opacity-60"
                  : "surface-strong text-ink hover:border-line-strong",
              )}
            >
              <span>{topic.name}</span>
              <span className="text-xs text-muted">{topic.storyCount}</span>
            </Link>
          ))}
        </div>
      </section>
    </aside>
  );
}
