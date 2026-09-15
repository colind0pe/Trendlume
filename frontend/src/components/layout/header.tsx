"use client";

import { useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useTaskEvents, type TaskEvent } from "@/lib/use-task-events";
import { ThemeToggle } from "@/components/theme-provider";

const TASK_LIST_REFRESH_EVENTS = new Set([
  "task.queued",
  "task.started",
  "task.completed",
  "task.failed",
  "task.cancelled",
  "task_queued",
  "task_started",
  "task_completed",
  "task_failed",
  "task_cancelled",
  "job.started",
  "job.retrying",
  "job.completed",
  "job.failed",
  "job.cancelled",
  "job.uncertain",
  "step.completed",
]);

export function Header() {
  const pathname = usePathname();
  const queryClient = useQueryClient();

  const refreshTaskLists = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["all-tasks"] });
  }, [queryClient]);

  const handleEvent = useCallback(
    (event: TaskEvent) => {
      if (event.event === "publish.verification_needed") {
        queryClient.invalidateQueries({ queryKey: ["pending-verifications"] });
      }
      if (event.data?.task_id && TASK_LIST_REFRESH_EVENTS.has(event.event)) {
        refreshTaskLists();
      }
    },
    [queryClient, refreshTaskLists]
  );
  const handleReconnect = useCallback(() => {
    refreshTaskLists();
    queryClient.invalidateQueries({ queryKey: ["pending-verifications"] });
  }, [queryClient, refreshTaskLists]);

  const { isConnected } = useTaskEvents({
    onEvent: handleEvent,
    onReconnect: handleReconnect,
  });

  // Dynamic breadcrumb labels
  const getBreadcrumbs = () => {
    if (pathname === "/") return [{ name: "工作台", href: "/" }];
    const segments = pathname.split("/").filter(Boolean);
    const crumbs = [{ name: "工作台", href: "/" }];

    if (segments[0] === "projects") {
      crumbs.push({ name: "项目库", href: "/projects" });
      if (segments[1] && segments[1] !== "tasks") {
        crumbs.push({ name: "项目空间", href: `/projects/${segments[1]}` });
        if (segments[2] === "tasks" && segments[3]) {
          crumbs.push({ name: "故事板", href: pathname });
        }
      }
    } else if (segments[0] === "tasks") {
      crumbs.push({ name: "任务中心", href: "/tasks" });
    } else if (segments[0] === "trends") {
      crumbs.push({ name: "热点中心", href: "/trends" });
    } else if (segments[0] === "assets") {
      crumbs.push({ name: "素材库", href: "/assets" });
    } else if (segments[0] === "publishing") {
      crumbs.push({ name: "发布中心", href: "/publishing" });
    } else if (segments[0] === "settings") {
      crumbs.push({ name: "系统设置", href: "/settings" });
    }

    return crumbs;
  };

  const breadcrumbs = getBreadcrumbs();

  return (
    <header className="glass-panel sticky top-0 z-30 flex h-12 shrink-0 items-center justify-between border-b border-border/70 px-3.5 md:px-5 transition-colors">
      {/* Left: Dynamic Breadcrumbs Navigation */}
      <nav aria-label="路径导航" className="flex items-center min-w-0">
        <ol className="flex items-center gap-2 text-sm text-muted-foreground min-w-0">
          {breadcrumbs.map((crumb, idx) => {
            const isLast = idx === breadcrumbs.length - 1;
            return (
              <li key={crumb.href + idx} className="flex items-center gap-2 min-w-0">
                {idx > 0 && (
                  <ChevronRight aria-hidden="true" className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0" />
                )}
                {isLast ? (
                  <span className="font-semibold text-foreground truncate max-w-[240px]" aria-current="page">
                    {crumb.name}
                  </span>
                ) : (
                  <Link
                    href={crumb.href}
                    className="hover:text-foreground transition-colors truncate max-w-[160px]"
                  >
                    {crumb.name}
                  </Link>
                )}
              </li>
            );
          })}
        </ol>
      </nav>

        {/* Right: Realtime status & Theme switch */}
      <div className="flex items-center gap-2 shrink-0">
        {!isConnected ? (
          <div
            className="flex items-center gap-1.5 rounded-full bg-warning/15 px-2 py-0.5 text-xs text-warning font-medium shadow-xs"
            role="status"
            aria-live="polite"
            title="实时连接中断，正在尝试重新连接…"
          >
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-warning animate-pulse" />
            <span className="hidden sm:inline">重新连接中</span>
          </div>
        ) : (
          <div
            className="flex items-center justify-center h-7 w-7 rounded-lg text-muted-foreground/60 transition-colors cursor-default"
            title="实时同步已就绪"
            aria-label="实时同步已就绪"
          >
            <span aria-hidden="true" className="h-2 w-2 rounded-full bg-success/80 shadow-[0_0_5px_hsl(var(--success))]" />
          </div>
        )}

        <ThemeToggle />
      </div>
    </header>
  );
}
