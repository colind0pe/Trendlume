"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowRight, BookOpen, Clapperboard, Film, Flame, FolderKanban, Loader2, Play, Plus, ExternalLink, Download, Sparkles, ShoppingBag } from "lucide-react";
import { api } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer, PageHeader, SectionHeader } from "@/components/ui/page-shell";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/ui/status-badge";
import { getTaskStatusTone, isTaskActive, TASK_STATUS_LABELS, formatStageName, formatTemplateName, PRODUCTION_MODE_SPECS } from "@/lib/ui-constants";
import { cn, formatDate } from "@/lib/utils";

export default function DashboardPage() {
  const [previewVideo, setPreviewVideo] = React.useState<{ title: string; url: string } | null>(null);

  const { data: projects = [], isLoading: isProjectsLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects(6),
  });

  const { data: tasks = [] } = useQuery({
    queryKey: ["all-tasks"],
    queryFn: () => api.listAllTasks(),
    refetchInterval: (query) => {
      const currentTasks = (query.state.data as Array<{ status?: string; active_job?: { status?: string } | null }> | undefined) || [];
      return currentTasks.some(isTaskActive) ? 2000 : false;
    },
  });

  const runningTasks = tasks.filter(isTaskActive);
  const completedTasks = tasks.filter((task) => task.status === "completed" && task.result_payload?.final_video_url);

  return (
    <PageContainer width="wide" className="space-y-6">
      <PageHeader
        title="工作台"
        description="短视频创作流水线概览、运行中任务与最新成片。"
        actions={(
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href="/trends"
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border/80 bg-card/50 px-3.5 text-sm font-medium text-foreground backdrop-blur-sm transition-all duration-150 hover:border-foreground/20 hover:bg-secondary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
            >
              <Flame aria-hidden="true" className="h-4 w-4" />
              查看热点
            </Link>
            <Link href="/projects">
              <Button variant="default" className="gap-1.5 h-9 px-3.5 text-sm">
                <Plus aria-hidden="true" className="h-4 w-4" />
                新建项目
              </Button>
            </Link>
          </div>
        )}
      />

      <section className="space-y-3" aria-labelledby="production-modes-title">
        <SectionHeader title={<span id="production-modes-title">选择内容赛道</span>} />
        <div className="grid gap-3 md:grid-cols-3">
          {([
            { mode: "knowledge" as const, href: "/projects", icon: BookOpen, action: "新建 Knowledge 项目" },
            { mode: "commerce" as const, href: "/products", icon: ShoppingBag, action: "进入商品与方案" },
            { mode: "drama" as const, href: "/drama", icon: Clapperboard, action: "进入 Drama 制片" },
          ]).map(({ mode, href, icon: Icon, action }) => (
            <Card key={mode} className="group border-border/80 bg-card/70 transition-colors hover:border-primary/40">
              <CardContent className="flex h-full flex-col p-4 sm:p-5">
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <span className="rounded-lg border border-primary/20 bg-primary/10 p-2 text-primary"><Icon className="h-4 w-4" aria-hidden="true" /></span>
                  {PRODUCTION_MODE_SPECS[mode].label}
                </div>
                <p className="mt-3 flex-1 text-sm leading-6 text-muted-foreground">{PRODUCTION_MODE_SPECS[mode].description}</p>
                <Link href={href} className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
                  {action}<ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Studio Pulse Metrics Strip */}
      <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
        <div
          className={cn(
            "rounded-xl glass-card p-4 sm:p-5 transition-all duration-200 flex flex-col justify-between",
            runningTasks.length > 0
              ? "border-primary/50 shadow-glass"
              : "hover:border-primary/40"
          )}
        >
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="font-medium">正在生成</span>
            <div
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-lg transition-colors shadow-xs",
                runningTasks.length > 0
                  ? "bg-primary/15 text-primary shadow-[0_0_12px_rgba(99,102,241,0.25)]"
                  : "bg-secondary/70 text-muted-foreground"
              )}
            >
              {runningTasks.length > 0 ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
            </div>
          </div>
          <div className="mt-3.5 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-foreground tabular-nums">
              {runningTasks.length}
            </span>
            <span className="text-xs text-muted-foreground">个活跃任务</span>
          </div>
        </div>

        <div className="rounded-xl glass-card p-4 sm:p-5 transition-all duration-200 hover:border-success/50 flex flex-col justify-between">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="font-medium">已就绪成片</span>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-success/15 text-success shadow-xs shadow-[0_0_10px_rgba(16,185,129,0.2)]">
              <Film className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3.5 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-foreground tabular-nums">
              {completedTasks.length}
            </span>
            <span className="text-xs text-muted-foreground">部视频</span>
          </div>
        </div>

        <div className="rounded-xl glass-card p-4 sm:p-5 transition-all duration-200 hover:border-primary/40 flex flex-col justify-between">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="font-medium">项目空间</span>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary/70 text-foreground shadow-xs">
              <FolderKanban className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3.5 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-foreground tabular-nums">
              {projects.length}
            </span>
            <span className="text-xs text-muted-foreground">个空间</span>
          </div>
        </div>

        <div className="rounded-xl glass-card p-4 sm:p-5 transition-all duration-200 hover:border-primary/40 flex flex-col justify-between">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="font-medium">流水线任务</span>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary/70 text-foreground shadow-xs">
              <Clapperboard className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3.5 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-foreground tabular-nums">
              {tasks.length}
            </span>
            <span className="text-xs text-muted-foreground">条任务</span>
          </div>
        </div>
      </div>

      {/* Live Pipeline Strip */}
      {runningTasks.length > 0 && (
        <section className="space-y-2.5" aria-labelledby="running-tasks-title">
          <SectionHeader
            title={(
              <span id="running-tasks-title" className="flex items-center gap-2">
                <span>实时生成任务</span>
                <span className="rounded border border-primary/25 bg-primary/10 px-1.5 py-0.5 text-xs font-mono text-primary tabular-nums">
                  {runningTasks.length} 运行中
                </span>
              </span>
            )}
          />
          <div className="grid gap-2.5">
            {runningTasks.map((task) => {
              const progress = task.active_job?.progress ?? task.progress_percentage;
              return (
                <Card key={task.id} className="border-primary/30">
                  <CardContent className="space-y-2 p-3 sm:p-3.5">
                    <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex min-w-0 items-center gap-2">
                        <StatusBadge label={TASK_STATUS_LABELS[task.status] || task.status} tone={getTaskStatusTone(task.status)} />
                        <span className="truncate text-xs sm:text-sm font-semibold text-foreground">{task.title}</span>
                      </div>
                      <span className="font-mono text-xs tabular-nums text-primary font-bold">{progress}%</span>
                    </div>
                    <Progress value={progress} className="h-1" />
                    <div className="flex flex-col gap-1.5 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between pt-0.5">
                      <span>流程阶段：<strong className="text-foreground">{formatStageName(task.current_stage || task.active_job?.current_stage || task.job_type)}</strong></span>
                      <Link
                        href={`/projects/${task.project_id}/tasks/${task.id}`}
                        className="inline-flex items-center gap-1 font-medium text-primary hover:underline group"
                      >
                        <span>进入故事板</span>
                        <ArrowRight aria-hidden="true" className="h-3 w-3 transition-transform duration-150 group-hover:translate-x-0.5" />
                      </Link>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </section>
      )}

      {/* Main Studio Grid: Left Projects / Right Videos */}
      <div className="grid gap-5 lg:grid-cols-3">
        {/* Left 2 Cols: Recent Projects */}
        <section className="space-y-3 lg:col-span-2" aria-labelledby="recent-projects-title">
          <SectionHeader
            title={<span id="recent-projects-title">最近项目</span>}
            actions={(
              <Link href="/projects" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
                全部项目 ({projects.length}) →
              </Link>
            )}
          />
          {isProjectsLoading ? (
            <div className="grid gap-3.5 sm:grid-cols-2">
              {[1, 2].map((item) => (
                <div key={item} className="h-36 animate-pulse rounded-xl border border-border/60 bg-card/40" />
              ))}
            </div>
          ) : projects.length === 0 ? (
            <EmptyState icon={FolderKanban} title="暂无项目" description="创建项目后，排版模板和视频任务会集中在此管理。" />
          ) : (
            <div className="grid gap-3.5 sm:grid-cols-2">
              {projects.map((project) => (
                <Card key={project.id} className="group flex flex-col justify-between hover:border-primary/40 transition-all duration-150">
                  <CardHeader className="p-4 sm:p-5 pb-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5">
                        <span className="rounded-md border border-primary/20 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                          {PRODUCTION_MODE_SPECS[project.primary_production_mode].label}
                        </span>
                        <span className="rounded-md border border-border/80 bg-secondary/80 px-2 py-0.5 font-mono text-xs font-medium text-foreground shadow-xs">
                          {project.aspect_ratio}
                        </span>
                      </div>
                      <span className="font-mono text-xs tabular-nums text-muted-foreground">
                        {formatDate(project.updated_at)}
                      </span>
                    </div>
                    <CardTitle className="truncate text-base mt-2 group-hover:text-primary transition-colors">
                      {project.name}
                    </CardTitle>
                    <CardDescription className="line-clamp-2 text-xs sm:text-sm leading-relaxed mt-1 text-muted-foreground">
                      {project.description || "暂无项目说明"}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="flex items-center justify-between gap-3 border-t border-border/60 px-4 sm:px-5 py-3 text-xs sm:text-sm">
                    <span className="truncate text-muted-foreground">
                      模板：<strong className="text-foreground/85 font-normal">{formatTemplateName(project.template?.template_id, project.template?.name) || "默认模板"}</strong>
                    </span>
                    <Link
                      href={`/projects/${project.id}`}
                      className="inline-flex shrink-0 items-center gap-1 font-medium text-primary hover:underline group"
                    >
                      <span>进入空间</span>
                      <ArrowRight aria-hidden="true" className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5" />
                    </Link>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </section>

        {/* Right 1 Col: Recent Completed Videos */}
        <section className="space-y-3" aria-labelledby="ready-videos-title">
          <SectionHeader
            title={<span id="ready-videos-title">最近成片</span>}
            actions={(
              <Link href="/tasks" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
                全部任务 →
              </Link>
            )}
          />
          {completedTasks.length === 0 ? (
            <EmptyState icon={Film} title="暂无成片" description="完成视频合成后，MP4 成片会展示在此处。" />
          ) : (
            <div className="space-y-3">
              {completedTasks.slice(0, 4).map((task) => (
                <Card key={task.id} className="flex items-center justify-between gap-3.5 p-4 hover:border-success/40 transition-all duration-150">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span aria-hidden="true" className="h-2 w-2 rounded-full bg-success shadow-[0_0_6px_hsl(var(--success))] shrink-0" />
                      <span className="truncate text-sm font-semibold text-foreground">{task.title}</span>
                    </div>
                    <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground font-mono">
                      <span>成片 MP4</span>
                      <span>·</span>
                      <span>{formatDate(task.updated_at)}</span>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() =>
                        task.result_payload?.final_video_url &&
                        setPreviewVideo({ title: task.title, url: task.result_payload.final_video_url })
                      }
                      aria-label={`预览 ${task.title}`}
                      title="预览成片"
                      className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border/80 bg-secondary/80 backdrop-blur-sm text-foreground transition-all hover:bg-primary/20 hover:border-primary/40 hover:text-primary active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer shadow-xs"
                    >
                      <Play aria-hidden="true" className="h-3.5 w-3.5 fill-current" />
                    </button>
                    <Link
                      href={`/projects/${task.project_id}/tasks/${task.id}`}
                      aria-label={`进入 ${task.title} 故事板`}
                      title="打开故事板"
                      className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border/80 bg-secondary/80 backdrop-blur-sm text-foreground transition-all hover:bg-secondary active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring shadow-xs"
                    >
                      <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
                    </Link>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* Video Preview Modal */}
      <Dialog open={Boolean(previewVideo)} onOpenChange={(open) => !open && setPreviewVideo(null)} className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="truncate pr-6 text-base sm:text-lg font-semibold">{previewVideo?.title || "成片预览"}</DialogTitle>
          <DialogDescription>本地渲染完成的高清 MP4 视频。</DialogDescription>
        </DialogHeader>
        {previewVideo && (
          <div className="space-y-4 pt-1">
            <div className="relative max-h-[500px] w-full mx-auto overflow-hidden rounded-xl border border-border bg-black/95 shadow-xl flex items-center justify-center">
              <video
                src={previewVideo.url}
                controls
                autoPlay
                className="max-h-[500px] w-auto max-w-full object-contain"
              />
            </div>
            <div className="flex items-center justify-between pt-1 text-sm">
              <a
                href={previewVideo.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors"
              >
                <ExternalLink className="h-4 w-4" />
                新标签页打开
              </a>
              <a
                href={previewVideo.url}
                download
                className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline"
              >
                <Download className="h-4 w-4" />
                下载 MP4
              </a>
            </div>
          </div>
        )}
      </Dialog>
    </PageContainer>
  );
}
