import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell/app-shell";
import { getShellData } from "@/lib/services/news-service";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const shellData = await getShellData();
  return <AppShell shellData={shellData}>{children}</AppShell>;
}
