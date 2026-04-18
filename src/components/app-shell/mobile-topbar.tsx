import { Search } from "lucide-react";
import type { ShellData } from "@/lib/types";
import { AuthControls } from "@/components/app-shell/auth-controls";
import { Input } from "@/components/ui/input";
import { ThemeToggle } from "@/components/settings/theme-toggle";

export function MobileTopbar({ shellData }: { shellData: ShellData }) {
  return (
    <div className="surface fade-in space-y-4 rounded-[24px] px-4 py-4 lg:hidden">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-muted">News 4 u</p>
          <p className="headline mt-2 text-2xl text-ink">Daily stories without the desktop-only shell.</p>
        </div>
        <ThemeToggle />
      </div>

      <form action="/search" className="relative">
        <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
        <Input name="q" placeholder="Search stories" className="pl-10" />
      </form>

      <div className="flex flex-col gap-3">
        <AuthControls isAuthenticated={shellData.user.isAuthenticated} name={shellData.user.name} />
        {!shellData.user.isAuthenticated ? (
          <p className="text-sm leading-6 text-muted">
            Sign in to save preferences.
          </p>
        ) : (
          <p className="text-sm leading-6 text-muted">
            Signed in as {shellData.user.email ?? shellData.user.name ?? "reader"}.
          </p>
        )}
      </div>
    </div>
  );
}
