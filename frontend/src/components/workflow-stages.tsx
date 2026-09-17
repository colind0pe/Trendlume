"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Circle,
  AlertCircle,
  Loader2,
  RotateCcw,
  Download,
  FileText,
  SlidersHorizontal,
  ShieldCheck,
  Volume2,
  Image as ImageIcon,
  Film,
  RefreshCw,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { isSourceMaterialMode, resolveSceneAssetRefreshAction } from "@/lib/task-generation-state";
import { getContentModeSpec } from "@/lib/ui-constants";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import type {
  WorkflowSnapshot,
  WorkflowStageSummary,
  WorkflowStepRun,
} from "@/lib/types";

export const STAGE_NAMES: Record<string, string> = {
  topic: "主题",
  research: "研究",
  planning: "策划",
  script: "脚本",
  storyboard: "分镜",
  assets: "素材",
  voice: "配音",
  subtitles: "字幕",
  composition: "合成",
  export: "导出",
};

export const STAGE_SHORT_NAMES: Record<string, string> = {
  topic: "主题",
  research: "研究",
  planning: "策划",
  script: "脚本",
  storyboard: "分镜",
  assets: "素材",
  voice: "配音",
  subtitles: "字幕",
  composition: "合成",
  export: "成片",
};

export const STAGE_STATES: Record<string, string> = {
  waiting: "等待",
  running: "执行中",
  completed: "完成",
  completed_with_warning: "有警告",
  skipped: "已跳过",
  failed: "失败",
  interrupted: "已中断",
  cancelled: "已取消",
  reused: "已复用",
};

export const ALL_STEP_KEYS = [
  "topic",
  "research",
  "planning",
  "script",
  "storyboard",
  "assets",
  "voice",
  "subtitles",
  "composition",
  "export",
] as const;

export function getStageIcon(status: string, validity?: string) {
  if (status === "running") return Loader2;
  if (
    ["failed", "interrupted", "completed_with_warning"].includes(status) ||
    (validity && validity !== "valid")
  ) {
    return AlertCircle;
  }
  if (["completed", "reused", "skipped"].includes(status)) return CheckCircle2;
  return Circle;
}

export function getStageStatusColor(status: string, validity?: string) {
  if (status === "running") return "text-primary border-primary/40 bg-primary/10";
  if (validity === "corrupt" || status === "failed" || status === "interrupted") {
    return "text-destructive border-destructive/40 bg-destructive/10";
  }
  if (validity === "stale" || status === "completed_with_warning") {
    return "text-warning border-warning/40 bg-warning/10";
  }
  if (status === "reused") return "text-primary border-primary/30 bg-primary/5";
  if (status === "completed" || status === "skipped") {
    return "text-success border-success/30 bg-success/10";
  }
  return "text-muted-foreground/60 border-border/60 bg-secondary/20";
}

export function getStageDotColor(status: string, validity?: string) {
  if (status === "running") return "bg-primary animate-pulse";
  if (validity === "corrupt" || status === "failed" || status === "interrupted") {
    return "bg-destructive";
  }
  if (validity === "stale" || status === "completed_with_warning") {
    return "bg-warning";
  }
  if (status === "reused") return "bg-primary";
  if (status === "completed" || status === "skipped") {
    return "bg-success";
  }
  return "bg-muted-foreground/30";
}

/**
 * 紧凑型十阶段流水线微缩轨 (Workflow Mini-Rail)
 * 高度仅约 44px，取代原先通栏占用数百像素的巨幅卡片。
 */
