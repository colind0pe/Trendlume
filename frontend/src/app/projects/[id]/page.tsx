"use client";
import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Plus,
  Film,
  Image as ImageIcon,
  Trash2,
  Save,
  Copy,
  ArrowRight,
  Volume2,
  Check,
  RefreshCw,
  Flame,
  Clapperboard,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { TASK_REFRESH_EVENTS, useTaskEvents, type TaskEvent } from "@/lib/use-task-events";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ProductionTaskDialog } from "@/components/projects/production-task-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/field";
import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import { PageContainer, PageHeader, SectionHeader } from "@/components/ui/page-shell";
import { StatusBadge } from "@/components/ui/status-badge";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toast";
import {
  ASSET_TYPE_LABELS,
  TEMPLATE_TYPE_LABELS,
  TASK_STATUS_LABELS,
  getTaskStatusTone,
  isTaskActive,
  formatTemplateName,
  formatParamLabel,
  PRODUCTION_MODE_SPECS,
} from "@/lib/ui-constants";
import {
  ProjectTemplateUpdate,
  TemplateCatalogItem,
} from "@/lib/types";
const canonicalTemplateId = (id?: string | null) =>
  id || "image_gallery_matted";
const assetFileUrl = (filePath: string) =>
  `/api/v1/assets/files/${filePath.split("/").map(encodeURIComponent).join("/")}`;
