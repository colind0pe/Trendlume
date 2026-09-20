"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, FolderKanban, LayoutGrid, List, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Field } from "@/components/ui/field";
import { IconButton } from "@/components/ui/icon-button";
import { Input, SearchInput } from "@/components/ui/input";
import { PageContainer, PageHeader } from "@/components/ui/page-shell";
import { Textarea } from "@/components/ui/textarea";
import { formatDate } from "@/lib/utils";
import { ProductionModeSelector } from "@/components/projects/production-mode-selector";
import { PRODUCTION_MODE_SPECS } from "@/lib/ui-constants";
import type { ProductionMode } from "@/lib/types";

export default function ProjectsPage() {
  const queryClient = useQueryClient();
  const [viewMode, setViewMode] = React.useState<"grid" | "list">("grid");
  const [searchQuery, setSearchQuery] = React.useState("");
  const [aspectFilter, setAspectFilter] = React.useState<string>("all");
  const [isCreateOpen, setIsCreateOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [aspectRatio, setAspectRatio] = React.useState("9:16");
  const [primaryProductionMode, setPrimaryProductionMode] = React.useState<ProductionMode>("knowledge");
  const [projectToDelete, setProjectToDelete] = React.useState<{ id: string; name: string } | null>(null);

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects(),
  });

  const filteredProjects = React.useMemo(() => {
    return projects.filter((project) => {
      const matchesSearch =
        !searchQuery.trim() ||
        project.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (project.description && project.description.toLowerCase().includes(searchQuery.toLowerCase()));
      const matchesAspect = aspectFilter === "all" || project.aspect_ratio === aspectFilter;
      return matchesSearch && matchesAspect;
    });
  }, [projects, searchQuery, aspectFilter]);

  const countsByAspect = React.useMemo(() => {
    const counts = { all: projects.length, "9:16": 0, "16:9": 0, "1:1": 0 };
    projects.forEach((p) => {
      if (p.aspect_ratio in counts) {
        counts[p.aspect_ratio as "9:16" | "16:9" | "1:1"]++;
      }
    });
    return counts;
  }, [projects]);

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => api.createProject(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setIsCreateOpen(false);
      setName("");
      setDescription("");
      setPrimaryProductionMode("knowledge");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setProjectToDelete(null);
    },
  });

  const handleCreate = (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    const profile = primaryProductionMode === "knowledge"
      ? { knowledge_profile: {} }
      : primaryProductionMode === "commerce"
        ? { commerce_profile: {} }
        : { drama_profile: { series_title: name }, drama_style_guide: {} };
    createMutation.mutate({ name, description, aspect_ratio: aspectRatio, mode: primaryProductionMode, ...profile });
  };

  const requestDelete = (project: { id: string; name: string }) => setProjectToDelete(project);

  return (
    <PageContainer width="wide" className="space-y-6">
      <PageHeader
        title="项目库"
        description="管理短视频项目、画布规格与默认排版模板。"
        actions={(
          <>
            <div className="inline-flex items-center rounded-xl glass-pill p-1 shadow-xs" role="group" aria-label="项目显示方式">
              <button
                type="button"
                aria-label="网格视图"
                aria-pressed={viewMode === "grid"}
                onClick={() => setViewMode("grid")}
                className={`inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-all cursor-pointer ${
                  viewMode === "grid" ? "bg-card text-foreground shadow-xs font-medium" : "hover:text-foreground hover:bg-card/40"
                }`}
              >
                <LayoutGrid aria-hidden="true" className="h-4 w-4" />
              </button>
              <button
                type="button"
                aria-label="列表视图"
                aria-pressed={viewMode === "list"}
                onClick={() => setViewMode("list")}
                className={`inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-all cursor-pointer ${
                  viewMode === "list" ? "bg-card text-foreground shadow-xs font-medium" : "hover:text-foreground hover:bg-card/40"
                }`}
              >
                <List aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>
            <Button onClick={() => setIsCreateOpen(true)} className="gap-1.5 h-9 px-3.5 text-sm shadow-xs">
              <Plus aria-hidden="true" className="h-4 w-4" />
              新建项目
            </Button>
          </>
        )}
      />

      {/* Search & Filter Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="inline-flex h-9 items-center justify-start gap-1 rounded-lg glass-pill p-1 text-muted-foreground overflow-x-auto no-scrollbar shadow-xs" role="tablist" aria-label="按画幅筛选">
          {[
            { id: "all", label: "全部画幅", count: countsByAspect.all },
            { id: "9:16", label: "竖屏 9:16", count: countsByAspect["9:16"] },
            { id: "16:9", label: "横屏 16:9", count: countsByAspect["16:9"] },
            { id: "1:1", label: "正方形 1:1", count: countsByAspect["1:1"] },
          ].map((chip) => {
            const isActive = aspectFilter === chip.id;
            return (
              <button
                key={chip.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setAspectFilter(chip.id)}
                className={`inline-flex h-7 px-3 items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-xs sm:text-sm font-medium cursor-pointer transition-all duration-150 ease-out select-none ${
                  isActive
                    ? "bg-card text-foreground shadow-xs font-semibold border border-border/80"
                    : "text-muted-foreground hover:text-foreground hover:bg-card/40"
                }`}
              >
                <span>{chip.label}</span>
                <span className={`text-xs font-mono tabular-nums ${isActive ? "text-foreground/85 font-semibold" : "opacity-60"}`}>
                  ({chip.count})
                </span>
              </button>
            );
          })}
        </div>

        <div className="w-full sm:w-72">
          <SearchInput
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onClear={() => setSearchQuery("")}
            placeholder="搜索项目名称或简介…"
            className="h-9 text-sm"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
          {[1, 2, 3, 4].map((item) => <div key={item} className="h-52 animate-pulse rounded-xl border border-border/60 bg-card/40" />)}
        </div>
      ) : projects.length === 0 ? (
        <EmptyState icon={FolderKanban} title="暂无项目" description="点击上方“新建项目”开始构建您的第一个短视频空间。" />
      ) : filteredProjects.length === 0 ? (
        <EmptyState
          icon={FolderKanban}
          title="未找到匹配的项目"
          description="尝试更改搜索关键词或画幅筛选条件。"
          action={(
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSearchQuery("");
                setAspectFilter("all");
              }}
              className="h-8 text-xs sm:text-sm"
            >
              清除筛选
            </Button>
          )}
        />
      ) : viewMode === "grid" ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
          {filteredProjects.map((project) => (
            <Card key={project.id} className="group flex flex-col justify-between hover:border-primary/40 transition-colors duration-200">
              <CardHeader className="p-4 sm:p-5 pb-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <span className="rounded-md border border-primary/20 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                      {PRODUCTION_MODE_SPECS[project.mode].label}
                    </span>
                    <span className="rounded-md border border-border/80 bg-secondary/80 px-2 py-0.5 font-mono text-xs font-medium text-foreground shadow-xs">
                      {project.aspect_ratio}
                    </span>
                  </div>
                  <IconButton
                    label={`删除项目 ${project.name}`}
                    variant="ghost"
                    className="h-7 w-7 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 rounded-lg"
                    onClick={() => requestDelete(project)}
                  >
                    <Trash2 aria-hidden="true" className="h-4 w-4" />
                  </IconButton>
                </div>
                <CardTitle className="mt-2.5 truncate text-base font-semibold group-hover:text-primary transition-colors">
                  <Link href={`/projects/${project.id}`} className="hover:underline">
                    {project.name}
                  </Link>
                </CardTitle>
                <CardDescription className="line-clamp-2 text-xs sm:text-sm leading-relaxed mt-1 text-muted-foreground">
                  {project.description || "暂无项目说明"}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 border-t border-border/50 p-4 sm:p-5 py-3 text-xs sm:text-sm text-muted-foreground">
                <div className="flex justify-between items-center gap-3">
                  <span>模板风格</span>
                  <span className="truncate font-medium text-foreground">系列默认设置</span>
                </div>
                <div className="flex justify-between items-center gap-3">
                  <span>更新日期</span>
                  <span className="font-mono text-xs tabular-nums text-foreground/80">{formatDate(project.updated_at)}</span>
                </div>
              </CardContent>
              <CardFooter className="p-4 sm:p-5 pt-0">
                <Link href={`/projects/${project.id}`} className="w-full">
                  <Button variant="outline" className="w-full justify-between group/btn h-9 text-sm">
                    <span>进入工作空间</span>
                    <ArrowRight aria-hidden="true" className="h-4 w-4 transition-transform duration-150 group-hover/btn:translate-x-0.5" />
                  </Button>
                </Link>
              </CardFooter>
            </Card>
          ))}
        </div>
      ) : (
        <div className="divide-y divide-border/60 overflow-hidden rounded-xl glass-card">
          {filteredProjects.map((project) => (
            <div key={project.id} className="flex items-center justify-between gap-4 p-4 sm:px-5 transition-colors hover:bg-secondary/40">
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-center gap-2.5">
                  <span className="rounded-md border border-primary/20 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                    {PRODUCTION_MODE_SPECS[project.mode].label}
                  </span>
                  <span className="rounded-md border border-border/80 bg-secondary/80 px-2 py-0.5 font-mono text-xs font-medium text-foreground shadow-xs">
                    {project.aspect_ratio}
                  </span>
                  <Link href={`/projects/${project.id}`} className="truncate text-sm sm:text-base font-semibold text-foreground hover:text-primary transition-colors">
                    {project.name}
                  </Link>
                </div>
                <p className="truncate text-xs sm:text-sm text-muted-foreground">{project.description || "暂无项目说明"}</p>
              </div>
              <div className="flex shrink-0 items-center gap-3 text-sm text-muted-foreground">
                <span className="hidden lg:inline font-medium text-foreground/80">系列工作区</span>
                <span className="hidden sm:inline font-mono text-xs tabular-nums text-foreground/70">{formatDate(project.updated_at)}</span>
                <Link href={`/projects/${project.id}`}>
                  <Button size="sm" variant="outline" className="gap-1.5 h-8 text-xs sm:text-sm">
                    进入
                    <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
                  </Button>
                </Link>
                <IconButton
                  label={`删除项目 ${project.name}`}
                  variant="ghost"
                  className="h-8 w-8 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 rounded-lg"
                  onClick={() => requestDelete(project)}
                >
                  <Trash2 aria-hidden="true" className="h-4 w-4" />
                </IconButton>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modern Project Creation Modal with Visual Aspect Selectors */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen} className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-base sm:text-lg font-semibold">新建项目</DialogTitle>
          <DialogDescription>定义项目名称与画布比例，作为视频创作与排版预设的容器。</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleCreate} className="space-y-4 pt-1">
          <ProductionModeSelector value={primaryProductionMode} onChange={setPrimaryProductionMode} />

          <Field label="项目名称" htmlFor="project-name" required>
            <Input
              id="project-name"
              placeholder="例如：每日科技前沿 / 历史悬案档案"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="h-10 text-sm"
              required
            />
          </Field>
          
          <fieldset className="space-y-1.5">
            <legend className="block text-sm font-medium text-foreground">画幅比例</legend>
            <div className="grid grid-cols-3 gap-2.5" role="group" aria-label="画幅比例">
              {[
                { label: "竖屏 9:16", value: "9:16", desc: "抖音 · 视频号", aspectClass: "w-3.5 h-6" },
                { label: "横屏 16:9", value: "16:9", desc: "B 站 · YouTube", aspectClass: "w-6 h-3.5" },
                { label: "正方形 1:1", value: "1:1", desc: "小红书 · 图文", aspectClass: "w-4.5 h-4.5" },
              ].map((ratio) => (
                <button
                  type="button"
                  key={ratio.value}
                  aria-pressed={aspectRatio === ratio.value}
                  onClick={() => setAspectRatio(ratio.value)}
                  className={`flex flex-col items-center justify-between rounded-xl border p-3.5 text-center transition-all cursor-pointer shadow-xs ${
                    aspectRatio === ratio.value
                      ? "border-primary/60 bg-primary/10 text-primary ring-1 ring-primary/40 shadow-xs"
                      : "border-border/80 bg-card/60 text-muted-foreground hover:bg-secondary/70 hover:text-foreground"
                  }`}
                >
                  <div className={`rounded-sm border border-current my-1.5 ${ratio.aspectClass}`} />
                  <span className="block text-xs sm:text-sm font-semibold text-foreground">{ratio.label}</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">{ratio.desc}</span>
                </button>
              ))}
            </div>
          </fieldset>

          <Field label="项目描述" htmlFor="project-description" description="可选">
            <Textarea
              id="project-description"
              placeholder="简述该项目的主题或受众风格（可选）"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              className="text-sm"
            />
          </Field>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setIsCreateOpen(false)} disabled={createMutation.isPending} className="h-9 text-sm">
              取消
            </Button>
            <Button type="submit" disabled={createMutation.isPending || !name.trim()} className="h-9 text-sm">
              {createMutation.isPending ? "创建中…" : "确认创建"}
            </Button>
          </DialogFooter>
        </form>
      </Dialog>

      <ConfirmDialog
        open={Boolean(projectToDelete)}
        onOpenChange={(open) => !open && setProjectToDelete(null)}
        title="删除项目？"
        description={projectToDelete ? `删除项目“${projectToDelete.name}”后，其包含的所有视频任务与分镜将被彻底移除。` : undefined}
        confirmLabel="确认删除"
        variant="destructive"
        onConfirm={async () => {
          if (projectToDelete) await deleteMutation.mutateAsync(projectToDelete.id);
        }}
      />
    </PageContainer>
  );
}
