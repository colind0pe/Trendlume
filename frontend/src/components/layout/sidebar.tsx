"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Film,
  FolderKanban,
  Image as ImageIcon,
  Share2,
  Settings,
  LayoutDashboard,
  Flame,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { BrandMark } from "@/components/brand/logo";

const navigation = [
  { name: "工作台", href: "/", icon: LayoutDashboard },
  { name: "热点中心", href: "/trends", icon: Flame },
  { name: "项目库", href: "/projects", icon: FolderKanban },
  { name: "任务中心", href: "/tasks", icon: Film },
  { name: "素材库", href: "/assets", icon: ImageIcon },
  { name: "发布中心", href: "/publishing", icon: Share2 },
  { name: "系统设置", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="glass-panel flex w-16 shrink-0 select-none flex-col justify-between border-r border-border/70 p-2 md:w-56 md:p-3 transition-colors duration-150">
      <div>
        {/* Brand Logo */}
        <Link
          href="/"
          className="mb-3.5 flex items-center justify-center gap-2.5 px-1 py-1 md:justify-start md:px-2 group cursor-pointer"
        >
          <BrandMark
            size={28}
            glow
            className="transition-transform duration-200 group-hover:scale-105"
          />
          <div className="hidden min-w-0 md:block">
            <div className="flex items-center gap-1.5 leading-tight">
              <span className="font-extrabold text-sm tracking-tight font-sans brand-wordmark select-none">
                Trendlume
              </span>
              <span className="rounded border border-primary/25 bg-primary/10 px-1.5 py-0.5 text-xs font-mono font-medium tracking-wider text-primary">
                STUDIO
              </span>
            </div>
            <p className="text-xs text-muted-foreground leading-none mt-1">AI 短视频创作引擎</p>
          </div>
        </Link>

        {/* Navigation List */}
        <nav className="space-y-1.5" aria-label="侧边栏主导航">
          {navigation.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.name}
                href={item.href}
                title={item.name}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "group relative flex items-center justify-center gap-2.5 rounded-lg px-2 py-2 text-sm font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:justify-start md:px-3 active:scale-[0.98]",
                  isActive
                    ? "bg-primary/15 text-primary font-semibold border border-primary/25 shadow-xs backdrop-blur-md"
                    : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground border border-transparent"
                )}
              >
                <item.icon
                  aria-hidden="true"
                  className={cn(
                    "h-4 w-4 shrink-0 transition-transform duration-150",
                    isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                  )}
                />
                <span className="hidden truncate md:inline">{item.name}</span>
                {isActive && (
                  <span
                    aria-hidden="true"
                    className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r-full bg-primary hidden md:block shadow-[0_0_8px_hsl(var(--primary))]"
                  />
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Minimal Discreet Footer */}
      <div className="px-2 py-1 flex items-center justify-center md:justify-between text-xs text-muted-foreground/60 select-none">
        <span className="hidden md:inline font-mono text-[12px]">Trendlume</span>
        <span className="flex items-center gap-1.5 text-xs" title="生成引擎已就绪">
          <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-success/80 shadow-[0_0_4px_hsl(var(--success))]" />
          <span className="hidden md:inline text-muted-foreground/80 font-mono text-[12px]">就绪</span>
        </span>
      </div>
    </aside>
  );
}