export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const projectId = params.id as string;
  const [activeTab, setActiveTab] = React.useState("tasks");
  const [isCreateTaskOpen, setIsCreateTaskOpen] = React.useState(false);
  const [selectedTemplateId, setSelectedTemplateId] = React.useState("image_gallery_matted");
  const [templateParams, setTemplateParams] = React.useState<Record<string, any>>({});
  const [templateFilter, setTemplateFilter] = React.useState<"all" | "image" | "video" | "static">("all");
  const [templatePreviewUrl, setTemplatePreviewUrl] = React.useState<string | null>(null);
  const [taskToDelete, setTaskToDelete] = React.useState<{ id: string; title: string } | null>(null);
  const [taskStatusFilter, setTaskStatusFilter] = React.useState<string>("all");
  const { toast } = useToast();
  // Queries
  const { data: taskVoices = [], isLoading: isVoicesLoading, isError: isVoicesError, refetch: refetchVoices } = useQuery({
    queryKey: ["voices", "active"],
    queryFn: () => api.listVoices(true),
    enabled: isCreateTaskOpen,
  });
  const { data: project, isLoading: isProjectLoading } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
  });
  const { data: publishingAccounts = [] } = useQuery({
    queryKey: ["publishing-accounts"],
    queryFn: () => api.listAccounts("douyin"),
  });
  const publishableAccounts = publishingAccounts.filter(
    (account) => account.status === "active" && Boolean(account.credential_id),
  );
  const { data: template } = useQuery({
    queryKey: ["project-template", projectId],
    queryFn: () => api.getProjectTemplate(projectId),
  });
  const { data: tasks = [], isLoading: isTasksLoading } = useQuery({
    queryKey: ["project-tasks", projectId],
    queryFn: () => api.listProjectTasks(projectId),
    refetchInterval: (query) => {
      const currentTasks = (query.state.data as Array<{ status?: string; active_job?: { status?: string } | null }> | undefined) || [];
      return currentTasks.some(isTaskActive) ? 2000 : false;
    },
  });
  const filteredProjectTasks = React.useMemo(() => {
    return tasks.filter((task) => {
      if (taskStatusFilter === "all") return true;
      if (taskStatusFilter === "running") return isTaskActive(task);
      if (taskStatusFilter === "completed") return task.status === "completed";
      if (taskStatusFilter === "failed") return task.status === "failed";
      if (taskStatusFilter === "draft") return task.status === "draft" || task.status === "pending";
      return task.status === taskStatusFilter;
    });
  }, [tasks, taskStatusFilter]);
  const taskCounts = React.useMemo(() => ({
    all: tasks.length,
    running: tasks.filter(isTaskActive).length,
    completed: tasks.filter((t) => t.status === "completed").length,
    failed: tasks.filter((t) => t.status === "failed").length,
  }), [tasks]);
  const { data: assets = [] } = useQuery({
    queryKey: ["project-assets", projectId],
    queryFn: () => api.listAssets(projectId),
  });
  const { data: projectBgm = [] } = useQuery({
    queryKey: ["project-bgm", projectId],
    queryFn: () => api.getProjectBgm(projectId),
  });
  const { data: workflows = [] } = useQuery({
    queryKey: ["comfyui-workflows"],
    queryFn: () => api.listComfyUIWorkflows(),
  });
  const { data: templates = [] } = useQuery<TemplateCatalogItem[]>({
    queryKey: ["template-catalog"],
    queryFn: () => api.listTemplates(),
  });
  const projectTaskIdsRef = React.useRef(new Set<string>());
  React.useEffect(() => {
    projectTaskIdsRef.current = new Set(tasks.map((task) => task.id));
  }, [tasks]);
  const refreshProjectTaskQueries = React.useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["project-tasks", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project", projectId] });
  }, [projectId, queryClient]);
  const handleProjectTaskEvent = React.useCallback(
    (event: TaskEvent) => {
      if (!event.data?.task_id || !projectTaskIdsRef.current.has(event.data.task_id)) return;
      if (event.event === "asset.created") {
        queryClient.invalidateQueries({ queryKey: ["project-assets", projectId] });
        return;
      }
      if (TASK_REFRESH_EVENTS.has(event.event)) {
        refreshProjectTaskQueries();
      }
    },
    [projectId, queryClient, refreshProjectTaskQueries]
  );
  useTaskEvents({
    onEvent: handleProjectTaskEvent,
    onReconnect: refreshProjectTaskQueries,
  });
  // Template Form State
  const [templateForm, setTemplateForm] = React.useState<ProjectTemplateUpdate>({});
  React.useEffect(() => {
    if (template) {
      setTemplateForm({
        name: template.name,
        aspect_ratio: template.aspect_ratio,
        style_preset: template.style_preset,
        font_family: template.font_family,
        primary_color: template.primary_color,
        background_color: template.background_color,
        layout_type: template.layout_type,
        frame_template: template.frame_template,
        custom_css: template.custom_css,
        template_id: template.template_id,
        template_version: template.template_version,
        params: template.params,
      });
      setSelectedTemplateId(canonicalTemplateId(template.template_id));
      setTemplateParams(template.params || {});
    }
  }, [template]);
  React.useEffect(() => {
    const selected = templates.find((item) => item.id === selectedTemplateId);
    if (selected && !Object.keys(templateParams).length) {
      setTemplateParams(selected.default_params || {});
    }
  }, [selectedTemplateId, templates, templateParams]);
  // Mutations
  const updateTemplateMutation = useMutation({
    mutationFn: (data: ProjectTemplateUpdate) => api.updateProjectTemplate(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-template", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      toast("模板配置已保存。", "success");
    },
  });
  const updateProjectBgmMutation = useMutation({
    mutationFn: (assetId: string | null) => api.updateProject(projectId, { bgm_asset_id: assetId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      toast("项目默认背景音乐已保存。", "success");
    },
  });
  const templatePreviewMutation = useMutation({
    mutationFn: (templateId: string) =>
      api.previewTemplate(templateId, {
        title: templateParams.title || "",
        text: "AI 短视频模板预览",
        params: templateParams,
      }),
    onSuccess: (preview) => setTemplatePreviewUrl(preview.preview_url),
  });
  const deleteTaskMutation = useMutation({
    mutationFn: (taskId: string) => api.deleteTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-tasks", projectId] });
    },
  });
  const duplicateTaskMutation = useMutation({
    mutationFn: (taskId: string) => api.duplicateTask(taskId),
    onSuccess: (copy) => {
      queryClient.invalidateQueries({ queryKey: ["project-tasks", projectId] });
      router.push(`/projects/${projectId}/tasks/${copy.id}`);
    },
  });
  const [aspectScope, setAspectScope] = React.useState<"project" | "all">("project");
  const projectAspect = project?.aspect_ratio || "9:16";
  const filteredTemplates = templates.filter((item) => {
    const matchesType = templateFilter === "all" || item.template_type === templateFilter;
    const matchesAspect =
      aspectScope === "all" ||
      item.aspect_ratio === projectAspect ||
      (!item.aspect_ratio && projectAspect === "9:16");
    return matchesType && matchesAspect;
  });
  const handleSaveTemplate = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const selected = templates.find((item) => item.id === selectedTemplateId);
    updateTemplateMutation.mutate({
      ...templateForm,
      template_id: selectedTemplateId || undefined,
      template_version: selected?.version || templateForm.template_version,
      frame_template: selected?.html_path || templateForm.frame_template,
      name: selected?.name || templateForm.name,
      params: templateParams,
    });
  };
  if (isProjectLoading) {
    return <PageContainer className="space-y-4"><div className="h-24 animate-pulse rounded-lg border border-border bg-card" /></PageContainer>;
  }
  if (!project) {
    return <PageContainer><EmptyState title="项目不存在或已被删除" /></PageContainer>;
  }
  const isKnowledgeProject = project.primary_production_mode === "knowledge";
  const isDramaProject = project.primary_production_mode === "drama";
  return (
    <PageContainer width="wide" className="space-y-6">
      <PageHeader
        back={(
          <Link href="/projects" className="mb-1 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors group">
            <ArrowLeft aria-hidden="true" className="h-4 w-4 transition-transform duration-150 group-hover:-translate-x-0.5" />
            <span>返回项目库</span>
          </Link>
        )}
        title={(
          <span className="flex items-center gap-2.5">
            <span>{project.name}</span>
            <span className="rounded-md border border-primary/20 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              {PRODUCTION_MODE_SPECS[project.primary_production_mode].label}
            </span>
            <span className="rounded-md border border-border/80 bg-secondary/80 px-2 py-0.5 font-mono text-xs font-medium text-foreground shadow-xs">
              {project.aspect_ratio}
            </span>
          </span>
        )}
        description={project.description || "短视频创作项目空间"}
        actions={(
          <>
            {isKnowledgeProject && <Button variant="outline" onClick={() => router.push(`/trends?project=${encodeURIComponent(project.id)}`)} className="gap-1.5 h-9 px-3.5 text-sm">
              <Flame aria-hidden="true" className="h-4 w-4" />
              查看热点
            </Button>}
            {isDramaProject && (
              <Link href={`/projects/${project.id}/drama`}>
                <Button className="gap-1.5 h-9 px-3.5 text-sm shadow-xs">
                  <Clapperboard aria-hidden="true" className="h-4 w-4" />
                  进入 Drama workspace
                </Button>
              </Link>
            )}
            <Button variant={isDramaProject ? "outline" : "default"} onClick={() => setIsCreateTaskOpen(true)} className="gap-1.5 h-9 px-3.5 text-sm shadow-xs">
              <Plus aria-hidden="true" className="h-4 w-4" />
              {isDramaProject ? "新建其他模式 Task" : "新建 Production Task"}
            </Button>
          </>
        )}
      />
      {/* Workspace Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList aria-label="项目工作区" className="w-full sm:w-auto h-10 p-1 glass-pill">
          <TabsTrigger value="tasks" className="text-sm px-3.5 py-1.5">
            视频任务 ({tasks.length})
          </TabsTrigger>
          <TabsTrigger value="template" className="text-sm px-3.5 py-1.5">
            排版模板 ({templates.length})
          </TabsTrigger>
          <TabsTrigger value="assets" className="text-sm px-3.5 py-1.5">
            项目素材 ({assets.length})
          </TabsTrigger>
        </TabsList>
        {/* Tab 1: Video Tasks */}
        <TabsContent value="tasks" className="space-y-4">
          <SectionHeader
            title="视频任务"
            description="管理该项目下的分镜脚本、生成流水线与成片导出。"
            actions={(
              <div className="inline-flex h-9 items-center justify-start gap-1 rounded-lg glass-pill p-1 text-muted-foreground overflow-x-auto no-scrollbar shadow-xs" role="tablist" aria-label="按任务状态筛选">
                {[
                  { id: "all", label: "全部", count: taskCounts.all },
                  { id: "running", label: "运行中", count: taskCounts.running },
                  { id: "completed", label: "已完成", count: taskCounts.completed },
                  { id: "failed", label: "失败", count: taskCounts.failed },
                ].map((chip) => {
                  const isActive = taskStatusFilter === chip.id;
                  return (
                    <button
                      key={chip.id}
                      type="button"
                      role="tab"
                      aria-selected={isActive}
                      onClick={() => setTaskStatusFilter(chip.id)}
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
            )}
          />
          {isTasksLoading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
              {[1, 2].map((i) => (
                <div key={i} className="h-40 rounded-xl border border-border/60 bg-card/40 animate-pulse" />
              ))}
            </div>
          ) : tasks.length === 0 ? (
          <EmptyState
            icon={project.primary_production_mode === "drama" ? Clapperboard : Film}
            title={project.primary_production_mode === "drama" ? "Drama 项目尚未开始前期制片" : "该项目下暂无视频任务"}
            description={project.primary_production_mode === "drama" ? "进入 Drama workspace，从故事想法或已有剧本开始，完成 Approved Storyboard。" : "点击右上角的“制作视频”开始整理主题、来源和分镜。"}
            action={project.primary_production_mode === "drama" ? <Link href={`/projects/${project.id}/drama`}><Button variant="outline">打开 Drama workspace</Button></Link> : undefined}
          />
          ) : filteredProjectTasks.length === 0 ? (
            <EmptyState
              icon={Film}
              title="未找到该状态下的视频任务"
              description="尝试切换上方任务状态筛选条件。"
              action={(
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setTaskStatusFilter("all")}
                  className="h-8 text-xs sm:text-sm"
                >
                  查看全部任务
                </Button>
              )}
            />
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filteredProjectTasks.map((task) => (
                <Card
                  key={task.id}
                  className="group flex flex-col justify-between hover:border-primary/40 transition-colors duration-200"
                >
                  <CardHeader className="p-4 sm:p-5 pb-3">
                    <div className="flex items-start justify-between gap-2">
                      <StatusBadge label={TASK_STATUS_LABELS[task.status] || task.status} tone={getTaskStatusTone(task.status)} />
                      <IconButton
                        label={`删除任务 ${task.title}`}
                        variant="ghost"
                        className="h-7 w-7 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 rounded-lg"
                        onClick={() => setTaskToDelete({ id: task.id, title: task.title })}
                      >
                        <Trash2 aria-hidden="true" className="h-4 w-4" />
                      </IconButton>
                    </div>
                    <CardTitle className="text-base font-semibold truncate mt-2 group-hover:text-primary transition-colors">
                      {task.title}
                    </CardTitle>
                    <CardDescription className="line-clamp-2 text-xs sm:text-sm leading-relaxed mt-1 text-muted-foreground">
                      {task.description || "暂无任务说明"}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="px-4 sm:px-5 py-3 border-t border-border/50 space-y-2.5 text-sm text-muted-foreground">
                    {isTaskActive(task) && (
                      <div className="space-y-1.5 rounded-lg border border-primary/20 bg-primary/5 p-2.5">
                        <div className="flex justify-between text-xs font-mono">
                          <span className="text-foreground font-medium">{task.current_stage_label || task.current_stage || task.active_job?.current_stage || "排队中"}</span>
                          <span className="font-semibold text-primary">{task.active_job?.progress ?? task.progress_percentage}%</span>
                        </div>
                        <Progress value={task.active_job?.progress ?? task.progress_percentage} className="h-1.5" />
                      </div>
                    )}
                    <div className="flex items-center justify-between text-sm">
                      <span>分镜数量</span>
                      <span className="font-mono font-medium text-foreground">{task.scenes_count || 0} 个镜头</span>
                    </div>
                  </CardContent>
                  <CardFooter className="p-4 sm:p-5 pt-0">
                    <div className="flex w-full gap-2">
                      <Link href={`/projects/${projectId}/tasks/${task.id}`} className="flex-1">
                        <Button variant="outline" className="w-full justify-between group/btn h-9 text-sm">
                          <span>编辑分镜与脚本</span>
                          <ArrowRight className="h-4 w-4 transition-transform duration-150 group-hover/btn:translate-x-0.5" />
                        </Button>
                      </Link>
                      <IconButton
                        title="复制任务设置与脚本"
                        label="复制任务设置与脚本"
                        variant="outline"
                        className="h-9 w-9"
                        disabled={duplicateTaskMutation.isPending}
                        onClick={() => duplicateTaskMutation.mutate(task.id)}
                      >
                        <Copy aria-hidden="true" className="h-4 w-4" />
                      </IconButton>
                    </div>
                  </CardFooter>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
        {/* Tab 2: Template Configuration */}
        <TabsContent value="template" className="space-y-6">
          <SectionHeader
            title="排版模板"
            description="设定项目默认排版模板，规范成片视觉结构与字幕版式。"
            actions={(
              <div className="flex flex-wrap items-center gap-2">
                <Tabs
                  value={templateFilter}
                  onValueChange={(value) => setTemplateFilter(value as typeof templateFilter)}
                  className="space-y-0"
                >
                  <TabsList aria-label="模板类型筛选" className="h-9 p-1">
                    {[
                      ["all", `全部 (${templates.filter((t) => aspectScope === "all" || t.aspect_ratio === projectAspect || (!t.aspect_ratio && projectAspect === "9:16")).length})`],
                      ["image", `图片 (${templates.filter((t) => t.template_type === "image" && (aspectScope === "all" || t.aspect_ratio === projectAspect || (!t.aspect_ratio && projectAspect === "9:16"))).length})`],
                      ["video", `视频 (${templates.filter((t) => t.template_type === "video" && (aspectScope === "all" || t.aspect_ratio === projectAspect || (!t.aspect_ratio && projectAspect === "9:16"))).length})`],
                      ["static", `文字 (${templates.filter((t) => t.template_type === "static" && (aspectScope === "all" || t.aspect_ratio === projectAspect || (!t.aspect_ratio && projectAspect === "9:16"))).length})`],
                    ].map(([value, label]) => (
                      <TabsTrigger key={value} value={value} className="px-3 text-xs">
                        {label}
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>
                <div className="inline-flex h-9 items-center justify-start gap-1 rounded-lg glass-pill p-1 text-muted-foreground shadow-xs" role="tablist" aria-label="画幅范围筛选">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={aspectScope === "project"}
                    onClick={() => setAspectScope("project")}
                    className={`inline-flex h-7 px-3 items-center justify-center whitespace-nowrap rounded-md text-xs font-medium cursor-pointer transition-all duration-150 ease-out select-none ${
                      aspectScope === "project"
                        ? "bg-card text-foreground shadow-xs font-semibold border border-border/80"
                        : "text-muted-foreground hover:text-foreground hover:bg-card/40"
                    }`}
                  >
                    本画幅 ({projectAspect})
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={aspectScope === "all"}
                    onClick={() => setAspectScope("all")}
                    className={`inline-flex h-7 px-3 items-center justify-center whitespace-nowrap rounded-md text-xs font-medium cursor-pointer transition-all duration-150 ease-out select-none ${
                      aspectScope === "all"
                        ? "bg-card text-foreground shadow-xs font-semibold border border-border/80"
                        : "text-muted-foreground hover:text-foreground hover:bg-card/40"
                    }`}
                  >
                    全部画幅
                  </button>
                </div>
              </div>
            )}
          />
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left: Template Catalog Gallery */}
            <div className="lg:col-span-7 xl:col-span-8 space-y-4">
              {templates.length === 0 ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-4">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} className="aspect-[9/16] rounded-xl border border-border/60 bg-card/60 animate-pulse" />
                  ))}
                </div>
              ) : filteredTemplates.length === 0 ? (
                <EmptyState title="未找到匹配的排版模板" description="可切换上方分类筛选查看其他模式的模板。" />
              ) : (
                <div className={`grid gap-4 ${
                  project.aspect_ratio === "16:9" && aspectScope === "project"
                    ? "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3"
                    : "grid-cols-2 sm:grid-cols-3 xl:grid-cols-4"
                }`}>
                  {filteredTemplates.map((item) => {
                    const isSelected = selectedTemplateId === item.id;
                    const isCurrentDefault = canonicalTemplateId(template?.template_id) === item.id;
                    const previewSrc = `/api/v1/templates/previews/${encodeURIComponent(item.id)}`;
                    const thumbAspectClass =
                      item.aspect_ratio === "16:9" || item.width > item.height
                        ? "aspect-[16/9]"
                        : item.aspect_ratio === "1:1" || item.width === item.height
                        ? "aspect-square"
                        : "aspect-[9/16]";
                    return (
                      <button
                        type="button"
                        key={item.id}
                        aria-pressed={isSelected}
                        aria-label={`选择模板 ${formatTemplateName(item.id, item.name)}`}
                        onClick={() => {
                          setSelectedTemplateId(item.id);
                          setTemplateParams(item.default_params || {});
                          setTemplatePreviewUrl(null);
                          setTemplateForm((current) => ({
                            ...current,
                            template_id: item.id,
                            template_version: item.version,
                            frame_template: item.html_path,
                            name: item.name,
                          }));
                        }}
                        className={`group relative text-left rounded-2xl glass-card overflow-hidden transition-all duration-200 cursor-pointer flex flex-col ${
                          isSelected
                            ? "border-primary ring-2 ring-primary/40 bg-primary/[0.06]"
                            : "hover:border-primary/40"
                        }`}
                      >
                        {/* Multi-Aspect Thumbnail */}
                        <div className={`${thumbAspectClass} w-full bg-secondary/30 relative overflow-hidden`}>
                          <img
                            src={previewSrc}
                            alt={`${formatTemplateName(item.id, item.name)} 预览`}
                            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-103"
                            loading="lazy"
                          />
                          {/* Badges on preview */}
                          <div className="absolute top-2.5 left-2.5 flex flex-col gap-1 items-start">
                            <Badge className="backdrop-blur-md bg-background/85 text-xs border-border/60" variant="secondary">
                              {TEMPLATE_TYPE_LABELS[item.template_type] || item.template_type}
                            </Badge>
                            {isCurrentDefault && (
                              <Badge className="backdrop-blur-md bg-success/20 text-success border-success/40 text-xs" variant="success">
                                当前默认
                              </Badge>
                            )}
                          </div>
                          {/* Selected Checkmark Badge */}
                          {isSelected && (
                            <div className="absolute top-2.5 right-2.5 w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-md animate-in zoom-in-75 duration-150">
                              <Check className="h-3.5 w-3.5 stroke-[2.5]" />
                            </div>
                          )}
                        </div>
                        {/* Title & Format Specs */}
                        <div className="p-3 border-t border-border/50 flex-1 flex flex-col justify-between">
                          <p className="text-sm font-semibold text-foreground truncate group-hover:text-primary transition-colors">
                            {formatTemplateName(item.id, item.name)}
                          </p>
                          <p className="text-xs text-muted-foreground font-mono truncate mt-1">
                            {item.width}×{item.height} · {item.template_type === "image" ? (item.aspect_ratio === "16:9" ? "横屏排版" : item.aspect_ratio === "1:1" ? "方正排版" : "画廊视窗") : item.template_type === "video" ? (item.aspect_ratio === "16:9" ? "横屏动态视窗" : item.aspect_ratio === "1:1" ? "方正动态视窗" : "全景动态视窗") : "纯文字版式"}
                          </p>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            {/* Right: Selected Template Inspector & Parameters */}
            <div className="lg:col-span-5 xl:col-span-4 sticky top-6">
              {(() => {
                const activeTpl = templates.find((item) => item.id === selectedTemplateId) || templates[0];
                const previewSrc = activeTpl
                  ? `/api/v1/templates/previews/${encodeURIComponent(activeTpl.id)}`
                  : "";
                const isCurrentDefault = canonicalTemplateId(template?.template_id) === activeTpl?.id;
                const inspectorAspectClass =
                  activeTpl?.aspect_ratio === "16:9"
                    ? "aspect-[16/9] max-w-[340px]"
                    : activeTpl?.aspect_ratio === "1:1"
                    ? "aspect-square max-w-[280px]"
                    : "aspect-[9/16] max-w-[240px]";
                if (!activeTpl) {
                  return (
                    <Card className="rounded-2xl glass-card p-6 text-center text-xs text-muted-foreground">
                      请选择排版模板查看详情
                    </Card>
                  );
                }
                return (
                  <Card className="rounded-2xl glass-card">
                    <CardHeader className="p-4 sm:p-5 pb-3">
                      <div className="flex items-center justify-between gap-2">
                        <CardTitle className="text-base font-semibold truncate">
                          {formatTemplateName(activeTpl.id, activeTpl.name)}
                        </CardTitle>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <Badge variant="outline" className="text-xs">
                            {TEMPLATE_TYPE_LABELS[activeTpl.template_type] || activeTpl.template_type}
                          </Badge>
                          {isCurrentDefault && (
                            <Badge variant="success" className="text-xs">
                              当前默认
                            </Badge>
                          )}
                        </div>
                      </div>
                      <CardDescription className="text-xs text-muted-foreground mt-1 line-clamp-2">
                        规范视听版式结构与字幕排印，呈现专业数字工坊质感。
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="p-4 sm:p-5 pt-0 space-y-4">
                      {/* Live / Static Preview Frame */}
                      <div className={`relative ${inspectorAspectClass} mx-auto rounded-xl overflow-hidden border border-border/80 bg-secondary/30 shadow-inner group`}>
                        <img
                          src={templatePreviewUrl || previewSrc}
                          alt={`${formatTemplateName(activeTpl.id, activeTpl.name)} 效果预览`}
                          className="h-full w-full object-cover"
                        />
                        <div className="absolute inset-x-0 bottom-0 p-2 bg-gradient-to-t from-background/90 via-background/60 to-transparent flex justify-center">
                          <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            className="h-7 text-xs gap-1.5 backdrop-blur-md shadow-xs"
                            disabled={templatePreviewMutation.isPending || !selectedTemplateId}
                            onClick={() => templatePreviewMutation.mutate(selectedTemplateId)}
                          >
                            <RefreshCw className={`h-3 w-3 ${templatePreviewMutation.isPending ? "animate-spin" : ""}`} />
                            {templatePreviewMutation.isPending ? "渲染中…" : "实时渲染预览"}
                          </Button>
                        </div>
                      </div>
                      {/* Parameter Schema Configuration */}
                      {activeTpl.parameter_schema && activeTpl.parameter_schema.length > 0 && (
                        <div className="rounded-xl glass-pill p-3.5 space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-foreground">模板个性化参数</span>
                            <span className="text-xs text-muted-foreground font-mono">留空则自动隐藏对应元素</span>
                          </div>
                          <div className="space-y-2.5">
                            {activeTpl.parameter_schema.map((parameter) => {
                              let placeholder = "留空则不展示";
                              if (parameter.name === "author") placeholder = "例如: @创作者 (留空自动隐藏)";
                              else if (parameter.name === "describe") placeholder = "例如: 数字化视听工坊 (留空自动隐藏)";
                              else if (parameter.name === "brand") placeholder = "例如: Trendlume (留空自动隐藏)";
                              else if (parameter.default) placeholder = `默认: ${parameter.default}`;
                              return (
                                <div key={parameter.name} className="space-y-1">
                                  <label
                                    htmlFor={`tpl-param-${parameter.name}`}
                                    className="text-xs font-medium text-foreground flex items-center justify-between"
                                  >
                                    <span>{formatParamLabel(parameter.name, parameter.label)}</span>
                                  </label>
                                  <Input
                                    id={`tpl-param-${parameter.name}`}
                                    value={String(templateParams[parameter.name] ?? "")}
                                    onChange={(e) =>
                                      setTemplateParams((current) => ({
                                        ...current,
                                        [parameter.name]: e.target.value,
                                      }))
                                    }
                                    placeholder={placeholder}
                                    className="h-8 text-xs"
                                  />
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </CardContent>
                    <CardFooter className="p-4 sm:p-5 pt-0 border-t border-border/40 flex flex-col gap-2">
                      <Button
                        type="button"
                        onClick={() => handleSaveTemplate()}
                        disabled={updateTemplateMutation.isPending || !selectedTemplateId}
                        className="w-full h-9 gap-1.5 text-xs font-medium"
                      >
                        <Save className="h-3.5 w-3.5" />
                        {updateTemplateMutation.isPending ? "正在保存…" : "保存为项目默认模板"}
                      </Button>
                      <p className="text-xs text-muted-foreground text-center">
                        保存后，此项目下新建及重渲染的分镜将默认套用此模板。
                      </p>
                    </CardFooter>
                  </Card>
                );
              })()}
            </div>
          </div>
        </TabsContent>
        {/* Tab 4: Assets */}
        <TabsContent value="assets" className="space-y-4">
          <SectionHeader
            title="项目素材"
            description="项目专属的图片、视频与背景音乐资产。"
            actions={(
              <Link href="/assets">
                <Button variant="outline" className="h-9 px-3.5 text-sm">前往素材库上传</Button>
              </Link>
            )}
          />
          <Card>
            <CardHeader className="p-4 sm:p-5 pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Volume2 className="h-4 w-4 text-primary" /> 背景音乐设置
              </CardTitle>
              <CardDescription className="text-sm mt-0.5">设定该项目下视频任务默认引用的音频资产。</CardDescription>
            </CardHeader>
            <CardContent className="p-4 sm:p-5 pt-0 flex flex-col sm:flex-row gap-3 sm:items-end">
              <div className="flex-1 space-y-1.5">
                <label htmlFor="project-default-bgm" className="text-sm font-medium text-foreground">默认背景音乐</label>
                <Select
                  id="project-default-bgm"
                  value={project.bgm_asset_id || ""}
                  className="h-9 text-sm"
                  onChange={(e) => updateProjectBgmMutation.mutate(e.target.value || null)}
                  disabled={updateProjectBgmMutation.isPending || !projectBgm.length}
                >
                  <option value="">不设置项目默认背景音乐</option>
                  {projectBgm.map((asset) => (
                    <option key={asset.id} value={asset.id}>
                      {asset.file_name}{asset.project_id ? "（项目素材）" : "（系统内置）"}
                    </option>
                  ))}
                </Select>
              </div>
              {projectBgm.find((asset) => asset.id === project.bgm_asset_id) && (
                <audio
                  controls
                  preload="none"
                  className="h-9 max-w-full"
                  src={assetFileUrl(projectBgm.find((asset) => asset.id === project.bgm_asset_id)!.file_path)}
                />
              )}
            </CardContent>
          </Card>
          {assets.length === 0 ? (
            <EmptyState icon={ImageIcon} title="暂无项目素材" description="上传或生成素材后，会在这里统一查看。" />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3.5">
              {assets.map((asset) => (
                <Card key={asset.id} className="overflow-hidden group hover:border-primary/40 transition-colors duration-200 rounded-2xl">
                  <div className="h-32 bg-secondary/50 flex items-center justify-center relative overflow-hidden">
                    <ImageIcon className="h-7 w-7 text-muted-foreground/50" />
                    <Badge className="absolute bottom-2 left-2 text-xs" variant="secondary">
                      {ASSET_TYPE_LABELS[asset.asset_type] || asset.asset_type}
                    </Badge>
                  </div>
                  <div className="p-2.5">
                    <p className="text-sm font-medium truncate text-foreground" title={asset.file_name}>{asset.file_name}</p>
                    <p className="mt-1 text-xs text-muted-foreground font-mono">
                      {(asset.file_size_bytes / 1024).toFixed(1)} KB
                    </p>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
      {/* Two-Column Studio Task Creation Modal */}
      {project && (
        <ProductionTaskDialog
          open={isCreateTaskOpen}
          onOpenChange={setIsCreateTaskOpen}
          projectId={projectId}
          project={project}
          templates={templates}
          assets={assets}
          projectBgm={projectBgm}
          workflows={workflows}
          publishableAccounts={publishableAccounts}
          taskVoices={taskVoices}
          isVoicesLoading={isVoicesLoading}
          isVoicesError={isVoicesError}
          refetchVoices={refetchVoices}
          canonicalTemplateId={canonicalTemplateId}
        />
      )}
      <ConfirmDialog
        open={Boolean(taskToDelete)}
        onOpenChange={(open) => !open && setTaskToDelete(null)}
        title="删除任务？"
        description={taskToDelete ? `删除“${taskToDelete.title}”后，任务及其分镜数据将被移除。` : undefined}
        confirmLabel="删除任务"
        variant="destructive"
        onConfirm={async () => {
          if (taskToDelete) await deleteTaskMutation.mutateAsync(taskToDelete.id);
        }}
      />
    </PageContainer>
  );
}
