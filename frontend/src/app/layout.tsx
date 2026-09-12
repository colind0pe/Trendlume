import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";

export const metadata: Metadata = {
  title: "Trendlume — 短视频工作台",
  description: "AI 短视频创作与发布工作台",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon.ico", sizes: "32x32" },
    ],
    shortcut: "/icon.svg",
    apple: "/icon.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>
        <Providers>
          <div className="flex h-screen overflow-hidden bg-background relative">
            {/* Ambient Studio Lighting Orbs for Subtle Depth */}
            <div
              aria-hidden="true"
              className="pointer-events-none fixed -top-32 left-[15%] h-[420px] w-[420px] rounded-full bg-primary/[0.05] dark:bg-primary/[0.07] blur-[120px]"
            />
            <div
              aria-hidden="true"
              className="pointer-events-none fixed -bottom-32 right-[10%] h-[380px] w-[380px] rounded-full bg-cyan-500/[0.04] dark:bg-cyan-500/[0.05] blur-[120px]"
            />

            <Sidebar />
            <div className="flex flex-col flex-1 min-w-0 overflow-hidden relative z-10">
              <Header />
              <a
                href="#main-content"
                className="sr-only z-[100] rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground focus:not-sr-only focus:absolute focus:left-4 focus:top-4 shadow-sm"
              >
                跳转到主要内容
              </a>
              <main id="main-content" className="min-h-0 flex-1 overflow-y-auto bg-transparent">
                {children}
              </main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