export function WorkflowMiniRail({
  workflow,
  busy,
  onOpenDetails,
  onResume,
  isResumePending,
  activeStageKey,
  variant = "standalone",
  className,
}: {
  workflow?: WorkflowSnapshot | null;
  busy: boolean;
  onOpenDetails: () => void;
  onResume?: () => void;
  isResumePending?: boolean;
  activeStageKey?: string | null;
  variant?: "standalone" | "integrated";
  className?: string;
}) {
  const stagesMap = React.useMemo(() => {
    const map = new Map<string, WorkflowStageSummary>();
    if (workflow?.stages) {
      for (const stage of workflow.stages) {
        map.set(stage.step_key, stage);
      }
    }
    return map;
  }, [workflow]);

  // 计算全局统计信息
  const completedCount = ALL_STEP_KEYS.filter((key) => {
    const stage = stagesMap.get(key);
    return stage?.status === "completed" || stage?.status === "reused" || stage?.status === "skipped";
  }).length;

  const hasIssues = ALL_STEP_KEYS.some((key) => {
    const stage = stagesMap.get(key);
    return (
      stage?.status === "failed" ||
      stage?.status === "interrupted" ||
      stage?.validity === "stale" ||
      stage?.validity === "corrupt"
    );
  });

  const containerStyle =
    variant === "integrated"
      ? "flex flex-wrap items-center justify-between gap-2 text-xs py-0.5"
      : "flex flex-wrap items-center justify-between gap-2.5 rounded-xl glass-card px-3.5 py-2 text-xs shadow-xs";

  return (
    <div
      className={`${containerStyle} ${className || ""}`}
      aria-label="生产流水线概览"
    >
      {/* 左侧：十阶段紧凑流线轨 */}
      <div className="flex flex-1 items-center gap-1 overflow-x-auto py-0.5 scrollbar-none min-w-0">
        <span className="shrink-0 font-medium text-muted-foreground mr-1 hidden sm:inline">
          流水线:
        </span>
        {ALL_STEP_KEYS.map((key, index) => {
          const stage = stagesMap.get(key);
          const status = stage?.status || "waiting";
          const validity = stage?.validity || "valid";
          const Icon = getStageIcon(status, validity);
          const colorClass = getStageStatusColor(status, validity);
          const isCurrentActive = activeStageKey === key || status === "running";

          return (
            <React.Fragment key={key}>
              {index > 0 && (
                <div
                  className={`h-0.5 w-1.5 sm:w-2 shrink-0 rounded-full ${
                    ["completed", "reused"].includes(status)
                      ? "bg-success/50"
                      : "bg-border"
                  }`}
                  aria-hidden="true"
                />
              )}
              <button
                type="button"
                onClick={onOpenDetails}
                title={`${STAGE_NAMES[key] || key} · ${STAGE_STATES[status] || status}${
                  validity === "stale" ? " (已过期)" : validity === "corrupt" ? " (制品损坏)" : ""
                }`}
                className={`group inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 transition-all hover:scale-[1.02] cursor-pointer ${colorClass} ${
                  isCurrentActive ? "ring-2 ring-primary/40" : ""
                }`}
              >
                <Icon
                  className={`h-3 w-3 shrink-0 ${
                    status === "running" ? "animate-spin motion-reduce:animate-none" : ""
                  }`}
                  aria-hidden="true"
                />
                <span className="font-medium text-xs">
                  {STAGE_SHORT_NAMES[key] || key}
                </span>
                {status === "reused" && (
                  <span className="text-xs opacity-80" title="该阶段已复用已有制品">
                    复用
                  </span>
                )}
              </button>
            </React.Fragment>
          );
        })}
      </div>

      {/* 右侧：状态概要与详情唤起入口 */}
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-xs font-mono text-muted-foreground">
          {completedCount}/10 阶段就绪
        </span>

        {hasIssues && (
          <Badge variant="warning" className="text-xs px-1.5 py-0 h-5">
            有更新待重算
          </Badge>
        )}

        {onResume && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onResume}
            disabled={busy || isResumePending}
            className="h-7 px-2 text-xs gap-1 text-muted-foreground hover:text-foreground"
            title="从最近检查点继续任务"
          >
            {isResumePending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RotateCcw className="h-3 w-3" />
            )}
            <span className="hidden md:inline">继续任务</span>
          </Button>
        )}

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onOpenDetails}
          className="h-7 px-2.5 text-xs gap-1.5 font-medium border-border/80 hover:bg-secondary"
        >
          <SlidersHorizontal className="h-3 w-3 text-muted-foreground" />
          <span>流水线详情</span>
        </Button>
      </div>
    </div>
  );
}

