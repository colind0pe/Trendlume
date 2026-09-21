"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, Film, LayoutGrid, List } from "lucide-react";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SearchInput } from "@/components/ui/input";
import { PageContainer, PageHeader } from "@/components/ui/page-shell";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/ui/status-badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  isTaskActive,
  TASK_STATUS_LABELS,
  getTaskStatusTone,
} from "@/lib/ui-constants";
import { formatDate } from "@/lib/utils";

export default function TasksGlobalPage() {
  const [statusFilter, setStatusFilter] = React.useState("all");
  const [searchQuery, setSearchQuery] = React.useState("");
  const [viewMode, setViewMode] = React.useState<"grid" | "table">("grid");

  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ["all-tasks"],
    queryFn: () => api.listAllTasks(),
    refetchInterval: (query) => {
      const currentTasks =
        (query.state.data as
          | Array<{ production_status?: string; latest_job?: { status?: string } | null }>
          | undefined) || [];
      return currentTasks.some(isTaskActive) ? 2000 : false;
    },
  });

  const filteredTasks = React.useMemo(() => {
    return tasks.filter((task) => {
      const matchesStatus =
        statusFilter === "all"
          ? true
          : statusFilter === "draft"
            ? task.production_status === "not_started" ||
              task.production_status === "queued"
            : task.production_status === statusFilter;

      const matchesSearch =
        !searchQuery.trim() ||
        task.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (task.description &&
          task.description.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (task.latest_job?.error_message &&
          task.latest_job?.error_message
            .toLowerCase()
            .includes(searchQuery.toLowerCase()));

      return matchesStatus && matchesSearch;
    });
  }, [tasks, statusFilter, searchQuery]);

  const filters = [
    { label: "全部", value: "all", count: tasks.length },
    {
      label: "运行中",
      value: "running",
      count: tasks.filter((task) => isTaskActive(task)).length,
    },
    {
      label: "已完成",
      value: "completed",
      count: tasks.filter((task) => task.production_status === "completed")
        .length,
    },
    {
      label: "失败",
      value: "failed",
      count: tasks.filter((task) => task.production_status === "failed").length,
    },
    {
      label: "草稿",
      value: "draft",
      count: tasks.filter(
        (task) =>
          task.production_status === "not_started" ||
          task.production_status === "queued",
      ).length,
    },
  ];

  return (
    <PageContainer width="wide" className="space-y-5">
      <PageHeader
        title="任务中心"
        description="追踪全部视频任务的生成进度、执行阶段与渲染日志。"
        actions={
          <div className="flex items-center gap-2">
            <div
              className="inline-flex items-center rounded-xl glass-pill p-0.5 border border-border/60 shadow-xs"
              role="group"
              aria-label="任务显示方式"
            >
              <button
                type="button"
                aria-label="卡片视图"
                aria-pressed={viewMode === "grid"}
                onClick={() => setViewMode("grid")}
                className={`inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-all cursor-pointer ${
                  viewMode === "grid"
                    ? "bg-card text-foreground shadow-xs font-medium"
                    : "hover:text-foreground hover:bg-card/40"
                }`}
              >
                <LayoutGrid aria-hidden="true" className="h-4 w-4" />
              </button>
              <button
                type="button"
                aria-label="表格视图"
                aria-pressed={viewMode === "table"}
                onClick={() => setViewMode("table")}
                className={`inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-all cursor-pointer ${
                  viewMode === "table"
                    ? "bg-card text-foreground shadow-xs font-medium"
                    : "hover:text-foreground hover:bg-card/40"
                }`}
              >
                <List aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>
            <Link href="/projects">
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5 h-9 px-3.5 text-sm"
              >
                <span>前往项目空间</span>
                <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </div>
        }
      />

      {/* Status Tabs and Quick Search Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <Tabs
          value={statusFilter}
          onValueChange={setStatusFilter}
          className="space-y-0"
        >
          <TabsList
            aria-label="任务状态"
            className="h-9 max-w-full overflow-x-auto no-scrollbar"
          >
            {filters.map((filter) => (
              <TabsTrigger
                key={filter.value}
                value={filter.value}
                className="gap-1.5 text-sm h-8 px-3"
              >
                <span>{filter.label}</span>
                <span className="rounded-full bg-secondary border border-border px-2 py-0.2 font-mono text-xs text-muted-foreground tabular-nums">
                  {filter.count}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <div className="w-full sm:w-72">
          <SearchInput
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onClear={() => setSearchQuery("")}
            placeholder="搜索任务或失败原因…"
            className="h-9 text-sm bg-card"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
          {[1, 2, 3, 4].map((item) => (
            <div
              key={item}
              className="h-48 animate-pulse rounded-xl border border-border/60 bg-card/40"
            />
          ))}
        </div>
      ) : filteredTasks.length === 0 ? (
        <EmptyState
          icon={Film}
          title="暂无符合条件的流水线任务"
          description="在具体项目中启动生成任务后，进度会集中同步在此处。"
          action={
            searchQuery || statusFilter !== "all" ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSearchQuery("");
                  setStatusFilter("all");
                }}
                className="h-7 text-xs"
              >
                重置筛选条件
              </Button>
            ) : undefined
          }
        />
      ) : viewMode === "grid" ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
          {filteredTasks.map((task) => {
            const active = isTaskActive(task);
            const progress =
              task.latest_job?.progress ?? 0;
            return (
              <Card
                key={task.id}
                className="group flex flex-col justify-between glass-card rounded-xl hover:border-primary/40 hover:shadow-glass-hover transition-all duration-200"
              >
                <CardHeader className="p-4 sm:p-5 pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <StatusBadge
                      label={
                        TASK_STATUS_LABELS[task.production_status] ||
                        task.production_status
                      }
                      tone={getTaskStatusTone(task.production_status)}
                    />
                    <span className="font-mono text-xs tabular-nums text-muted-foreground/80">
                      {formatDate(task.created_at)}
                    </span>
                  </div>
                  <CardTitle className="mt-2.5 truncate text-base font-semibold group-hover:text-primary transition-colors">
                    <Link
                      href={`/projects/${task.project_id}/tasks/${task.id}`}
                      className="hover:underline"
                    >
                      {task.title}
                    </Link>
                  </CardTitle>
                  <CardDescription className="line-clamp-2 min-h-10 text-sm mt-1 leading-relaxed">
                    {task.description || "暂无任务说明"}
                  </CardDescription>
                </CardHeader>

                <CardContent className="space-y-3 border-t border-border/60 p-4 sm:p-5 py-3 text-sm text-muted-foreground">
                  {active && (
                    <div className="space-y-1.5 rounded-lg border border-primary/20 bg-primary/5 p-2.5">
                      <div className="flex justify-between text-xs font-mono">
                        <span className="text-foreground font-medium">
                          {task.current_stage_label ||
                            task.current_stage ||
                            task.latest_job?.current_stage ||
                            "生成中"}
                        </span>
                        <span className="font-semibold text-primary tabular-nums">
                          {progress}%
                        </span>
                      </div>
                      <Progress value={progress} className="h-1.5" />
                    </div>
                  )}

                  {task.production_status === "failed" &&
                    task.latest_job?.error_message && (
                      <div className="flex gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-2.5 text-xs text-destructive">
                        <AlertCircle
                          aria-hidden="true"
                          className="mt-0.5 h-4 w-4 shrink-0"
                        />
                        <span className="line-clamp-2 font-mono">
                          {task.latest_job?.error_message}
                        </span>
                      </div>
                    )}

                  <div className="flex items-center justify-between text-xs">
                    <span>分镜序列</span>
                    <span className="font-mono font-medium text-foreground">
                      {task.scenes_count || 0} 个镜头
                    </span>
                  </div>
                </CardContent>

                <CardFooter className="p-4 sm:p-5 pt-0">
                  <Link
                    href={`/projects/${task.project_id}/tasks/${task.id}`}
                    className="w-full"
                  >
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full justify-between group/btn h-9 px-3.5 text-sm"
                    >
                      <span>进入分镜工坊</span>
                      <ArrowRight
                        aria-hidden="true"
                        className="h-4 w-4 transition-transform duration-150 group-hover/btn:translate-x-0.5"
                      />
                    </Button>
                  </Link>
                </CardFooter>
              </Card>
            );
          })}
        </div>
      ) : (
        /* Dense Pipeline Table View */
        <div className="overflow-hidden rounded-xl border border-border/80 glass-panel shadow-glass">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="border-b border-border/70 bg-secondary/40 text-muted-foreground text-xs uppercase tracking-wider">
                  <th className="py-3 px-4 font-semibold">状态</th>
                  <th className="py-3 px-4 font-semibold">任务标题</th>
                  <th className="py-3 px-4 font-semibold">流程阶段 / 进度</th>
                  <th className="py-3 px-4 font-semibold text-center">
                    分镜数
                  </th>
                  <th className="py-3 px-4 font-semibold">创建时间</th>
                  <th className="py-3 px-4 font-semibold text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {filteredTasks.map((task) => {
                  const active = isTaskActive(task);
                  const progress =
                    task.latest_job?.progress ?? 0;
                  return (
                    <tr
                      key={task.id}
                      className="hover:bg-secondary/30 transition-colors"
                    >
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        <StatusBadge
                          label={
                            TASK_STATUS_LABELS[task.production_status] ||
                            task.production_status
                          }
                          tone={getTaskStatusTone(task.production_status)}
                        />
                      </td>
                      <td className="py-3.5 px-4 min-w-[220px] max-w-[340px]">
                        <Link
                          href={`/projects/${task.project_id}/tasks/${task.id}`}
                          className="font-semibold text-foreground hover:text-primary transition-colors block truncate"
                        >
                          {task.title}
                        </Link>
                        {task.latest_job?.error_message &&
                        task.production_status === "failed" ? (
                          <p className="text-xs text-destructive truncate font-mono mt-1">
                            {task.latest_job?.error_message}
                          </p>
                        ) : task.description ? (
                          <p className="text-xs text-muted-foreground truncate mt-1">
                            {task.description}
                          </p>
                        ) : null}
                      </td>
                      <td className="py-3.5 px-4 min-w-[160px]">
                        {active ? (
                          <div className="space-y-1.5">
                            <div className="flex justify-between text-xs font-mono">
                              <span className="text-foreground">
                                {task.current_stage_label ||
                                  task.current_stage ||
                                  task.latest_job?.current_stage ||
                                  "生成中"}
                              </span>
                              <span className="font-semibold text-primary">
                                {progress}%
                              </span>
                            </div>
                            <Progress value={progress} className="h-1.5" />
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground font-mono">
                            {task.production_status === "completed"
                              ? "已完成全自动合成"
                              : task.production_status === "failed"
                                ? "已中断"
                                : "待启动"}
                          </span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-center whitespace-nowrap font-mono text-sm">
                        {task.scenes_count || 0}
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap font-mono text-xs text-muted-foreground">
                        {formatDate(task.created_at)}
                      </td>
                      <td className="py-3.5 px-4 text-right whitespace-nowrap">
                        <Link
                          href={`/projects/${task.project_id}/tasks/${task.id}`}
                        >
                          <Button
                            size="sm"
                            variant="outline"
                            className="gap-1 h-8 px-3 text-xs sm:text-sm"
                          >
                            <span>进入</span>
                            <ArrowRight
                              aria-hidden="true"
                              className="h-3.5 w-3.5"
                            />
                          </Button>
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </PageContainer>
  );
}
