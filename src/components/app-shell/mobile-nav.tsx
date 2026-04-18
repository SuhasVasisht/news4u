import Link from "next/link";
import { Archive, Bookmark, CalendarRange, House, Search, Settings2 } from "lucide-react";
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

export function MobileNav({ shellData }: { shellData: ShellData }) {
  return (
    <div className="space-y-3 lg:hidden">
      <nav className="-mx-4 overflow-x-auto px-4">
        <div className="flex min-w-max gap-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className="surface-strong flex items-center gap-2 rounded-full px-4 py-2.5 text-sm text-muted hover:text-ink"
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
                {item.href === "/saved" ? <Badge>{shellData.savedCount}</Badge> : null}
              </Link>
            );
          })}
        </div>
      </nav>

      <div className="-mx-4 overflow-x-auto px-4">
        <div className="flex min-w-max gap-2">
          {shellData.topics.map((topic) => (
            <Link
              key={topic.id}
              href={`/topics/${topic.slug}`}
              className={cn(
                "rounded-full border px-3 py-2 text-sm whitespace-nowrap",
                topic.muted
                  ? "border-dashed text-muted opacity-60"
                  : "surface-strong text-ink hover:border-line-strong",
              )}
            >
              {topic.name}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
