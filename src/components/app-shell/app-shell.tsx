import type { ReactNode } from "react";
import type { ShellData } from "@/lib/types";
import { MobileNav } from "@/components/app-shell/mobile-nav";
import { MobileTopbar } from "@/components/app-shell/mobile-topbar";
import { AppSidebar } from "@/components/app-shell/sidebar";
import { Topbar } from "@/components/app-shell/topbar";

export function AppShell({
  children,
  shellData,
}: {
  children: ReactNode;
  shellData: ShellData;
}) {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[1500px] flex-col gap-4 px-4 py-4 lg:flex-row lg:gap-6 lg:px-6 lg:py-6">
      <AppSidebar shellData={shellData} />
      <div className="flex min-w-0 flex-1 flex-col gap-6">
        <MobileTopbar shellData={shellData} />
        <MobileNav shellData={shellData} />
        <Topbar shellData={shellData} />
        <main className="fade-in min-w-0">{children}</main>
      </div>
    </div>
  );
}