/**
 * 生产流水线详情抽屉/弹窗 (Workflow Inspector Dialog)
 * 收纳原本占满首屏的所有 10 阶段详细日志、制品下载、SHA-256 哈希校验与阶段重试。
 */
export function WorkflowInspectorDialog({
  open,
  onClose,
  taskId,
  busy,
  requireSaved,
}: {
  open: boolean;
  onClose: () => void;
  taskId: string;
  busy: boolean;
  requireSaved: () => boolean;
}) {
  const cache = useQueryClient();
  const query = useQuery({
    queryKey: ["task-workflow", taskId],
    queryFn: () => api.getWorkflow(taskId),
    refetchInterval: busy ? 3000 : false,
    enabled: open,
  });

  const action = useMutation({
    mutationFn: ({ step, unit }: { step?: string; unit?: string }) =>
      step
        ? api.retryWorkflowStep(taskId, step, unit)
        : api.resumeTaskGeneration(taskId),
    onSuccess: () => {
      cache.invalidateQueries({ queryKey: ["task-workflow", taskId] });
      cache.invalidateQueries({ queryKey: ["task-detail", taskId] });
    },
  });

  const retry = (step?: string, unit?: string) => {
    if (requireSaved()) action.mutate({ step, unit });
  };

  const renderRunCard = (run: WorkflowStepRun) => {
    return (
      <div
        key={run.id}
        className="min-w-0 space-y-2 overflow-hidden rounded-xl glass-card p-3.5 text-xs"
      >
        <div className="flex flex-wrap items-center justify-between gap-1 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">
            {run.unit_key ? `分镜单元 #${run.unit_key.slice(0, 8)}` : "整阶段运行"} · 第 {run.attempt} 次尝试
          </span>
          <span className="font-mono">
            {run.duration_ms == null ? "耗时记录中" : `${(run.duration_ms / 1000).toFixed(2)} 秒`}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <Badge
            variant={
              ["completed", "reused", "skipped"].includes(run.status)
                ? "success"
                : run.status === "running"
                ? "default"
                : "warning"
            }
            className="text-xs px-2 py-0.5"
          >
            {STAGE_STATES[run.status] || run.status}
          </Badge>
          {run.validity && run.validity !== "valid" && (
            <Badge variant="destructive" className="text-xs px-2 py-0.5">
              {run.validity === "stale" ? "已过期" : "制品损坏"}
            </Badge>
          )}
        </div>

        {run.invalid_reason && (
          <p className="break-words text-xs text-warning bg-warning/5 p-2 rounded-md border border-warning/20">
            失效原因：{run.invalid_reason}
          </p>
        )}
        {run.error_message && (
          <p className="break-words text-xs text-destructive bg-destructive/5 p-2 rounded-md border border-destructive/20 font-mono">
            {run.error_message}
          </p>
        )}
        {run.warning && (
          <p className="break-words text-xs text-warning font-mono">{run.warning}</p>
        )}

        {/* 产物列表 */}
        {!!run.artifacts.length && (
          <div className="space-y-1.5 pt-1">
            <span className="text-xs font-medium text-muted-foreground">产出制品：</span>
            <ul className="space-y-1 rounded-md bg-secondary/30 p-2.5">
              {run.artifacts.map((artifact) => {
                const fileName = artifact.relative_path.split("/").pop() || "制品文件";
                return (
                  <li
                    key={artifact.id}
                    className="min-w-0 flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-xs"
                  >
                    <a
                      className="inline-flex max-w-full items-center gap-1.5 text-primary underline underline-offset-2 truncate hover:opacity-80"
                      href={api.workflowArtifactUrl(taskId, artifact.id)}
                      download
                      aria-label={`下载 ${fileName}`}
                    >
                      <Download className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                      <span className="truncate font-medium">{fileName}</span>
                    </a>
                    <div className="flex items-center gap-2 shrink-0 text-muted-foreground font-mono text-xs">
                      <span>{(artifact.size_bytes / 1024).toFixed(1)} KB</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {run.unit_key && (
          <div className="pt-1 flex justify-end">
            <Button
              size="sm"
              variant="outline"
              disabled={busy || action.isPending}
              aria-label={`重试此分镜单元`}
              onClick={() => retry(run.step_key, run.unit_key)}
              className="h-7 text-xs px-2.5"
            >
              重试此单元
            </Button>
          </div>
        )}
      </div>
    );
  };

  return (
    <Dialog open={open} onClose={onClose} className="max-w-4xl max-h-[88vh] p-5 sm:p-6">
      <DialogHeader>
        <div className="flex items-center justify-between pr-6">
          <DialogTitle className="text-base sm:text-lg flex items-center gap-2 font-semibold">
            <SlidersHorizontal className="h-4.5 w-4.5 text-primary" />
            流水线控制台
          </DialogTitle>
        </div>
        <DialogDescription className="text-xs sm:text-sm leading-relaxed text-muted-foreground">
          监控阶段执行状态、各单元耗时与制品产出。
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-3.5 my-3 max-h-[60vh] overflow-y-auto pr-1">
        <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl border border-border bg-secondary/25">
          <div className="text-xs sm:text-sm text-foreground font-medium">
            自动校验上游依赖并保留已修改的手工分镜素材
          </div>
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs gap-1.5 px-3"
            disabled={busy || action.isPending}
            onClick={() => retry()}
          >
            <RotateCcw className="h-3.5 w-3.5" />
            继续未完流水线
          </Button>
        </div>

        {query.isPending && (
          <div className="flex items-center justify-center py-8 text-xs sm:text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
            正在读取十阶段状态与制品快照…
          </div>
        )}

        {query.error && (
          <div
            role="alert"
            className="flex flex-wrap items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-xs sm:text-sm text-destructive"
          >
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span className="flex-1">读取失败：{query.error.message}</span>
            <Button variant="outline" size="sm" onClick={() => query.refetch()} className="h-7 text-xs">
              重试
            </Button>
          </div>
        )}

        {action.error && (
          <div
            role="alert"
            className="flex flex-wrap items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-xs sm:text-sm text-destructive"
          >
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span className="flex-1">操作失败：{action.error.message}</span>
            <Button variant="outline" size="sm" onClick={() => action.reset()} className="h-7 text-xs">
              知道了
            </Button>
          </div>
        )}

        {query.data?.stages.map((stage) => {
          const Icon = getStageIcon(stage.status, stage.validity);
          const stageName = STAGE_NAMES[stage.step_key] || stage.step_key;
          const stageStatus = STAGE_STATES[stage.status] || stage.status;

          return (
            <details
              key={stage.step_key}
              className="min-w-0 overflow-hidden rounded-xl border border-border bg-card/60"
            >
              <summary className="min-h-11 cursor-pointer p-3.5 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring flex items-center justify-between hover:bg-secondary/40 transition-colors">
                <span className="inline-flex max-w-full flex-wrap items-center gap-2.5">
                  <Icon
                    className={`h-4 w-4 shrink-0 ${
                      stage.status === "running" ? "animate-spin motion-reduce:animate-none" : ""
                    }`}
                    aria-hidden="true"
                  />
                  <strong className="text-sm font-semibold">{stageName}</strong>
                  <Badge
                    variant={
                      ["completed", "reused", "skipped"].includes(stage.status)
                        ? "success"
                        : stage.status === "running"
                        ? "default"
                        : "warning"
                    }
                    className="text-xs px-2 py-0.5"
                  >
                    {stageStatus}
                  </Badge>
                  {stage.validity === "stale" && (
                    <Badge variant="warning" className="text-xs px-2 py-0.5">已过期</Badge>
                  )}
                  {stage.validity === "corrupt" && (
                    <Badge variant="destructive" className="text-xs px-2 py-0.5">制品损坏</Badge>
                  )}
                </span>
                <span className="text-xs text-muted-foreground font-mono">
                  {(stage.duration_ms / 1000).toFixed(1)}s · 重试 {stage.retry_count}
                </span>
              </summary>

              <div className="space-y-3 border-t border-border p-3.5 bg-secondary/10">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground">阶段控制</span>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs px-2.5"
                    disabled={busy || action.isPending}
                    aria-label={`重试${stageName}阶段`}
                    onClick={() => retry(stage.step_key)}
                  >
                    重试此阶段
                  </Button>
                </div>

                {stage.units.map((run) => renderRunCard(run))}

                {!stage.units.length && (
                  <p className="text-xs text-muted-foreground">该阶段尚无单元执行记录。</p>
                )}

                {stage.history.length > 0 && (
                  <details className="pt-1">
                    <summary className="cursor-pointer py-1 text-xs text-muted-foreground hover:text-foreground">
                      查看全部历史尝试记录（共 {stage.history.length} 条）
                    </summary>
                    <div className="space-y-2 pt-2">
                      {stage.history.map((run) => renderRunCard(run))}
                    </div>
                  </details>
                )}
              </div>
            </details>
          );
        })}
      </div>

      <DialogFooter>
        <Button variant="outline" size="sm" onClick={onClose} className="text-sm h-9 px-4">
          关闭控制台
        </Button>
      </DialogFooter>
    </Dialog>
  );
}

/**
 * 故事板分镜级流水线状态单元 (Scene Pipeline Status)
 * 深度融合在每个分镜卡片中，展示对应镜头的配音/画面运行状态、失效提示、手工素材保护、单镜头重试。
 */
export function ScenePipelineStatus({
  taskId,
  sceneId,
  workflow,
  busy,
  isManualAsset,
  onRetryUnit,
  isUnitRetrying,
  onGenerateTTS,
  onGenerateImage,
  onGenerateVideo,
  onGenerateOnlineMaterial,
  isGeneratingTTS,
  isGeneratingImage,
  isGeneratingVideo,
  isGeneratingOnlineMaterial,
  isGeneratingStopMotion = false,
  contentMode = "generated_image",
  animationMode = null,
  hasAudio = false,
  hasVisual = false,
  hasVideo = false,
  canGenerateVoice = true,
  canGenerateVisual = true,
  measuredDuration,
  errorMessage,
}: {
  taskId: string;
  sceneId?: string | null;
  sceneIndex: number;
  workflow?: WorkflowSnapshot | null;
  busy: boolean;
  isManualAsset: boolean;
  onRetryUnit?: (stepKey: "voice" | "assets", unitKey: string) => void;
  isUnitRetrying?: boolean;
  onGenerateTTS?: () => void;
  onGenerateImage?: () => void;
  onGenerateVideo?: () => void;
  onGenerateOnlineMaterial?: () => void;
  isGeneratingTTS?: boolean;
  isGeneratingImage?: boolean;
  isGeneratingVideo?: boolean;
  isGeneratingOnlineMaterial?: boolean;
  isGeneratingStopMotion?: boolean;
  contentMode?: string;
  animationMode?: string | null;
  hasAudio?: boolean;
  hasVisual?: boolean;
  hasVideo?: boolean;
  canGenerateVoice?: boolean;
  canGenerateVisual?: boolean;
  measuredDuration?: number | null;
  errorMessage?: string | null;
}) {
  // 从 workflow 中获取当前分镜对应的 voice、assets、composition 单元
  const { voiceRun, assetsRun, compRun } = React.useMemo(() => {
    if (!workflow || !sceneId) return { voiceRun: null, assetsRun: null, compRun: null };

    const voiceStage = workflow.stages?.find((s) => s.step_key === "voice");
    const assetsStage = workflow.stages?.find((s) => s.step_key === "assets");
    const compStage = workflow.stages?.find((s) => s.step_key === "composition");

    const vRun = voiceStage?.units?.find((u) => u.unit_key === sceneId) || null;
    const aRun = assetsStage?.units?.find((u) => u.unit_key === sceneId) || null;
    const cRun = compStage?.units?.find((u) => u.unit_key === sceneId) || null;

    return { voiceRun: vRun, assetsRun: aRun, compRun: cRun };
  }, [workflow, sceneId]);

  const voiceArtifact = voiceRun?.artifacts?.[0];
  const assetArtifact = assetsRun?.artifacts?.[0];

  const isVoiceStale = voiceRun?.validity === "stale";
  const isAssetStale = assetsRun?.validity === "stale";

  const voiceReady = hasAudio || voiceRun?.status === "completed" || voiceRun?.status === "reused";
  const visualReady = hasVisual || assetsRun?.status === "completed" || assetsRun?.status === "reused";
  const assetRefreshAction = resolveSceneAssetRefreshAction(
    contentMode,
    Boolean(onGenerateOnlineMaterial),
    Boolean(onRetryUnit),
    Boolean(sceneId),
  );
  const sourceMaterialMode = isSourceMaterialMode(contentMode);
  const contentModeSpec = getContentModeSpec(contentMode);
  const isEnhancedStopMotion = animationMode === "enhanced_stop_motion";
  const isStaticMode = contentModeSpec?.sourceKind === "text";
  const isUploadedMode = contentModeSpec?.requiresSourceAsset === true;
  const isGeneratedVideoMode = contentModeSpec?.visualKind === "video" && contentModeSpec?.sourceKind === "ai";
  const canRegenerate = contentModeSpec?.supportsSceneRetry === true && contentModeSpec?.sourceKind === "ai";
  const canRefreshVisual = !isEnhancedStopMotion && (canRegenerate || sourceMaterialMode);
  const sourceMaterialLabel = contentModeSpec?.label || "素材";
  const refreshAsset = () => {
    if (assetRefreshAction === "online_material") {
      onGenerateOnlineMaterial?.();
      return;
    }
    if (assetRefreshAction === "workflow_unit" && sceneId) {
      onRetryUnit?.("assets", sceneId);
      return;
    }
    if (isGeneratedVideoMode) {
      onGenerateVideo?.();
      return;
    }
    if (contentModeSpec?.visualKind === "image") onGenerateImage?.();
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-2.5 rounded-md border border-border/70 bg-secondary/15 px-3 py-2 text-xs">
      {/* 左侧：深度结合流水线的生成与状态操作 */}
      <div className="flex flex-wrap items-center gap-3">
        {/* 配音状态与操作 */}
        <div className="inline-flex items-center gap-1.5">
          {isGeneratingTTS ? (
            <span className="inline-flex items-center gap-1 text-primary text-xs font-medium">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              配音生成中…
            </span>
          ) : isVoiceStale || voiceRun?.status === "failed" ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy || isUnitRetrying}
              onClick={() => (onRetryUnit && sceneId ? onRetryUnit("voice", sceneId) : onGenerateTTS?.())}
              className="h-7 text-xs px-2.5 gap-1.5 border-warning/40 text-warning hover:bg-warning/10 font-medium"
              title="旁白已修改，重新生成配音"
            >
              <RefreshCw className="h-3 w-3" />
              旁白已改 · 重试配音
            </Button>
          ) : voiceReady ? (
            <div className="inline-flex items-center gap-1 rounded bg-secondary/70 px-2 py-1 text-xs text-foreground">
              <span className="h-1.5 w-1.5 rounded-full bg-success" />
              <Volume2 className="h-3.5 w-3.5 text-success" />
              <span className="font-medium">
                配音就绪{voiceRun?.status === "reused" && <span className="text-primary text-xs font-normal ml-0.5">(复用)</span>}
              </span>
              {voiceRun?.duration_ms != null && (
                <span className="text-xs text-muted-foreground font-mono">
                  {(voiceRun.duration_ms / 1000).toFixed(1)}s
                </span>
              )}
              {voiceArtifact && (
                <a
                  href={api.workflowArtifactUrl(taskId, voiceArtifact.id)}
                  download
                  title={`下载音频: ${voiceArtifact.relative_path.split("/").pop()}`}
                  className="text-primary hover:opacity-80 p-0.5 ml-0.5"
                >
                  <Download className="h-3 w-3" />
                </a>
              )}
              {onRetryUnit && sceneId && (
                <button
                  type="button"
                  onClick={() => onRetryUnit("voice", sceneId)}
                  disabled={busy || isUnitRetrying}
                  title="重新生成此分镜配音"
                  className="text-muted-foreground hover:text-foreground p-0.5 ml-0.5 cursor-pointer"
                >
                  <RefreshCw className="h-2.5 w-2.5" />
                </button>
              )}
            </div>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy || !canGenerateVoice}
              onClick={onGenerateTTS}
              className="h-7 text-xs px-2.5 gap-1.5"
            >
              <Volume2 className="h-3.5 w-3.5 text-muted-foreground" />
              生成配音
            </Button>
          )}
        </div>

        <span className="text-border">|</span>

        {/* 画面状态与操作 */}
        <div className="inline-flex items-center gap-1.5">
          {isEnhancedStopMotion ? (
            isGeneratingStopMotion ? (
              <span className="inline-flex items-center gap-1 text-primary text-xs font-medium">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                关键状态生成中…
              </span>
            ) : visualReady ? (
              <Badge variant="outline" className="h-7 px-2.5 text-xs text-primary border-primary/30 font-normal gap-1.5">
                <ImageIcon className="h-3.5 w-3.5 text-primary" />
                动画状态已就绪
              </Badge>
            ) : (
              <Badge variant="warning" className="h-7 px-2.5 text-xs font-normal gap-1.5">
                <ImageIcon className="h-3.5 w-3.5" />
                等待生成动画状态
              </Badge>
            )
          ) : isStaticMode ? (
            <Badge variant="secondary" className="h-7 px-2.5 text-xs font-normal gap-1.5">
              <FileText className="h-3.5 w-3.5 text-muted-foreground" />
              文字排版 · 无需素材
            </Badge>
          ) : isManualAsset ? (
            <Badge variant="outline" className="h-7 px-2.5 text-xs text-primary border-primary/30 font-normal gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-primary" />
              已保护我的素材
            </Badge>
          ) : isGeneratingImage || isGeneratingVideo || isGeneratingOnlineMaterial ? (
            <span className="inline-flex items-center gap-1 text-primary text-xs font-medium">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {sourceMaterialMode ? `${sourceMaterialLabel}获取中…` : isGeneratedVideoMode ? "AI 视频生成中…" : "AI 图片生成中…"}
            </span>
          ) : (isAssetStale || assetsRun?.status === "failed") && canRefreshVisual ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy || isUnitRetrying}
              onClick={refreshAsset}
              className="h-7 text-xs px-2.5 gap-1.5 border-warning/40 text-warning hover:bg-warning/10 font-medium"
              title={sourceMaterialMode ? `${sourceMaterialLabel}不可用，重新获取` : isGeneratedVideoMode ? "视频生成失败，重新生成" : "图片生成失败，重新生成"}
            >
              <RefreshCw className="h-3 w-3" />
              {sourceMaterialMode ? `${sourceMaterialLabel}失败 · 重新获取` : isGeneratedVideoMode ? "AI 视频失败 · 重试" : "AI 图片失败 · 重试"}
            </Button>
          ) : visualReady ? (
            <div className="inline-flex items-center gap-1 rounded bg-secondary/70 px-2 py-1 text-xs text-foreground">
              <span className="h-1.5 w-1.5 rounded-full bg-success" />
              {isGeneratedVideoMode || hasVideo ? (
                <Film className="h-3.5 w-3.5 text-success" />
              ) : (
                <ImageIcon className="h-3.5 w-3.5 text-success" />
              )}
              <span className="font-medium">
                {sourceMaterialMode
                  ? `${sourceMaterialLabel}就绪`
                  : isGeneratedVideoMode
                  ? "AI 视频就绪"
                  : isUploadedMode
                  ? "我的素材就绪"
                  : "AI 图片就绪"}
                {assetsRun?.status === "reused" && <span className="text-primary text-xs font-normal ml-0.5">(复用)</span>}
              </span>
              {assetArtifact && (
                <a
                  href={api.workflowArtifactUrl(taskId, assetArtifact.id)}
                  download
                  title={`下载画面: ${assetArtifact.relative_path.split("/").pop()}`}
                  className="text-primary hover:opacity-80 p-0.5 ml-0.5"
                >
                  <Download className="h-3 w-3" />
                </a>
              )}
              {sceneId && (assetRefreshAction !== "none" || canRegenerate) && (
                <button
                  type="button"
                  onClick={refreshAsset}
                  disabled={busy || isUnitRetrying}
                  title={sourceMaterialMode ? `重新获取${sourceMaterialLabel}` : isGeneratedVideoMode ? "重新生成 AI 视频" : "重新生成 AI 图片"}
                  className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground p-0.5 ml-0.5 cursor-pointer"
                >
                  <RefreshCw className="h-2.5 w-2.5" />
                  <span className="text-xs">{sourceMaterialMode ? "重新获取" : "重新生成"}</span>
                </button>
              )}
            </div>
          ) : isUploadedMode ? (
            <Badge variant="warning" className="h-7 px-2.5 text-xs font-normal gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5" />
              请先绑定我的素材
            </Badge>
          ) : sourceMaterialMode ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy || !canGenerateVisual || assetRefreshAction === "none"}
              onClick={refreshAsset}
              className="h-7 text-xs px-2.5 gap-1.5"
            >
              <Film className="h-3.5 w-3.5 text-muted-foreground" />
              获取素材库视频
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy || !canGenerateVisual || (isGeneratedVideoMode ? !onGenerateVideo : !onGenerateImage)}
              onClick={isGeneratedVideoMode ? onGenerateVideo : onGenerateImage}
              className="h-7 text-xs px-2.5 gap-1.5"
            >
              {isGeneratedVideoMode ? (
                <Film className="h-3.5 w-3.5 text-muted-foreground" />
              ) : (
                <ImageIcon className="h-3.5 w-3.5 text-muted-foreground" />
              )}
              {isGeneratedVideoMode ? "生成 AI 视频" : "生成 AI 图片"}
            </Button>
          )}
        </div>

        {/* 片段合成状态 */}
        {compRun && (
          <>
            <span className="text-border hidden sm:inline">|</span>
            <div className="hidden sm:inline-flex items-center gap-1 text-xs text-muted-foreground">
              <span className={`h-1.5 w-1.5 rounded-full ${getStageDotColor(compRun.status, compRun.validity)}`} />
              <span>片段: {compRun.status === "completed" ? "已合成" : STAGE_STATES[compRun.status] || compRun.status}</span>
            </div>
          </>
        )}
      </div>

      {/* 右侧：实测时长或错误提示 */}
      <div className="flex items-center gap-2 shrink-0 text-xs">
        {measuredDuration != null && (
          <span className="font-mono text-xs text-muted-foreground">
            实测 {Number(measuredDuration).toFixed(1)}s
          </span>
        )}
        {errorMessage && (
          <span
            className="inline-flex items-center gap-1 text-destructive text-xs max-w-[220px] truncate"
            title={errorMessage}
          >
            <AlertCircle className="h-3 w-3 shrink-0" />
            <span className="truncate">{errorMessage}</span>
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * 兼容旧导出
 */
export function WorkflowStages({
  taskId,
  busy,
  requireSaved,
}: {
  taskId: string;
  busy: boolean;
  requireSaved: () => boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const query = useQuery({
    queryKey: ["task-workflow", taskId],
    queryFn: () => api.getWorkflow(taskId),
    refetchInterval: busy ? 3000 : false,
  });

  return (
    <div className="space-y-2">
      <WorkflowMiniRail
        workflow={query.data}
        busy={busy}
        onOpenDetails={() => setOpen(true)}
      />
      <WorkflowInspectorDialog
        open={open}
        onClose={() => setOpen(false)}
        taskId={taskId}
        busy={busy}
        requireSaved={requireSaved}
      />
    </div>
  );
}
