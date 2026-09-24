"use client";

import * as React from "react";
import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Download,
  ExternalLink,
  FileText,
  Film,
  ImageIcon,
  Layers3,
  Loader2,
  MoveDown,
  MoveUp,
  Play,
  Plus,
  RotateCcw,
  Save,
  Send,
  Share2,
  Sliders,
  Sparkles,
  StopCircle,
  Trash2,
  Volume2,
} from "lucide-react";
import { api } from "@/lib/api-client";
import type {
  Asset,
  PlatformMetadata,
  SceneCreate,
  SocialAccount,
  TaskDetail,
  VisualRole,
  WorkflowArtifact,
  WorkflowJob,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/field";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { VISUAL_ROLE_OPTIONS } from "@/lib/ui-constants";

const ACTIVE = new Set(["queued", "retrying", "running"]);
const FAILED = new Set(["failed", "cancelled"]);

const jobLabel = (status: string) =>
  ({
    queued: "排队中",
    retrying: "等待重试",
    running: "生成中",
    completed: "已完成",
    succeeded: "已完成",
    failed: "生成失败",
    cancelled: "已取消",
  }[status] || status);

const stageLabel = (stage?: string | null) =>
  ({
    topic: "主题确认",
    research: "资料核验",
    planning: "内容规划",
    script: "脚本生成",
    storyboard: "分镜设计",
    assets: "画面生成",
    voice: "旁白配音",
    subtitles: "字幕制作",
    composition: "视频合成",
    export: "成片导出",
  }[stage || ""] || stage || "准备中");

const strategyLabel = (strategy?: string) =>
  ({
    static_card: "信息卡片",
    text_to_image: "AI 配图",
    image_to_image: "参考生图",
    text_to_video: "AI 视频",
    image_to_video: "图生视频",
    online_asset: "在线素材",
    uploaded_asset: "我的素材",
  }[strategy || ""] || "自动规划");

export interface KnowledgeStoryboardProps {
  projectId: string;
  task: TaskDetail;
  job: WorkflowJob | null;
  jobs: WorkflowJob[];
  selectedJobId: string | null;
  onSelectJobId: (id: string) => void;
  sceneDrafts: SceneCreate[];
  onUpdateScene: (index: number, changes: Partial<SceneCreate>) => void;
  onMoveScene: (index: number, direction: -1 | 1) => void;
  onAddScene: () => void;
  onDeleteScene: (index: number) => void;
  title: string;
  onTitleChange: (val: string) => void;
  detail: Record<string, unknown> & { type: "knowledge" | "commerce" | "drama" };
  onDetailChange: (val: Record<string, unknown> & { type: "knowledge" | "commerce" | "drama" }) => void;
  description: string;
  onDescriptionChange: (val: string) => void;
  storyboardDirty: boolean;
  contentDirty: boolean;
  onSaveAll: () => Promise<void>;
  isSaving: boolean;
  hasActiveJob: boolean;
  readiness?: {
    ready: boolean;
    checks: Array<{ key: string; label: string; status: string; message: string }>;
  };
  onStartProduction: () => Promise<void>;
  isStartingProduction: boolean;
  onRetryJob: (jobId: string) => void;
  onCancelJob: (jobId: string) => void;
  onRunSceneAction: (sceneId: string, kind: "voice" | "visual") => Promise<void>;
  sceneAction: { sceneId: string; kind: "voice" | "visual" } | null;
  projectAssets: Asset[];
  accounts: SocialAccount[];
  onPublish: (
    job: WorkflowJob,
    artifact: WorkflowArtifact,
    data: {
      accountId: string;
      scheduledAt: string | null;
      title: string;
      description: string;
      tags: string[];
      coverAssetId: string | null;
    }
  ) => Promise<void>;
  isPublishing: boolean;
  onRegenerateMetadata?: () => void;
  isRegeneratingMetadata?: boolean;
}

export function KnowledgeStoryboard({
  projectId,
  task,
  job,
  jobs,
  selectedJobId,
  onSelectJobId,
  sceneDrafts,
  onUpdateScene,
  onMoveScene,
  onAddScene,
  onDeleteScene,
  title,
  onTitleChange,
  detail,
  onDetailChange,
  description,
  onDescriptionChange,
  storyboardDirty,
  contentDirty,
  onSaveAll,
  isSaving,
  hasActiveJob,
  readiness,
  onStartProduction,
  isStartingProduction,
  onRetryJob,
  onCancelJob,
  onRunSceneAction,
  sceneAction,
  projectAssets,
  accounts,
  onPublish,
  isPublishing,
  onRegenerateMetadata,
  isRegeneratingMetadata,
}: KnowledgeStoryboardProps) {
  const [sceneToDelete, setSceneToDelete] = React.useState<number | null>(null);
  const [showSettingsDrawer, setShowSettingsDrawer] = React.useState(false);
  const [expandedAdvancedScenes, setExpandedAdvancedScenes] = React.useState<Record<number, boolean>>({});
  const [publishAccountId, setPublishAccountId] = React.useState("");
  const [publishMode, setPublishMode] = React.useState<"now" | "schedule">("now");
  const [publishScheduledAt, setPublishScheduledAt] = React.useState("");
  const [publishCoverAssetId, setPublishCoverAssetId] = React.useState("");
  const [pubTitle, setPubTitle] = React.useState("");
  const [pubDesc, setPubDesc] = React.useState("");
  const [pubTags, setPubTags] = React.useState("");
  const [isMetadataPanelOpen, setIsMetadataPanelOpen] = React.useState(false);
  const [videoMeta, setVideoMeta] = React.useState<{
    width: number;
    height: number;
    duration: number;
  } | null>(null);

  const resolvedAspect = React.useMemo(() => {
    if (videoMeta?.width && videoMeta?.height) {
      const ratio = videoMeta.width / videoMeta.height;
      if (ratio > 1.25) return "16:9";
      if (ratio < 0.8) return "9:16";
      return "1:1";
    }
    const taskAspect = String(
      task.generation_settings?.aspect_ratio ||
      task.detail?.aspect_ratio ||
      "9:16"
    );
    if (taskAspect.includes("16:9")) return "16:9";
    if (taskAspect.includes("1:1")) return "1:1";
    return "9:16";
  }, [videoMeta, task]);

  const metadata = React.useMemo(() => {
    return (
      task.generation_settings?.metadata ||
      task.publishing_settings?.metadata ||
      (task as any).input_payload?.metadata ||
      {}
    ) as PlatformMetadata;
  }, [task]);

  const totalDuration = sceneDrafts.reduce((sum, s) => sum + Number(s.duration_seconds || 0), 0);
  const totalWords = sceneDrafts.reduce((sum, s) => sum + (s.narration_text?.trim()?.length || 0), 0);

  const coverAssets = React.useMemo(() => {
    return projectAssets.filter((a) => a.asset_type === "image");
  }, [projectAssets]);

  React.useEffect(() => {
    setPubTitle(metadata.title || task.title || title || "");
    setPubDesc(metadata.description ?? task.description ?? description ?? "");
    setPubTags(
      Array.isArray(metadata.tags) && metadata.tags.length > 0
        ? metadata.tags.slice(0, 5).join(", ")
        : "AI科普, 知识分享, Trendlume"
    );
  }, [metadata.title, metadata.description, metadata.tags, task.title, task.description, title, description]);
  const isDirty = storyboardDirty || contentDirty;
  const contentMode = String(task.generation_settings?.content_mode || "generated_image");
  const usesVisualPrompt = contentMode === "generated_image" || contentMode === "generated_video";
  const finalVideo = job?.artifacts?.find((artifact) => artifact.kind === "final_video");
  const hasFinalVideo = Boolean(job && finalVideo && ["completed", "succeeded"].includes(job.status));

  const toggleAdvanced = (index: number) => {
    setExpandedAdvancedScenes((prev) => ({ ...prev, [index]: !prev[index] }));
  };

  // 10 阶段流水线追踪（对齐后端 ProductionWorkflow 契约与 commit 3eee0436~1）
  const PIPELINE_STAGES = [
    { key: "topic", label: "主题", fullName: "主题确认" },
    { key: "research", label: "研究", fullName: "资料核验" },
    { key: "planning", label: "策划", fullName: "内容规划" },
    { key: "script", label: "脚本", fullName: "脚本生成" },
    { key: "storyboard", label: "分镜", fullName: "分镜设计" },
    { key: "assets", label: "素材", fullName: "画面生成" },
    { key: "voice", label: "配音", fullName: "旁白配音" },
    { key: "subtitles", label: "字幕", fullName: "字幕制作" },
    { key: "composition", label: "合成", fullName: "视频合成" },
    { key: "export", label: "成片", fullName: "成片导出" },
  ] as const;

  const currentStageKey = (job?.current_stage || "").toLowerCase();
  const currentStageIndex = PIPELINE_STAGES.findIndex(
    (step) => step.key === currentStageKey
  );

  return (
    <div className="space-y-6">
      {/* 1. 顶部紧凑操作栏 */}
      <header className="flex flex-col gap-4 rounded-xl border border-border bg-card/70 p-4 shadow-sm backdrop-blur-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 flex-wrap items-center gap-3">
          <Link
            href={`/projects/${projectId}`}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-xs font-medium text-muted-foreground transition hover:bg-secondary hover:text-foreground"
            onClick={(e) => {
              if (isDirty && !window.confirm("故事板有未保存修改，确定离开吗？")) {
                e.preventDefault();
              }
            }}
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            返回项目
          </Link>

          <div className="flex min-w-[200px] flex-1 items-center gap-2">
            <Input
              value={title}
              onChange={(e) => onTitleChange(e.target.value)}
              placeholder="视频标题"
              className="h-9 font-semibold text-foreground md:text-base"
            />
          </div>

          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1 rounded-md bg-secondary/80 px-2 py-1 font-medium text-foreground">
              <Layers3 className="h-3.5 w-3.5 text-primary" />
              {sceneDrafts.length} 镜
            </span>
            <span className="inline-flex items-center gap-1 rounded-md bg-secondary/80 px-2 py-1 font-medium text-foreground">
              <FileText className="h-3.5 w-3.5 text-muted-foreground" />
              {totalWords} 字
            </span>
            <span className="inline-flex items-center gap-1 rounded-md bg-secondary/80 px-2 py-1 font-medium text-foreground">
              <Clock3 className="h-3.5 w-3.5 text-muted-foreground" />
              约 {Math.round(totalDuration)} 秒
            </span>
            {readiness?.ready ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-1 font-medium text-emerald-600 dark:text-emerald-400">
                <Check className="h-3.5 w-3.5" />
                就绪
              </span>
            ) : (
              <span
                className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-1 font-medium text-amber-600 dark:text-amber-400"
                title={readiness?.checks?.filter((c) => c.status !== "pass").map((c) => c.message).join("；")}
              >
                <AlertTriangle className="h-3.5 w-3.5" />
                待核对
              </span>
            )}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 gap-1 px-2 text-xs text-muted-foreground"
              onClick={() => setShowSettingsDrawer(!showSettingsDrawer)}
            >
              <Sliders className="h-3.5 w-3.5" />
              主题设定
              <ChevronDown className={`h-3 w-3 transition-transform ${showSettingsDrawer ? "rotate-180" : ""}`} />
            </Button>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* 保存按钮 */}
          <Button
            size="sm"
            variant={isDirty ? "default" : "outline"}
            onClick={onSaveAll}
            disabled={!isDirty || isSaving || hasActiveJob}
            className="h-9 gap-1.5"
          >
            {isSaving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : isDirty ? (
              <Save className="h-3.5 w-3.5" />
            ) : (
              <Check className="h-3.5 w-3.5 text-emerald-500" />
            )}
            {isSaving ? "保存中" : isDirty ? "保存修改" : "已保存"}
          </Button>

          {/* 一键生成 CTA 按钮 */}
          {hasActiveJob ? (
            <Button size="sm" variant="secondary" disabled className="h-9 gap-1.5 font-medium">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
              正在生成 ({job?.progress ?? 0}%)
            </Button>
          ) : (
            <Button
              size="sm"
              className="h-9 gap-1.5 font-medium shadow-sm"
              disabled={isStartingProduction || (!readiness?.ready && task.editorial_status === "approved")}
              onClick={onStartProduction}
            >
              {isStartingProduction ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5 fill-current" />
              )}
              {job && ["completed", "succeeded"].includes(job.status)
                ? "重新生成视频"
                : "开始生成视频"}
            </Button>
          )}
        </div>
      </header>

      {/* 可折叠的内容与主题设置 */}
      {showSettingsDrawer && (
        <Card className="border-border/80 bg-card/60">
          <CardContent className="grid gap-4 p-4 md:grid-cols-2">
            <label className="space-y-1.5 text-xs font-medium">
              <span>知识主题</span>
              <Input
                value={String(detail.topic || "")}
                onChange={(e) => onDetailChange({ ...detail, topic: e.target.value })}
                placeholder="这条视频要讲清楚什么？"
                className="h-9 text-sm"
              />
            </label>
            <label className="space-y-1.5 text-xs font-medium">
              <span>创作备注（可选）</span>
              <Input
                value={description}
                onChange={(e) => onDescriptionChange(e.target.value)}
                placeholder="记录制作意图或需要特别注意的内容"
                className="h-9 text-sm"
              />
            </label>
          </CardContent>
        </Card>
      )}

      {/* 2. 成片展示与发布工作台（成片完成时置顶呈现） */}
      {hasFinalVideo && finalVideo && job && (
        <Card className="overflow-hidden border-emerald-500/30 bg-gradient-to-br from-emerald-500/5 via-card to-card shadow-sm">
          <div className="flex flex-col gap-6 p-5 lg:flex-row lg:items-start">
            {/* 左侧：成片视频播放器与交付规格 (根据画幅自适应，消除多余空白) */}
            {resolvedAspect === "16:9" ? (
              <div className="flex flex-col space-y-3 w-full max-w-[480px] lg:w-[440px] xl:w-[480px] lg:flex-shrink-0 mx-auto lg:mx-0">
                <div className="relative aspect-video w-full overflow-hidden rounded-lg border border-border bg-black shadow-inner flex items-center justify-center">
                  <video
                    src={api.workflowArtifactUrl(job.id, finalVideo.id)}
                    controls
                    onLoadedMetadata={(e) => {
                      const v = e.currentTarget;
                      if (v.videoWidth && v.videoHeight) {
                        setVideoMeta({
                          width: v.videoWidth,
                          height: v.videoHeight,
                          duration: v.duration,
                        });
                      }
                    }}
                    className="h-full w-full object-contain"
                    poster={
                      publishCoverAssetId
                        ? `/api/v1/assets/${publishCoverAssetId}/file`
                        : task.scenes?.[0]?.media_asset_id
                        ? `/api/v1/assets/${task.scenes[0].media_asset_id}/file`
                        : undefined
                    }
                  />
                </div>
                {/* 16:9 横屏规格与操作区，填补底部空白 */}
                <div className="space-y-2.5 rounded-lg border border-border/60 bg-background/50 p-3 text-xs">
                  <div className="flex items-center justify-between text-muted-foreground">
                    <span className="font-medium text-foreground">成片规格</span>
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {videoMeta ? `${videoMeta.width}×${videoMeta.height}` : "1920×1080"} · 16:9 横屏
                    </Badge>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center text-[11px] text-muted-foreground">
                    <div className="rounded border border-border/40 bg-card/60 py-1.5">
                      <div className="text-[10px] opacity-75">视频时长</div>
                      <div className="font-semibold text-foreground">
                        {videoMeta?.duration ? `${Math.round(videoMeta.duration)}s` : `${totalDuration}s`}
                      </div>
                    </div>
                    <div className="rounded border border-border/40 bg-card/60 py-1.5">
                      <div className="text-[10px] opacity-75">分镜镜头</div>
                      <div className="font-semibold text-foreground">{sceneDrafts.length} 镜</div>
                    </div>
                    <div className="rounded border border-border/40 bg-card/60 py-1.5">
                      <div className="text-[10px] opacity-75">编码格式</div>
                      <div className="font-semibold text-foreground">H.264 / MP4</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 pt-0.5">
                    <a
                      href={api.workflowArtifactUrl(job.id, finalVideo.id)}
                      download={`${pubTitle || title || "trendlume_video"}.mp4`}
                      className="inline-flex h-8 flex-1 items-center justify-center gap-1.5 rounded-md border border-border bg-background px-3 text-xs font-medium text-foreground shadow-sm transition hover:bg-secondary"
                    >
                      <Download className="h-3.5 w-3.5" />
                      下载成片 MP4
                    </a>
                    <a
                      href={api.workflowArtifactUrl(job.id, finalVideo.id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex h-8 items-center justify-center gap-1 rounded-md border border-border bg-background px-2.5 text-xs text-muted-foreground shadow-sm hover:text-foreground"
                      title="新窗口全屏预览"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                      新窗口
                    </a>
                  </div>
                </div>
              </div>
            ) : resolvedAspect === "1:1" ? (
              <div className="flex flex-col space-y-3 w-full max-w-[340px] lg:w-[340px] lg:flex-shrink-0 mx-auto lg:mx-0">
                <div className="relative aspect-square w-full overflow-hidden rounded-lg border border-border bg-black shadow-inner flex items-center justify-center">
                  <video
                    src={api.workflowArtifactUrl(job.id, finalVideo.id)}
                    controls
                    onLoadedMetadata={(e) => {
                      const v = e.currentTarget;
                      if (v.videoWidth && v.videoHeight) {
                        setVideoMeta({
                          width: v.videoWidth,
                          height: v.videoHeight,
                          duration: v.duration,
                        });
                      }
                    }}
                    className="h-full w-full object-contain"
                    poster={
                      publishCoverAssetId
                        ? `/api/v1/assets/${publishCoverAssetId}/file`
                        : task.scenes?.[0]?.media_asset_id
                        ? `/api/v1/assets/${task.scenes[0].media_asset_id}/file`
                        : undefined
                    }
                  />
                </div>
                <div className="flex w-full flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <a
                      href={api.workflowArtifactUrl(job.id, finalVideo.id)}
                      download={`${pubTitle || title || "trendlume_video"}.mp4`}
                      className="inline-flex h-8 flex-1 items-center justify-center gap-1.5 rounded-md border border-border bg-background px-3 text-xs font-medium text-foreground shadow-sm transition hover:bg-secondary"
                    >
                      <Download className="h-3.5 w-3.5" />
                      下载成片 MP4
                    </a>
                    <a
                      href={api.workflowArtifactUrl(job.id, finalVideo.id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex h-8 items-center justify-center gap-1 rounded-md border border-border bg-background px-2.5 text-xs text-muted-foreground shadow-sm hover:text-foreground"
                      title="新窗口全屏预览"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  </div>
                  <div className="flex items-center justify-between px-1 text-[11px] text-muted-foreground">
                    <span>{videoMeta ? `${videoMeta.width}×${videoMeta.height}` : "1080×1080"} · 1:1 方形</span>
                    <span>{videoMeta?.duration ? `${Math.round(videoMeta.duration)}s` : `${totalDuration}s`} · MP4</span>
                  </div>
                </div>
              </div>
            ) : (
              /* 9:16 竖屏（短视频主流）：完整竖屏呈现，高度自然充满卡片，下方无多余空白 */
              <div className="flex flex-col items-center space-y-3 w-full max-w-[270px] sm:max-w-[280px] lg:w-[280px] lg:flex-shrink-0 mx-auto lg:mx-0">
                <div className="relative aspect-[9/16] w-full max-h-[480px] overflow-hidden rounded-lg border border-border bg-black shadow-inner flex items-center justify-center">
                  <video
                    src={api.workflowArtifactUrl(job.id, finalVideo.id)}
                    controls
                    onLoadedMetadata={(e) => {
                      const v = e.currentTarget;
                      if (v.videoWidth && v.videoHeight) {
                        setVideoMeta({
                          width: v.videoWidth,
                          height: v.videoHeight,
                          duration: v.duration,
                        });
                      }
                    }}
                    className="h-full w-full object-contain"
                    poster={
                      publishCoverAssetId
                        ? `/api/v1/assets/${publishCoverAssetId}/file`
                        : task.scenes?.[0]?.media_asset_id
                        ? `/api/v1/assets/${task.scenes[0].media_asset_id}/file`
                        : undefined
                    }
                  />
                </div>
                <div className="flex w-full flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <a
                      href={api.workflowArtifactUrl(job.id, finalVideo.id)}
                      download={`${pubTitle || title || "trendlume_video"}.mp4`}
                      className="inline-flex h-8 flex-1 items-center justify-center gap-1.5 rounded-md border border-border bg-background px-3 text-xs font-medium text-foreground shadow-sm transition hover:bg-secondary"
                    >
                      <Download className="h-3.5 w-3.5" />
                      下载成片 MP4
                    </a>
                    <a
                      href={api.workflowArtifactUrl(job.id, finalVideo.id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex h-8 items-center justify-center gap-1 rounded-md border border-border bg-background px-2.5 text-xs text-muted-foreground shadow-sm hover:text-foreground"
                      title="新窗口全屏预览"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  </div>
                  <div className="flex items-center justify-between px-1 text-[11px] text-muted-foreground">
                    <span>{videoMeta ? `${videoMeta.width}×${videoMeta.height}` : "1080×1920"} · 9:16 竖屏</span>
                    <span>{videoMeta?.duration ? `${Math.round(videoMeta.duration)}s` : `${totalDuration}s`} · MP4</span>
                  </div>
                </div>
              </div>
            )}

            {/* 右侧：一体化成片交付与发布控制台 (收敛展示与编辑) */}
            <div className="flex flex-1 flex-col space-y-3">
              {/* 顶部标题与 AI 重新生成 */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2.5">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 className="h-4 w-4" />
                  </span>
                  <h2 className="text-base font-semibold text-foreground">成片生成就绪</h2>
                  <Badge variant="outline" className="border-emerald-500/30 text-emerald-600 dark:text-emerald-400">
                    100% 合成完毕
                  </Badge>
                  <Badge variant="secondary" className="text-xs">
                    抖音发布
                  </Badge>
                </div>
                {onRegenerateMetadata && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={hasActiveJob || isRegeneratingMetadata}
                    onClick={onRegenerateMetadata}
                    className="h-7 gap-1.5 px-2.5 text-xs text-muted-foreground hover:text-foreground"
                    title="AI 根据视频旁白重新提炼爆款标题、描述和话题"
                  >
                    {isRegeneratingMetadata ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Sparkles className="h-3.5 w-3.5 text-amber-500" />
                    )}
                    AI 重新生成文案
                  </Button>
                )}
              </div>

              {/* 统一发布表单：参数与文案合一，无冗余卡片 */}
              <div className="space-y-3 rounded-lg border border-border/70 bg-background/60 p-3">
                {/* 基础参数：账号、封面、发布方式 */}
                <div className="grid gap-2.5 sm:grid-cols-3">
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground block mb-1">发布账号</label>
                    <Select
                      value={publishAccountId}
                      onChange={(e) => setPublishAccountId(e.target.value)}
                      className="h-8 text-xs"
                    >
                      <option value="">选择抖音账号</option>
                      {accounts
                        .filter((account) => account.status === "active")
                        .map((account) => (
                          <option key={account.id} value={account.id}>
                            {account.account_name}
                          </option>
                        ))}
                    </Select>
                  </div>

                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground block mb-1">视频封面</label>
                    <Select
                      value={publishCoverAssetId}
                      onChange={(e) => setPublishCoverAssetId(e.target.value)}
                      className="h-8 text-xs"
                    >
                      <option value="">使用视频默认封面</option>
                      {coverAssets.map((asset) => (
                        <option key={asset.id} value={asset.id}>
                          {asset.file_name || `素材 ${asset.id.slice(0, 6)}`}
                        </option>
                      ))}
                    </Select>
                  </div>

                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground block mb-1">发布方式</label>
                    <Select
                      value={publishMode}
                      onChange={(e) => setPublishMode(e.target.value as "now" | "schedule")}
                      className="h-8 text-xs"
                    >
                      <option value="now">立即发布</option>
                      <option value="schedule">定时发布</option>
                    </Select>
                  </div>
                </div>

                {/* 定时发布时间输入 */}
                {publishMode === "schedule" && (
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground block mb-1">计划发布时间</label>
                    <Input
                      type="datetime-local"
                      value={publishScheduledAt}
                      min={new Date(Date.now() + 60_000).toISOString().slice(0, 16)}
                      onChange={(e) => setPublishScheduledAt(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                )}

                {/* 发布标题 */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] font-medium text-muted-foreground">发布标题</label>
                    <span className="text-[10px] text-muted-foreground font-mono">{pubTitle.length}/30</span>
                  </div>
                  <Input
                    value={pubTitle}
                    maxLength={30}
                    onChange={(e) => setPubTitle(e.target.value)}
                    placeholder="视频发布标题（30字以内）"
                    className="h-8 text-xs font-medium"
                  />
                </div>

                {/* 视频文案描述 */}
                <div>
                  <label className="text-[11px] font-medium text-muted-foreground block mb-1">视频文案描述</label>
                  <Textarea
                    value={pubDesc}
                    onChange={(e) => setPubDesc(e.target.value)}
                    placeholder="发布描述与文案..."
                    rows={2}
                    className="text-xs resize-none"
                  />
                </div>

                {/* 话题标签与预览 */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] font-medium text-muted-foreground">话题标签</label>
                    <span className="text-[10px] text-muted-foreground">以逗号或空格分隔</span>
                  </div>
                  <Input
                    value={pubTags}
                    onChange={(e) => setPubTags(e.target.value)}
                    placeholder="话题标签（最多5个），例如：AI短视频, 科技科普"
                    className="h-8 text-xs"
                  />
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {pubTags
                      .split(/[,，\s]+/)
                      .map((t) => t.trim())
                      .filter(Boolean)
                      .slice(0, 5)
                      .map((tag) => (
                        <Badge key={tag} variant="secondary" className="px-1.5 py-0 text-[11px] font-normal">
                          #{tag}
                        </Badge>
                      ))}
                    {metadata.declaration && (
                      <span className="text-[11px] text-muted-foreground ml-1">
                        · 内容声明：{metadata.declaration}
                      </span>
                    )}
                  </div>
                </div>

                {/* 底部发布提交按钮 */}
                <div className="flex items-center justify-between border-t border-border/40 pt-2.5">
                  <span className="text-[11px] text-muted-foreground">
                    将自动同步至已绑定的抖音创作者平台
                  </span>
                  <Button
                    size="sm"
                    disabled={
                      !publishAccountId ||
                      isPublishing ||
                      (publishMode === "schedule" && !publishScheduledAt) ||
                      !pubTitle.trim()
                    }
                    onClick={() => {
                      const tagsArray = pubTags
                        .split(/[,，\s]+/)
                        .map((t) => t.trim())
                        .filter(Boolean)
                        .slice(0, 5);
                      onPublish(job, finalVideo, {
                        accountId: publishAccountId,
                        scheduledAt: publishMode === "schedule" && publishScheduledAt ? publishScheduledAt : null,
                        title: pubTitle.trim(),
                        description: pubDesc.trim(),
                        tags: tagsArray,
                        coverAssetId: publishCoverAssetId || null,
                      });
                    }}
                    className="h-8 gap-1.5 px-4 text-xs font-medium"
                  >
                    {isPublishing ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Send className="h-3.5 w-3.5" />
                    )}
                    {publishMode === "schedule" ? "确认定时发布" : "立即发布到抖音"}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* 3. 全局生成进度流水线（任务运行时或失败时呈现） */}
      {job && (hasActiveJob || FAILED.has(job.status)) && (
        <Card className={`overflow-hidden border ${FAILED.has(job.status) ? "border-destructive/40 bg-destructive/5" : "border-primary/30 bg-card/60"}`}>
          <div className="space-y-4 p-4 sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                {hasActiveJob ? (
                  <Loader2 className="h-5 w-5 animate-spin text-primary" />
                ) : (
                  <AlertCircle className="h-5 w-5 text-destructive" />
                )}
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    {hasActiveJob ? `正在生成视频 · ${stageLabel(job.current_stage)}` : "生成中断或遇到错误"}
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    {hasActiveJob
                      ? `生产整体进度 ${job.progress}% · 分镜卡片将随渲染进度实时刷新`
                      : job.error_message || "任务已暂停，请排查原因后重试"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {hasActiveJob && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onCancelJob(job.id)}
                    className="h-8 gap-1.5 text-xs hover:bg-destructive/10 hover:text-destructive"
                  >
                    <StopCircle className="h-3.5 w-3.5" />
                    停止生成
                  </Button>
                )}
                {FAILED.has(job.status) && (
                  <Button
                    size="sm"
                    variant="default"
                    onClick={() => onRetryJob(job.id)}
                    className="h-8 gap-1.5 text-xs"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    重试生成
                  </Button>
                )}
              </div>
            </div>

            {/* 总体进度条 */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>流水线进度</span>
                <span className="font-mono font-medium text-foreground">{job.progress}%</span>
              </div>
              <Progress value={job.progress} className="h-2" />
            </div>

            {/* 十阶段线性步骤进度指示器（对齐后端 ProductionWorkflow 契约与 commit 3eee0436~1） */}
            <div className="grid grid-cols-5 gap-y-3 gap-x-1 sm:grid-cols-10 pt-1">
              {PIPELINE_STAGES.map((step, idx) => {
                const stageRuns = (job.stages || []).filter((s) => s.step_key === step.key);
                const hasFailed = stageRuns.some((s) => s.status === "failed");
                const isCurrent = currentStageKey === step.key && hasActiveJob;
                const isPassed =
                  job.status === "completed" ||
                  (job.status as string) === "succeeded" ||
                  stageRuns.some((s) => s.status === "completed" || s.status === "reused") ||
                  (currentStageIndex > -1 && idx < currentStageIndex);

                return (
                  <div key={step.key} className="flex flex-col items-center text-center">
                    <div
                      className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                        hasFailed
                          ? "bg-destructive text-white"
                          : isPassed
                          ? "bg-emerald-500 text-white"
                          : isCurrent
                          ? "bg-primary text-primary-foreground ring-2 ring-primary/30"
                          : "bg-muted text-muted-foreground"
                      }`}
                      title={`${step.fullName} · 第 ${idx + 1}/10 阶段`}
                    >
                      {hasFailed ? (
                        <AlertCircle className="h-3.5 w-3.5" />
                      ) : isPassed ? (
                        <Check className="h-3.5 w-3.5" />
                      ) : isCurrent ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        idx + 1
                      )}
                    </div>
                    <span
                      className={`mt-1.5 text-[11px] font-medium leading-tight ${
                        hasFailed
                          ? "font-semibold text-destructive"
                          : isCurrent
                          ? "font-semibold text-primary"
                          : isPassed
                          ? "text-foreground"
                          : "text-muted-foreground"
                      }`}
                    >
                      {step.label}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </Card>
      )}

      {/* 3.5 平台发布文案与话题速览 (仅在成片尚未合成时呈现，合成后由顶部工作台统一接管) */}
      {!hasFinalVideo && (
        <Card className="overflow-hidden border-border/70 bg-card/60 shadow-sm backdrop-blur-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 p-3 sm:px-4">
          <div className="flex flex-wrap items-center gap-2">
            <Share2 className="h-4 w-4 text-primary" />
            <span className="text-xs font-semibold text-foreground">平台发布文案与话题</span>
            <Badge variant="outline" className="text-[10px] px-1.5 py-0 font-medium">
              {metadata.platform === "douyin" ? "抖音" : metadata.platform || "抖音"}
            </Badge>
            {metadata.declaration && (
              <span className="hidden text-[11px] text-muted-foreground sm:inline">
                · {metadata.declaration}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {onRegenerateMetadata && (
              <Button
                variant="outline"
                size="sm"
                disabled={hasActiveJob || isRegeneratingMetadata || isDirty}
                onClick={onRegenerateMetadata}
                className="h-7 gap-1.5 px-2.5 text-xs"
                title={isDirty ? "请先保存分镜修改" : "根据分镜旁白重新生成爆款标题、文案与话题"}
              >
                {isRegeneratingMetadata ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Sparkles className="h-3.5 w-3.5 text-amber-500" />
                )}
                {isRegeneratingMetadata ? "正在生成..." : "重新生成文案与话题"}
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsMetadataPanelOpen((prev) => !prev)}
              className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
              aria-label={isMetadataPanelOpen ? "收起发布信息" : "展开发布信息"}
            >
              {isMetadataPanelOpen ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>

        {isMetadataPanelOpen && (
          <div className="space-y-3 border-t border-border/50 bg-background/40 p-4 text-xs">
            <div>
              <div className="text-[11px] font-medium text-muted-foreground">推荐发布标题</div>
              <div className="mt-1 font-medium text-foreground">
                {metadata.title || pubTitle || "（暂未生成，可通过右上方按钮生成）"}
              </div>
            </div>

            {(metadata.description || pubDesc) && (
              <div>
                <div className="text-[11px] font-medium text-muted-foreground">视频文案描述</div>
                <p className="mt-1 leading-relaxed text-muted-foreground">
                  {metadata.description || pubDesc}
                </p>
              </div>
            )}

            <div>
              <div className="text-[11px] font-medium text-muted-foreground">推荐话题标签</div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {Array.isArray(metadata.tags) && metadata.tags.length > 0 ? (
                  metadata.tags.map((tag) => (
                    <Badge key={tag} variant="secondary" className="px-2 py-0.5 text-xs">
                      #{tag}
                    </Badge>
                  ))
                ) : (
                  <span className="text-muted-foreground">暂无标签推荐</span>
                )}
              </div>
            </div>

            {metadata.declaration && (
              <div className="text-[11px] text-muted-foreground">
                内容声明：{metadata.declaration}
              </div>
            )}
          </div>
        )}
        </Card>
      )}

      {/* 4. 主工作区：分镜故事板列表 */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
        <main className="space-y-4">
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2">
              <Film className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold text-foreground">分镜故事板</h2>
              <span className="text-xs text-muted-foreground">共 {sceneDrafts.length} 个镜头</span>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={onAddScene}
              disabled={hasActiveJob}
              className="h-8 gap-1 text-xs"
            >
              <Plus className="h-3.5 w-3.5" />
              添加镜头
            </Button>
          </div>

          {sceneDrafts.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border p-12 text-center">
              <Layers3 className="h-10 w-10 text-muted-foreground/40" />
              <p className="mt-3 text-sm font-medium text-foreground">故事板还没有镜头</p>
              <p className="mt-1 text-xs text-muted-foreground">
                点击上方“添加镜头”或开始生成，系统将根据知识主题自动规划分镜。
              </p>
              <Button size="sm" variant="outline" onClick={onAddScene} className="mt-4 gap-1.5">
                <Plus className="h-3.5 w-3.5" />
                创建第 1 个镜头
              </Button>
            </div>
          ) : (
            sceneDrafts.map((scene, index) => {
              const persisted = task.scenes?.[index];
              const sceneId = persisted?.id;

              // 精准判断当前分镜在 workflow job 中的各个 stage 执行状态
              const sceneStages = sceneId
                ? (job?.stages || []).filter((s) => s.unit_key === sceneId)
                : [];
              const voiceStage = sceneStages.find((s) => s.step_key === "voice");
              const assetStage = sceneStages.find((s) => s.step_key === "assets");
              const compStage = sceneStages.find((s) => s.step_key === "composition");

              const isVoiceActionRunning = sceneAction?.sceneId === sceneId && sceneAction.kind === "voice";
              const isVisualActionRunning = sceneAction?.sceneId === sceneId && sceneAction.kind === "visual";

              const isVoiceGenerating = isVoiceActionRunning || (hasActiveJob && voiceStage?.status === "running");
              const isAssetGenerating = isVisualActionRunning || (hasActiveJob && assetStage?.status === "running");
              const isSceneActiveInJob = isVoiceGenerating || isAssetGenerating || (hasActiveJob && compStage?.status === "running");

              const isVoiceSuccess = voiceStage?.status === "completed" || voiceStage?.status === "succeeded" || Boolean(scene.audio_asset_id);
              const isAssetSuccess = assetStage?.status === "completed" || assetStage?.status === "succeeded" || Boolean(scene.media_asset_id);
              const isFullyReady = isVoiceSuccess && isAssetSuccess;

              const plan = scene.production_metadata?.media_plan as { strategy?: string } | undefined;
              const mediaAsset = projectAssets.find((asset) => asset.id === scene.media_asset_id);
              const mediaIsVideo = mediaAsset?.asset_type === "video" || scene.layout_params?.media_type === "video";
              const isAdvancedExpanded = Boolean(expandedAdvancedScenes[index]);

              return (
                <article
                  key={persisted?.id || index}
                  className={`relative overflow-hidden rounded-xl border transition-all duration-200 ${
                    isSceneActiveInJob
                      ? "border-primary shadow-sm ring-1 ring-primary/40 bg-card/80"
                      : isFullyReady
                      ? "border-border/90 bg-card/60"
                      : "border-border/70 bg-card/40"
                  }`}
                >
                  {/* 卡片头部操作条 */}
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 bg-secondary/20 px-3.5 py-2.5">
                    <div className="flex items-center gap-2.5">
                      <span
                        className={`flex h-6 w-6 items-center justify-center rounded-md text-xs font-bold ${
                          isSceneActiveInJob
                            ? "bg-primary text-primary-foreground animate-pulse"
                            : isFullyReady
                            ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                            : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <h3 className="text-xs font-semibold text-foreground">镜头 {index + 1}</h3>

                      {/* 实时状态药丸 */}
                      {isSceneActiveInJob ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          {isVoiceGenerating ? "配音合成中" : isAssetGenerating ? "画面生成中" : "处理中"}
                        </span>
                      ) : isFullyReady ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                          <Check className="h-3 w-3" />
                          已就绪
                        </span>
                      ) : (
                        <span className="text-[11px] text-muted-foreground/80">待生成</span>
                      )}
                    </div>

                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1 font-mono text-[11px] text-muted-foreground">
                        <Clock3 className="h-3 w-3" />
                        {Number(scene.duration_seconds || 4).toFixed(1)}s
                      </span>
                      <div className="mx-1 h-3 w-px bg-border/60" />
                      <button
                        type="button"
                        onClick={() => onMoveScene(index, -1)}
                        disabled={index === 0 || hasActiveJob}
                        aria-label="上移镜头"
                        className="inline-flex h-7 w-7 items-center justify-center rounded hover:bg-secondary disabled:opacity-30"
                      >
                        <MoveUp className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => onMoveScene(index, 1)}
                        disabled={index === sceneDrafts.length - 1 || hasActiveJob}
                        aria-label="下移镜头"
                        className="inline-flex h-7 w-7 items-center justify-center rounded hover:bg-secondary disabled:opacity-30"
                      >
                        <MoveDown className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setSceneToDelete(index)}
                        disabled={sceneDrafts.length <= 1 || hasActiveJob}
                        aria-label="删除镜头"
                        className="inline-flex h-7 w-7 items-center justify-center rounded text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-30"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* 卡片主内容区 */}
                  <div className="grid gap-4 p-3.5 sm:p-4 md:grid-cols-[200px_minmax(0,1fr)]">
                    {/* 左侧：画面与音频组件 */}
                    <div className="flex flex-col gap-2.5">
                      {/* 画面视窗 */}
                      <div className="relative aspect-video w-full overflow-hidden rounded-lg border border-border bg-secondary/30">
                        {isAssetGenerating ? (
                          <div className="flex h-full w-full flex-col items-center justify-center bg-primary/5 p-2 text-center">
                            <Loader2 className="h-6 w-6 animate-spin text-primary" />
                            <span className="mt-1.5 text-[11px] font-medium text-primary">AI 画面绘制中…</span>
                          </div>
                        ) : scene.media_asset_id ? (
                          mediaIsVideo ? (
                            <video
                              src={`/api/v1/assets/${scene.media_asset_id}/file`}
                              controls
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <img
                              src={`/api/v1/assets/${scene.media_asset_id}/file`}
                              alt={`镜头 ${index + 1} 画面`}
                              className="h-full w-full object-cover"
                            />
                          )
                        ) : (
                          <div className="flex h-full w-full flex-col items-center justify-center p-2 text-center">
                            <ImageIcon className="h-6 w-6 text-muted-foreground/40" />
                            <span className="mt-1 text-[11px] text-muted-foreground">画面待生成</span>
                          </div>
                        )}
                        {plan?.strategy && (
                          <div className="absolute bottom-1 right-1">
                            <Badge variant="secondary" className="px-1.5 py-0 text-[10px] opacity-80 backdrop-blur-sm">
                              {strategyLabel(plan.strategy)}
                            </Badge>
                          </div>
                        )}
                      </div>

                      {/* 配音试听 */}
                      <div className="flex flex-col gap-1">
                        {isVoiceGenerating ? (
                          <div className="flex h-8 items-center justify-center gap-1.5 rounded-md border border-primary/20 bg-primary/5 text-xs text-primary">
                            <Loader2 className="h-3 w-3 animate-spin" />
                            <span>旁白配音合成中…</span>
                          </div>
                        ) : scene.audio_asset_id ? (
                          <audio
                            controls
                            preload="none"
                            src={`/api/v1/assets/${scene.audio_asset_id}/file`}
                            className="h-8 w-full"
                          />
                        ) : (
                          <div className="flex h-8 items-center justify-center rounded-md border border-dashed border-border/70 text-[11px] text-muted-foreground/60">
                            未生成旁白音频
                          </div>
                        )}
                      </div>

                      {/* 单镜局部生成快捷键 */}
                      {persisted && !hasActiveJob && (
                        <div className="grid grid-cols-2 gap-1.5 pt-0.5">
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 px-1.5 text-[11px]"
                            disabled={isVoiceGenerating || !scene.narration_text.trim()}
                            onClick={async () => {
                              if (isDirty) await onSaveAll();
                              await onRunSceneAction(persisted.id, "voice");
                            }}
                          >
                            {isVoiceGenerating ? (
                              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                            ) : (
                              <Volume2 className="mr-1 h-3 w-3 text-muted-foreground" />
                            )}
                            单镜配音
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 px-1.5 text-[11px]"
                            disabled={isAssetGenerating}
                            onClick={async () => {
                              if (isDirty) await onSaveAll();
                              await onRunSceneAction(persisted.id, "visual");
                            }}
                          >
                            {isAssetGenerating ? (
                              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                            ) : (
                              <RotateCcw className="mr-1 h-3 w-3 text-muted-foreground" />
                            )}
                            重画此镜
                          </Button>
                        </div>
                      )}
                    </div>

                    {/* 右侧：旁白文案与提示词主输入 */}
                    <div className="flex flex-col justify-between space-y-3">
                      <div className="space-y-3">
                        {/* 旁白文本 */}
                        <div className="space-y-1">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-medium text-foreground">旁白台词</span>
                            <span className="font-mono text-[11px] text-muted-foreground">
                              {scene.narration_text.length} 字
                            </span>
                          </div>
                          <Textarea
                            value={scene.narration_text}
                            onChange={(e) => onUpdateScene(index, { narration_text: e.target.value })}
                            rows={2}
                            placeholder="输入这个镜头要讲述的核心解说词…"
                            className="resize-none text-sm leading-relaxed"
                            disabled={hasActiveJob}
                          />
                        </div>

                        {/* 画面提示词 */}
                        <div className="space-y-1">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-medium text-foreground">
                              {usesVisualPrompt ? "画面描述 / 提示词" : "画面展现要求"}
                            </span>
                          </div>
                          <Textarea
                            value={scene.visual_prompt}
                            onChange={(e) => onUpdateScene(index, { visual_prompt: e.target.value })}
                            rows={2}
                            placeholder={
                              usesVisualPrompt
                                ? "描述画面的核心主体、场景环境、构图与光影…"
                                : "描述该画面要展示的信息…"
                            }
                            className="resize-none text-xs leading-relaxed text-muted-foreground focus:text-foreground"
                            disabled={hasActiveJob}
                          />
                        </div>
                      </div>

                      {/* 高级选项折叠条 */}
                      <div className="border-t border-border/50 pt-2">
                        <button
                          type="button"
                          onClick={() => toggleAdvanced(index)}
                          className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
                        >
                          <ChevronRight className={`h-3 w-3 transition-transform ${isAdvancedExpanded ? "rotate-90" : ""}`} />
                          高级选项（时长、镜头作用与素材绑定）
                        </button>

                        {isAdvancedExpanded && (
                          <div className="mt-2 grid grid-cols-1 gap-2.5 rounded-lg border border-border/60 bg-secondary/15 p-2.5 sm:grid-cols-3">
                            <label className="space-y-1 text-[11px] font-medium">
                              <span>镜头时长（秒）</span>
                              <Input
                                type="number"
                                min={0.5}
                                max={60}
                                step={0.5}
                                value={scene.duration_seconds}
                                onChange={(e) => onUpdateScene(index, { duration_seconds: Number(e.target.value) })}
                                className="h-8 text-xs font-mono"
                                disabled={hasActiveJob}
                              />
                            </label>
                            <label className="space-y-1 text-[11px] font-medium">
                              <span>叙事作用</span>
                              <Select
                                value={scene.visual_role || "concept"}
                                onChange={(e) => onUpdateScene(index, { visual_role: e.target.value as VisualRole })}
                                className="h-8 text-xs"
                                disabled={hasActiveJob}
                              >
                                {VISUAL_ROLE_OPTIONS.filter((i) => !["product_shot", "cta"].includes(i.value)).map((item) => (
                                  <option key={item.value} value={item.value}>
                                    {item.label}
                                  </option>
                                ))}
                              </Select>
                            </label>
                            <label className="space-y-1 text-[11px] font-medium">
                              <span>覆盖素材</span>
                              <Select
                                value={scene.media_asset_id || ""}
                                onChange={(e) => {
                                  const selected = projectAssets.find((a) => a.id === e.target.value);
                                  onUpdateScene(index, {
                                    media_asset_id: e.target.value || null,
                                    layout_params: { ...(scene.layout_params || {}), media_type: selected?.asset_type },
                                  });
                                }}
                                className="h-8 text-xs"
                                disabled={hasActiveJob}
                              >
                                <option value="">自动根据提示词生成</option>
                                {projectAssets.map((asset) => (
                                  <option key={asset.id} value={asset.id}>
                                    {asset.file_name}
                                  </option>
                                ))}
                              </Select>
                            </label>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </article>
              );
            })
          )}
        </main>

        {/* 5. 侧边栏：历史记录与状态 */}
        <aside className="space-y-4 xl:sticky xl:top-5 xl:self-start">
          {/* 生成准备检查项（如果未通过时展示） */}
          {!readiness?.ready && (
            <Card className="border-amber-500/30 bg-amber-500/5">
              <CardContent className="space-y-2 p-3.5">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-600 dark:text-amber-400">
                  <AlertTriangle className="h-4 w-4" />
                  生成准备核验
                </div>
                {(readiness?.checks || [])
                  .filter((c) => c.status !== "pass")
                  .map((check) => (
                    <div key={check.key} className="rounded border border-amber-500/20 bg-background/50 p-2 text-xs">
                      <p className="font-medium text-foreground">{check.label}</p>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">{check.message}</p>
                    </div>
                  ))}
              </CardContent>
            </Card>
          )}

          {/* 生成记录历史列表 */}
          <Card className="border-border/70">
            <div className="border-b border-border/50 px-3.5 py-2.5">
              <h3 className="text-xs font-semibold text-foreground">生成记录</h3>
            </div>
            <CardContent className="space-y-1.5 p-2.5">
              {jobs.length === 0 ? (
                <p className="py-4 text-center text-xs text-muted-foreground">暂无生成记录</p>
              ) : (
                jobs.map((item) => {
                  const isSelected = (selectedJobId || jobs[0]?.id) === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => onSelectJobId(item.id)}
                      className={`w-full rounded-lg border p-2.5 text-left text-xs transition-colors ${
                        isSelected
                          ? "border-primary/60 bg-primary/5 text-foreground font-medium"
                          : "border-border/60 hover:bg-secondary/40 text-muted-foreground"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1.5">
                          {ACTIVE.has(item.status) && <Loader2 className="h-3 w-3 animate-spin text-primary" />}
                          {jobLabel(item.status)}
                        </span>
                        <span className="font-mono text-[11px]">{item.progress}%</span>
                      </div>
                      <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                        {item.created_at ? new Date(item.created_at).toLocaleTimeString("zh-CN") : ""}
                      </p>
                    </button>
                  );
                })
              )}
            </CardContent>
          </Card>
        </aside>
      </div>

      {/* 删除分镜确认对话框 */}
      <ConfirmDialog
        open={sceneToDelete !== null}
        onOpenChange={(open) => !open && setSceneToDelete(null)}
        title="删除这个镜头？"
        description={
          sceneToDelete === null
            ? undefined
            : `镜头 ${sceneToDelete + 1} 的旁白台词和画面设置将从故事板中移除。`
        }
        confirmLabel="确认删除"
        variant="destructive"
        onConfirm={() => {
          if (sceneToDelete !== null) onDeleteScene(sceneToDelete);
        }}
      />
    </div>
  );
}
