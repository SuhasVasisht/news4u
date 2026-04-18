import type { ReactNode } from "react";
import type { ShellData } from "@/lib/types";
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
    <div className="mx-auto flex min-h-screen w-full max-w-[1500px] flex-col gap-6 px-4 py-6 lg:flex-row lg:px-6">
      <AppSidebar shellData={shellData} />
      <div className="flex min-w-0 flex-1 flex-col gap-6">
        <Topbar shellData={shellData} />
        <main className="fade-in min-w-0">{children}</main>
      </div>
    </div>
  );
}
