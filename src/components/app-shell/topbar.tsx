import { Search } from "lucide-react";
import type { ShellData } from "@/lib/types";
import { AuthControls } from "@/components/app-shell/auth-controls";
import { Input } from "@/components/ui/input";
import { ThemeToggle } from "@/components/settings/theme-toggle";

export function Topbar({ shellData }: { shellData: ShellData }) {
  return (
    <div className="surface fade-in flex flex-col gap-4 rounded-[28px] px-5 py-4">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-muted">Daily desk</p>
          <p className="headline text-2xl text-ink">Stable snapshots for stories worth keeping up with.</p>
        </div>
        <div className="flex items-center gap-3">
          <ThemeToggle />
          <AuthControls
            isAuthenticated={shellData.user.isAuthenticated}
            name={shellData.user.name}
          />
        </div>
      </div>

      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <form action="/search" className="relative md:w-[420px]">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <Input name="q" placeholder="Search story headlines, summaries, and bodies" className="pl-10" />
        </form>
        {!shellData.user.isAuthenticated ? (
          <p className="text-sm text-muted">
            Signed out: Today and Catch up use browser-only read/archive state.
          </p>
        ) : (
          <p className="text-sm text-muted">
            Signed in as {shellData.user.email ?? shellData.user.name ?? "reader"}.
          </p>
        )}
      </div>
    </div>
  );
}
