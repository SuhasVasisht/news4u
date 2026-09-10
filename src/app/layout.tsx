import type { Metadata } from "next";
import "./globals.css";
import "@/components/edition/edition.css";
import { themeBootstrap } from "@/lib/edition-themes";
export const metadata: Metadata = { title: "News 4 u", description: "The daily edition. Technology, markets, and the wider world." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: themeBootstrap }} /></head><body>{children}</body></html>; }
