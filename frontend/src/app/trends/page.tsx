"use client";

import * as React from "react";
import Link from "next/link";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  ExternalLink,
  Flame,
  Globe,
  Loader2,
  Music,
  Play,
  RefreshCw,
  Search,
  Settings2,
  ShieldAlert,
  Sparkles,
  Volume2,
  WifiOff,
  X,
} from "lucide-react";
import { api, ApiError } from "@/lib/api-client";
import type {
  Asset,
  ContentMode,
  KnowledgeBrief,
  Project,
  TemplateCatalogItem,
  TrendItem,
  TrendFreshness,
  TrendFeedResponse,
  TrendProposal,
  TrendProposalActionResponse,
  TrendRelation,
  TrendRun,
  TrendSourceCatalog,
  TrendSourceStatus,
  TrendSubscription,
  VoiceInfo,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Select } from "@/components/ui/field";
import { Input, SearchInput } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { PageContainer, PageHeader, SectionHeader } from "@/components/ui/page-shell";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { cn, formatDate } from "@/lib/utils";
import { buildGenerationOptions } from "@/lib/task-generation-state";
import {
  PLATFORMS_CONFIG,
  PLATFORM_OPTIONS,
  TrendSourceMonitorCard,
} from "@/components/trends/trend-source-monitor";
import {
  ASSET_TYPE_LABELS,
  CONTENT_MODE_GROUPS,
  CONTENT_MODE_SPECS,
  GENRE_OPTIONS,
  HOOK_OPTIONS,
  SCENE_COUNT_PRESETS,
  SPEED_PRESETS,
  STYLE_PRESET_OPTIONS,
  TREND_FREQUENCY_LABELS,
  TREND_FREQUENCY_OPTIONS,
  formatTemplateName,
  isContentMode,
} from "@/lib/ui-constants";

const FRESHNESS_OPTIONS: Array<{ value: TrendFreshness; label: string }> = [
  { value: "15m", label: "近 15 分钟" },
  { value: "1h", label: "近 1 小时" },
  { value: "6h", label: "近 6 小时" },
  { value: "24h", label: "近 24 小时" },
  { value: "all", label: "不限时间" },
];

const RELATION_LABELS: Record<TrendRelation, string> = {
  high: "高关联",
  medium: "中关联",
  low: "低关联",
  unknown: "待评估",
};

const SOURCE_LABELS: Record<TrendSourceStatus, string> = {
  fresh: "新鲜",
  stale: "可能过期",
  failed: "采集失败",
  unavailable: "不可用",
};

function relationTone(relation?: TrendRelation): StatusTone {
  if (relation === "high") return "success";
  if (relation === "medium") return "info";
  if (relation === "low") return "warning";
  return "neutral";
}

function sourceTone(status?: TrendSourceStatus): StatusTone {
  if (status === "fresh") return "success";
  if (status === "stale") return "warning";
  if (status === "failed" || status === "unavailable") return "destructive";
  return "neutral";
}

function sourceLabel(status?: TrendSourceStatus) {
  return status ? SOURCE_LABELS[status] : "未评估";
}

function safeExternalUrl(value?: string | null) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

function formatMetric(item: TrendItem) {
  if (item.raw_metric === undefined || item.raw_metric === null || item.raw_metric === "") return "—";
  return `${item.raw_metric}${item.metric_unit ? ` ${item.metric_unit}` : ""}`;
}

function errorCopy(error: unknown) {
  if (error instanceof ApiError && error.status === 404) {
    return "热点服务未就绪，请稍后重试。";
  }
  return "热点数据暂时不可用，请检查服务状态。";
}

// 排名徽章
function RankBadge({ rank }: { rank: number }) {
  if (rank === 1) {
    return (
      <span
        aria-label="第 1 名"
        className="inline-flex h-7 w-8 items-center justify-center rounded-lg bg-amber-500/15 font-mono text-xs font-bold text-amber-500 border border-amber-500/30 shadow-xs shadow-amber-500/20"
      >
        #1
      </span>
    );
  }
  if (rank === 2) {
    return (
      <span
        aria-label="第 2 名"
        className="inline-flex h-7 w-8 items-center justify-center rounded-lg bg-slate-400/15 font-mono text-xs font-bold text-slate-300 border border-slate-400/30 shadow-xs"
      >
        #2
      </span>
    );
  }
  if (rank === 3) {
    return (
      <span
        aria-label="第 3 名"
        className="inline-flex h-7 w-8 items-center justify-center rounded-lg bg-orange-500/15 font-mono text-xs font-bold text-orange-400 border border-orange-500/30 shadow-xs"
      >
        #3
      </span>
    );
  }
  return (
    <span
      aria-label={`第 ${rank || "—"} 名`}
      className="inline-flex h-7 w-8 items-center justify-center font-mono text-xs font-semibold tabular-nums text-muted-foreground"
    >
      {rank > 0 ? `#${rank}` : "—"}
    </span>
  );
}

// 单行热点展示组件
function TrendRow({
  item,
  onSelect,
  showRelation,
}: {
  item: TrendItem;
  onSelect: (item: TrendItem) => void;
  showRelation: boolean;
}) {
  const platform = item.platform_label || item.platform;
  const config = PLATFORMS_CONFIG[item.platform] || {
    badgeClass: "bg-secondary/70 text-foreground",
    dotClass: "bg-primary",
  };

  return (
    <button
      type="button"
      onClick={() => onSelect(item)}
      aria-label={`查看热点：${item.title}`}
      className="group grid w-full grid-cols-[2.75rem_minmax(0,1fr)_auto] items-center gap-3.5 rounded-xl border border-border/70 bg-card/60 px-3.5 py-3 text-left backdrop-blur-xs transition-all duration-200 hover:border-primary/50 hover:bg-card/90 hover:shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:grid-cols-[3.25rem_minmax(0,1fr)_9.5rem_auto] sm:px-4.5 cursor-pointer"
    >
      <div className="flex items-center justify-center">
        <RankBadge rank={item.rank} />
      </div>

      <div className="min-w-0 pr-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-foreground group-hover:text-primary transition-colors">
            {item.title}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span className={cn("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium border", config.badgeClass)}>
            <span className={cn("h-1.5 w-1.5 rounded-full", config.dotClass)} />
            {platform}
          </span>
          <span aria-hidden="true" className="text-border">·</span>
          <span className="font-mono text-[11px] tabular-nums">
            {item.fetched_at ? formatDate(item.fetched_at) : "最新"}
          </span>
        </div>
      </div>

      <div className="hidden min-w-0 sm:block text-right">
        <div className="font-mono text-xs font-bold tabular-nums text-foreground">
          {formatMetric(item)}
        </div>
        <div className="mt-0.5 text-[11px] text-muted-foreground">原始热度</div>
      </div>

      <div className="flex items-center gap-2">
        {showRelation && item.project_relevance && item.project_relevance !== "unknown" && (
          <StatusBadge
            label={RELATION_LABELS[item.project_relevance]}
            tone={relationTone(item.project_relevance)}
            showDot={false}
            className="shrink-0 text-xs px-2 py-0.5"
          />
        )}
        <div className="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground transition-all group-hover:bg-primary/10 group-hover:text-primary">
          <ArrowRight aria-hidden="true" className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
        </div>
      </div>
    </button>
  );
}

// 骨架屏组件
function TrendSkeleton() {
  return (
    <div className="space-y-2.5" aria-label="正在加载热点列表" role="status">
      {[1, 2, 3, 4, 5, 6].map((item) => (
        <div
          key={item}
          className="grid h-16 grid-cols-[3.25rem_1fr_8rem] items-center gap-3.5 rounded-xl border border-border/50 bg-card/35 px-4 motion-safe:animate-pulse"
        >
          <div className="h-6 w-8 rounded-lg bg-secondary/80" />
          <div className="space-y-2">
            <div className="h-4 w-3/5 rounded bg-secondary/80" />
            <div className="h-3 w-1/4 rounded bg-secondary/60" />
          </div>
          <div className="space-y-2 text-right">
            <div className="ml-auto h-4 w-16 rounded bg-secondary/80" />
            <div className="ml-auto h-3 w-12 rounded bg-secondary/60" />
          </div>
        </div>
      ))}
    </div>
  );
}

// 热点详情与选题方案工作台（Sheet 抽屉组件）
function TrendDetailSheet({
  item,
  projectId,
  projects,
  projectsLoading,
  projectsError,
  onProjectChange,
  onProjectsRetry,
  onClose,
}: {
  item: TrendItem;
  projectId: string;
  projects: Project[];
  projectsLoading: boolean;
  projectsError: boolean;
  onProjectChange: (projectId: string) => void;
  onProjectsRetry: () => void;
  onClose: () => void;
}) {
  const platform = item.platform_label || item.platform;
  const sourceUrl = safeExternalUrl(item.source_url);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [angle, setAngle] = React.useState("");
  const [sceneCount, setSceneCount] = React.useState(8);
  const [enableResearch, setEnableResearch] = React.useState(true);
  const [localProposal, setLocalProposal] = React.useState<TrendProposal | null>(null);

  // Keep hotspot generation settings aligned with the regular task dialog.
  const [contentMode, setContentMode] = React.useState<ContentMode>("generated_image");
  const [selectedTemplateId, setSelectedTemplateId] = React.useState("");
  const [taskGenre, setTaskGenre] = React.useState("auto");
  const [knowledgeAudience, setKnowledgeAudience] = React.useState("");
  const [knowledgeThesis, setKnowledgeThesis] = React.useState("");
  const [knowledgeViewerTakeaway, setKnowledgeViewerTakeaway] = React.useState("");
  const [taskHookType, setTaskHookType] = React.useState("auto");
  const [taskStylePreset, setTaskStylePreset] = React.useState("stick_figure");
  const [customPromptPrefix, setCustomPromptPrefix] = React.useState("");
  const [taskVoiceId, setTaskVoiceId] = React.useState("");
  const [taskSpeed, setTaskSpeed] = React.useState(1.0);
  const [bgmAssetId, setBgmAssetId] = React.useState("");
  const [bgmEnabled, setBgmEnabled] = React.useState(true);
  const [bgmVolume, setBgmVolume] = React.useState(0.2);
  const [sourceAssetId, setSourceAssetId] = React.useState("");

  const hasSelectedProject = Boolean(projectId && projectId !== "all");
  const selectedProject = projects.find((project) => project.id === projectId);
  const projectAspect = selectedProject?.aspect_ratio || "9:16";

  // 1. 若已选项目，打开抽屉自动即时获取或生成草稿。
  // Proposal creation is a write operation, so keep it out of query caching.
  type ProposalRequest = { projectId: string; trendItemId: string };
  const {
    data: createdProposal,
    isPending: isProposalPending,
    isError: isProposalError,
    mutate: createProposal,
    reset: resetProposal,
  } = useMutation<TrendProposal, Error, ProposalRequest>({
    mutationFn: ({ projectId: requestedProjectId, trendItemId }) =>
      api.createTrendProposal({ project_id: requestedProjectId, trend_item_id: trendItemId }),
  });

  const proposalRequestKey = `${projectId}:${item.id}`;
  const requestedProposalKey = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!hasSelectedProject) {
      requestedProposalKey.current = null;
      resetProposal();
      return;
    }
    if (requestedProposalKey.current === proposalRequestKey) return;
    requestedProposalKey.current = proposalRequestKey;
    resetProposal();
    createProposal({ projectId, trendItemId: item.id });
  }, [
    createProposal,
    hasSelectedProject,
    item.id,
    projectId,
    proposalRequestKey,
    resetProposal,
  ]);

  const templatesQuery = useQuery<TemplateCatalogItem[]>({
    queryKey: ["template-catalog"],
    queryFn: () => api.listTemplates(),
    enabled: hasSelectedProject,
    staleTime: 5 * 60_000,
  });

  const voicesQuery = useQuery<VoiceInfo[]>({
    queryKey: ["voices", "active"],
    queryFn: () => api.listVoices(true),
    enabled: hasSelectedProject,
    staleTime: 5 * 60_000,
  });

  const bgmQuery = useQuery<Asset[]>({
    queryKey: ["project-bgm", projectId],
    queryFn: () => api.getProjectBgm(projectId),
    enabled: hasSelectedProject,
    staleTime: 5 * 60_000,
  });

  const sourceAssetsQuery = useQuery<Asset[]>({
    queryKey: ["project-assets", projectId],
    queryFn: () => api.listAssets(projectId),
    enabled: hasSelectedProject && contentMode === "uploaded_asset",
    staleTime: 60_000,
  });

  const proposal = localProposal || createdProposal || null;
  const templates = templatesQuery.data || [];
  const taskVoices = voicesQuery.data || [];
  const projectBgm = bgmQuery.data || [];
  const sourceAssets = (sourceAssetsQuery.data || []).filter(
    (asset) => asset.asset_type === "image" || asset.asset_type === "video",
  );

  const availableTemplates = React.useMemo(
    () => templates.filter((template) => {
      const matchesAspect = template.aspect_ratio === projectAspect ||
        (!template.aspect_ratio && projectAspect === "9:16");
      return matchesAspect && template.supported_content_modes.includes(contentMode);
    }),
    [contentMode, projectAspect, templates],
  );
  const selectedTemplate = availableTemplates.find((template) => template.id === selectedTemplateId);
  const usesAiVisualStyle = contentMode === "generated_image" || contentMode === "generated_video";
  const projectTemplateId = selectedProject?.template?.template_id || "";

  React.useEffect(() => {
    if (createdProposal && !localProposal) {
      const options = createdProposal.generation_options || {};
      const count = Number(options.target_scene_count ?? 8);
      const speed = Number(options.voice_speed ?? options.speed ?? 1.0);
      const volume = Number(options.bgm_volume ?? 0.2);
      const savedVoiceId = typeof options.voice_id === "string"
        ? options.voice_id
        : selectedProject?.default_voice_id || "";

      setAngle(createdProposal.angle || "");
      const brief = createdProposal.knowledge_brief;
      const legacyBrief = createdProposal.content_brief;
      setKnowledgeAudience(brief?.audience || legacyBrief?.audience || "");
      setKnowledgeThesis(brief?.thesis || legacyBrief?.thesis || legacyBrief?.angle || "");
      setKnowledgeViewerTakeaway(brief?.viewer_takeaway || legacyBrief?.viewer_takeaway || legacyBrief?.goal || "");
      setSceneCount(Number.isFinite(count) ? Math.max(8, Math.min(20, count)) : 8);
      setEnableResearch(options.enable_research !== false);
      setContentMode(isContentMode(options.content_mode) ? options.content_mode : "generated_image");
      setSelectedTemplateId(typeof options.template_id === "string" ? options.template_id : "");
      setTaskGenre(typeof options.genre === "string" ? options.genre : "auto");
      setTaskHookType(typeof options.hook_type === "string" ? options.hook_type : "auto");
      setTaskStylePreset(typeof options.style_preset === "string" ? options.style_preset : "stick_figure");
      setCustomPromptPrefix(typeof options.prompt_prefix === "string" ? options.prompt_prefix : "");
      setTaskVoiceId(savedVoiceId);
      setTaskSpeed(Number.isFinite(speed) ? Math.max(0.5, Math.min(2, speed)) : 1.0);
      setBgmEnabled(options.bgm_enabled !== false);
      setBgmAssetId(typeof options.bgm_asset_id === "string"
        ? options.bgm_asset_id
        : selectedProject?.bgm_asset_id || "");
      setBgmVolume(Number.isFinite(volume) ? Math.max(0, Math.min(0.5, volume)) : 0.2);
      setSourceAssetId(typeof options.source_asset_id === "string" ? options.source_asset_id : "");
    }
  }, [createdProposal, localProposal, selectedProject]);

  React.useEffect(() => {
    if (!hasSelectedProject || templatesQuery.isLoading) return;
    if (availableTemplates.length === 0) {
      if (selectedTemplateId) setSelectedTemplateId("");
      return;
    }
    if (availableTemplates.some((template) => template.id === selectedTemplateId)) return;

    const preferredTemplateIds = [
      proposal?.generation_options?.template_id,
      projectTemplateId,
    ].filter((value): value is string => typeof value === "string" && value.length > 0);
    const preferredTemplate = availableTemplates.find((template) => preferredTemplateIds.includes(template.id));
    setSelectedTemplateId((preferredTemplate || availableTemplates[0]).id);
  }, [
    availableTemplates,
    hasSelectedProject,
    projectTemplateId,
    proposal,
    selectedTemplateId,
    templatesQuery.isLoading,
  ]);

  // 2. 投产或保存
  type TrendAction = "create" | "generate";
  const actionMutation = useMutation<TrendProposalActionResponse, Error, TrendAction>({
    mutationFn: async (action) => {
      if (!proposal) throw new Error("选题方案尚未就绪。");
      if (templatesQuery.isLoading) throw new Error("正在加载排版模板，请稍后再试。");
      if (!selectedTemplateId || !selectedTemplate) {
        throw new Error("当前画面来源没有可用的排版模板，请切换画面来源。");
      }
      if (contentMode === "uploaded_asset" && !sourceAssetId) {
        throw new Error("我的素材模式必须选择一项图片或视频素材。");
      }
      let current = proposal;
      const nextOptions = buildGenerationOptions(
        {
          targetSceneCount: sceneCount,
          enableResearch,
          contentMode,
          templateId: selectedTemplateId,
          genre: taskGenre,
          hookType: taskHookType,
          stylePreset: taskStylePreset,
          promptPrefix: customPromptPrefix.trim(),
          voiceId: taskVoiceId,
          speed: taskSpeed,
          bgmEnabled,
          bgmAssetId,
          bgmVolume,
          sourceAssetId,
        },
        current.generation_options,
      );
      const currentBrief = current.knowledge_brief || current.content_brief;
      const legacyCurrentBrief = current.content_brief;
      const currentKnowledgeBrief = current.knowledge_brief;
      const nextKnowledgeBrief: KnowledgeBrief = {
        audience: knowledgeAudience.trim(),
        thesis: knowledgeThesis.trim() || angle.trim(),
        viewer_takeaway: knowledgeViewerTakeaway.trim(),
        key_claims: currentBrief?.key_claims || [],
        source_refs: currentBrief?.source_refs || [],
        genre: taskGenre,
      };
      const existingKnowledgeBrief = currentKnowledgeBrief
        ? {
            audience: currentKnowledgeBrief.audience || "",
            thesis: currentKnowledgeBrief.thesis || "",
            viewer_takeaway: currentKnowledgeBrief.viewer_takeaway || "",
            key_claims: currentKnowledgeBrief.key_claims || [],
            source_refs: currentKnowledgeBrief.source_refs || [],
            genre: currentKnowledgeBrief.genre || "auto",
          }
        : {
            audience: legacyCurrentBrief?.audience || "",
            thesis: legacyCurrentBrief?.thesis || legacyCurrentBrief?.angle || "",
            viewer_takeaway: legacyCurrentBrief?.viewer_takeaway || legacyCurrentBrief?.goal || "",
            key_claims: legacyCurrentBrief?.key_claims || [],
            source_refs: legacyCurrentBrief?.source_refs || [],
            genre: legacyCurrentBrief?.genre || "auto",
          };
      const briefChanged = JSON.stringify(nextKnowledgeBrief) !== JSON.stringify(existingKnowledgeBrief);
      if (angle.trim() !== current.angle || JSON.stringify(nextOptions) !== JSON.stringify(current.generation_options) || briefChanged) {
        current = await api.updateTrendProposal(current.id, {
          expected_revision: current.revision,
          angle: angle.trim() || current.angle,
          knowledge_brief: nextKnowledgeBrief,
          generation_options: nextOptions,
        });
        setLocalProposal(current);
      }
      return action === "create"
        ? api.approveTrendProposal(current.id, current.revision)
        : api.approveAndRunTrendProposal(current.id, current.revision);
    },
    onSuccess: (data, action) => {
      setLocalProposal(data.proposal);
      if (action === "create") {
        toast("任务草稿已保存", "success");
      } else if (data.queue_status === "queued") {
        toast("已创建任务并进入生成流水线", "success");
      } else {
        toast(data.queue_error || "任务已创建，暂未进入队列", "warning");
      }
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["project", data.proposal.project_id] });
      queryClient.invalidateQueries({ queryKey: ["project-tasks", data.proposal.project_id] });
      queryClient.invalidateQueries({ queryKey: ["all-tasks"] });
    },
    onError: (error) => {
      toast(error.message || "操作失败，请重试", "error");
    },
  });

  // 3. 暂不采用
  const rejectMutation = useMutation({
    mutationFn: () => {
      if (!proposal) throw new Error("选题方案尚未就绪。");
      return api.rejectTrendProposal(proposal.id, proposal.revision);
    },
    onSuccess: (data) => {
      setLocalProposal(data);
      toast("已记录暂不采用", "default");
    },
    onError: (error) => {
      toast(error instanceof Error ? error.message : "操作失败", "error");
    },
  });

  const isWorking = isProposalPending || actionMutation.isPending || rejectMutation.isPending;
  const taskCreated = proposal?.status === "task_created" || proposal?.status === "queue_failed";
  const proposalClosed = taskCreated || proposal?.status === "rejected";
  const actionInProgress = actionMutation.variables;
  const platformConfig = PLATFORMS_CONFIG[item.platform] || { badgeClass: "bg-secondary text-foreground", dotClass: "bg-primary" };
  const canSubmitGeneration = Boolean(
    proposal &&
    !templatesQuery.isLoading &&
    selectedTemplate &&
    (contentMode !== "uploaded_asset" || sourceAssetId),
  );

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()} side="right">
      <SheetHeader>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className={cn("inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold border", platformConfig.badgeClass)}>
            <span className={cn("h-1.5 w-1.5 rounded-full", platformConfig.dotClass)} />
            {platform}
          </span>
          <Badge variant="outline" className="font-mono text-xs">
            排名 {item.rank > 0 ? `#${item.rank}` : "—"}
          </Badge>
          <StatusBadge label={sourceLabel(item.source_status)} tone={sourceTone(item.source_status)} showDot={false} />
        </div>
        <SheetTitle>{item.title}</SheetTitle>
        <SheetDescription>
          热点只是输入源；确认受众、主张和观众价值后，创建一条知识视频任务。
        </SheetDescription>
      </SheetHeader>

      <SheetContent>
        {/* 数据指标 */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-border/80 bg-secondary/35 p-3">
            <span className="text-xs text-muted-foreground">原始热度</span>
            <div className="mt-1 font-mono text-base font-bold tabular-nums text-foreground">
              {formatMetric(item)}
            </div>
          </div>
          <div className="rounded-xl border border-border/80 bg-secondary/35 p-3">
            <span className="text-xs text-muted-foreground">采集时间</span>
            <div className="mt-1 text-sm font-semibold text-foreground">
              {item.fetched_at ? formatDate(item.fetched_at) : "最新快照"}
            </div>
          </div>
        </div>

        {/* 创作项目 */}
        <section className="rounded-xl border border-primary/20 bg-primary/5 p-3.5" aria-labelledby="target-project-label">
          <div className="mb-2 flex items-center justify-between">
            <h3 id="target-project-label" className="text-sm font-semibold text-foreground">
              创作项目
            </h3>
            {item.project_relevance && item.project_relevance !== "unknown" && (
              <StatusBadge
                label={RELATION_LABELS[item.project_relevance]}
                tone={relationTone(item.project_relevance)}
                showDot={false}
              />
            )}
          </div>

          {projectsLoading ? (
            <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
              <span>读取项目空间…</span>
            </div>
          ) : projectsError ? (
            <div className="flex items-center justify-between gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
              <span>项目列表读取失败</span>
              <Button size="sm" variant="outline" onClick={onProjectsRetry}>重试</Button>
            </div>
          ) : projects.length > 0 ? (
            <Select
              id="sheet-project-select"
              value={projectId}
              onChange={(event) => {
                setLocalProposal(null);
                onProjectChange(event.target.value);
              }}
              disabled={Boolean(proposal) || isWorking}
            >
              <option value="all">选择项目空间…</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name} ({project.aspect_ratio})
                </option>
              ))}
            </Select>
          ) : (
            <div className="space-y-1 text-xs text-muted-foreground">
              <p>暂无可用项目空间。</p>
              <Link href="/projects" className="inline-flex items-center font-medium text-primary hover:underline">
                新建项目空间 <ArrowRight className="ml-1 h-3 w-3" />
              </Link>
            </div>
          )}
        </section>

        {/* 来源与风险提示 */}
        <div className="space-y-1.5 rounded-xl border border-border/70 bg-card/40 p-3 text-xs text-muted-foreground">
          <div className="flex items-start justify-between gap-2">
            <p className="flex items-center gap-1.5">
              <ShieldAlert className="h-3.5 w-3.5 shrink-0 text-warning" />
              <span>提示：<strong className="font-medium text-foreground">{item.risk_note || "请核对事实后合规发布。"}</strong></span>
            </p>
            {sourceUrl && (
              <a
                href={sourceUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-primary hover:underline shrink-0"
              >
                <span>查看原文</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        </div>

        {/* 方案编辑工作区 */}
        {!hasSelectedProject ? (
          <div className="rounded-xl border border-dashed border-border/80 bg-secondary/20 p-5 text-center">
            <Sparkles className="mx-auto h-6 w-6 text-primary/80" />
            <p className="mt-2 text-xs text-muted-foreground">
              请先在上方指定创作项目，系统将自动匹配模板并生成方案。
            </p>
          </div>
        ) : isProposalPending ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-border/70 bg-card/40 p-8 text-center space-y-2">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <p className="text-xs text-muted-foreground">正在提取创作方案…</p>
          </div>
        ) : isProposalError ? (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-xs text-destructive space-y-2">
            <p>方案提取失败，可能是热点不在最新快照中。</p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => createProposal({ projectId, trendItemId: item.id })}
            >
              重试
            </Button>
          </div>
        ) : proposal ? (
          <section className="space-y-3.5 rounded-xl border border-border/80 bg-card/60 p-4" aria-labelledby="proposal-heading">
            <div className="flex items-center justify-between border-b border-border/60 pb-2.5">
              <h3 id="proposal-heading" className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                <Sparkles className="h-3.5 w-3.5 text-primary" />
                选题方案
              </h3>
              <StatusBadge
                label={
                  proposal.status === "rejected"
                    ? "已暂不采用"
                    : taskCreated
                    ? proposal.status === "queue_failed"
                      ? "排队未完成"
                      : "已创建任务"
                    : "待确认"
                }
                tone={
                  proposal.status === "rejected"
                    ? "neutral"
                    : taskCreated
                    ? proposal.status === "queue_failed"
                      ? "warning"
                      : "success"
                    : "primary"
                }
                showDot={false}
              />
            </div>

            {/* Knowledge Brief */}
            <div className="space-y-3 rounded-lg border border-primary/20 bg-primary/5 p-3">
              <div>
                <p className="text-xs font-semibold text-foreground">知识视频 Brief</p>
                <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
                  这些字段会沿着脚本和分镜保存，帮助画面服务于信息逻辑。
                </p>
              </div>
              <Field label="面向谁" htmlFor="proposal-audience-input">
                <Input
                  id="proposal-audience-input"
                  value={knowledgeAudience}
                  onChange={(event) => setKnowledgeAudience(event.target.value)}
                  disabled={proposalClosed || isWorking}
                  placeholder="例如：第一次接触这个话题的普通观众"
                />
              </Field>
              <Field label="核心主张" htmlFor="proposal-thesis-input">
                <Textarea
                  id="proposal-thesis-input"
                  value={knowledgeThesis}
                  onChange={(event) => setKnowledgeThesis(event.target.value)}
                  rows={2}
                  disabled={proposalClosed || isWorking}
                  placeholder="一句话说清这条视频希望观众理解什么"
                />
              </Field>
              <Field label="观众看完带走什么" htmlFor="proposal-takeaway-input">
                <Textarea
                  id="proposal-takeaway-input"
                  value={knowledgeViewerTakeaway}
                  onChange={(event) => setKnowledgeViewerTakeaway(event.target.value)}
                  rows={2}
                  disabled={proposalClosed || isWorking}
                  placeholder="例如：能用一个例子解释热点背后的机制"
                />
              </Field>
            </div>

            {/* Angle remains a compatibility field and feeds the thesis when needed. */}
            <Field label="知识切入角度" htmlFor="proposal-angle-input">
              <Textarea
                id="proposal-angle-input"
                value={angle}
                onChange={(e) => setAngle(e.target.value)}
                rows={2}
                disabled={proposalClosed || isWorking}
                placeholder="输入视频叙事切入点..."
              />
            </Field>

            {/* 关键要点 */}
            {proposal.content_brief.key_points && proposal.content_brief.key_points.length > 0 && (
              <div className="space-y-1.5 text-xs">
                <span className="font-medium text-muted-foreground">关键要点：</span>
                <div className="flex flex-wrap gap-1.5">
                  {proposal.content_brief.key_points.map((pt, idx) => (
                    <span key={idx} className="rounded-md border border-border/80 bg-secondary/40 px-2 py-0.5 text-foreground text-[11px]">
                      {pt}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 生成规划 */}
            <div className="space-y-2.5 rounded-lg border border-border/60 bg-secondary/20 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-foreground">知识视频生成规划</span>
                <span className="font-mono text-[11px] font-medium text-primary">
                  目标 {sceneCount} 镜 · 约 {sceneCount * 4} 秒
                </span>
              </div>
              <div className="grid grid-cols-5 gap-1.5">
                {SCENE_COUNT_PRESETS.map((preset) => (
                  <button
                    key={preset.count}
                    type="button"
                    onClick={() => setSceneCount(preset.count)}
                    aria-pressed={sceneCount === preset.count}
                    disabled={proposalClosed || isWorking}
                    className={cn(
                      "rounded-md border px-1 py-1.5 text-center transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                      sceneCount === preset.count
                        ? "border-primary bg-primary text-primary-foreground shadow-xs"
                        : "border-border bg-card text-muted-foreground hover:bg-secondary hover:text-foreground",
                    )}
                  >
                    <span className="block font-mono text-xs font-semibold">{preset.label}</span>
                    <span className="mt-0.5 block text-[10px] opacity-80">{preset.desc.split(" ")[0]}</span>
                  </button>
                ))}
              </div>
              <label
                htmlFor="trend-research"
                className="flex cursor-pointer items-center justify-between rounded-md border border-border/70 bg-card/50 px-2.5 py-2 text-xs text-muted-foreground transition-colors hover:bg-secondary/45"
              >
                <span className="flex items-center gap-1.5">
                  <Search className="h-3.5 w-3.5 text-primary" />
                  前置研究（补充背景资料）
                </span>
                <input
                  id="trend-research"
                  type="checkbox"
                  className="h-4 w-4 cursor-pointer rounded border-border accent-primary"
                  checked={enableResearch}
                  onChange={(e) => setEnableResearch(e.target.checked)}
                  disabled={proposalClosed || isWorking}
                />
              </label>
            </div>

            {/* 与知识视频任务共用的生成设置 */}
            <div className="space-y-3 rounded-lg border border-primary/20 bg-primary/5 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-foreground">知识视频设置</span>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <Field
                  label="画面来源"
                  htmlFor="trend-content-mode"
                  description={CONTENT_MODE_SPECS[contentMode].selectionHint}
                >
                  <Select
                    id="trend-content-mode"
                    value={contentMode}
                    onChange={(event) => setContentMode(event.target.value as ContentMode)}
                    disabled={proposalClosed || isWorking}
                  >
                    {CONTENT_MODE_GROUPS.map((group) => (
                      <optgroup key={group.value} label={group.label}>
                        {group.modes.map((mode) => (
                          <option key={mode} value={mode}>{CONTENT_MODE_SPECS[mode].label}</option>
                        ))}
                      </optgroup>
                    ))}
                  </Select>
                </Field>

                <Field
                  label={
                    <span className="flex items-center justify-between gap-2">
                      <span>排版模板</span>
                      <Badge variant="outline" className="h-4 px-1.5 py-0 font-mono text-[10px] text-muted-foreground">
                        {projectAspect} 画幅
                      </Badge>
                    </span>
                  }
                  htmlFor="trend-template"
                >
                  <Select
                    id="trend-template"
                    value={selectedTemplateId}
                    onChange={(event) => setSelectedTemplateId(event.target.value)}
                    disabled={proposalClosed || isWorking || templatesQuery.isLoading || availableTemplates.length === 0}
                  >
                    {templatesQuery.isLoading ? (
                      <option value="">正在加载模板…</option>
                    ) : availableTemplates.length === 0 ? (
                      <option value="">当前来源暂无匹配模板</option>
                    ) : (
                      availableTemplates.map((template) => (
                        <option key={template.id} value={template.id}>
                          {formatTemplateName(template.id, template.name)}
                        </option>
                      ))
                    )}
                  </Select>
                  {templatesQuery.isError ? (
                    <p className="flex items-center gap-1 text-[11px] text-destructive">
                      <span>模板读取失败</span>
                      <button type="button" onClick={() => void templatesQuery.refetch()} className="underline">重试</button>
                    </p>
                  ) : !templatesQuery.isLoading && availableTemplates.length === 0 ? (
                    <p className="text-[11px] text-warning">切换画面来源后可选择其他模板。</p>
                  ) : null}
                </Field>

                <Field label="知识方向" htmlFor="trend-genre">
                  <Select
                    id="trend-genre"
                    value={taskGenre}
                    onChange={(event) => setTaskGenre(event.target.value)}
                    disabled={proposalClosed || isWorking}
                  >
                    {GENRE_OPTIONS.map((genre) => (
                      <option key={genre.value} value={genre.value}>{genre.label}</option>
                    ))}
                  </Select>
                </Field>

                <Field label="开场钩子" htmlFor="trend-hook">
                  <Select
                    id="trend-hook"
                    value={taskHookType}
                    onChange={(event) => setTaskHookType(event.target.value)}
                    disabled={proposalClosed || isWorking}
                  >
                    {HOOK_OPTIONS.map((hook) => (
                      <option key={hook.value} value={hook.value}>{hook.label}</option>
                    ))}
                  </Select>
                </Field>
              </div>

              {contentMode === "uploaded_asset" && (
                <Field label="绑定我的素材" htmlFor="trend-source-asset" required>
                  <Select
                    id="trend-source-asset"
                    value={sourceAssetId}
                    onChange={(event) => setSourceAssetId(event.target.value)}
                    disabled={proposalClosed || isWorking || sourceAssetsQuery.isLoading}
                  >
                    <option value="">
                      {sourceAssetsQuery.isLoading ? "正在加载项目素材…" : "请选择图片或视频素材"}
                    </option>
                    {sourceAssets.map((asset) => (
                      <option key={asset.id} value={asset.id}>
                        {asset.file_name}（{ASSET_TYPE_LABELS[asset.asset_type] || asset.asset_type}）
                      </option>
                    ))}
                  </Select>
                  {!sourceAssetsQuery.isLoading && sourceAssets.length === 0 && (
                    <p className="text-[11px] text-warning">当前项目暂无可绑定的图片或视频素材。</p>
                  )}
                </Field>
              )}

              {usesAiVisualStyle && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="视觉风格" htmlFor="trend-style-preset">
                    <Select
                      id="trend-style-preset"
                      value={taskStylePreset}
                      onChange={(event) => setTaskStylePreset(event.target.value)}
                      disabled={proposalClosed || isWorking}
                    >
                      {STYLE_PRESET_OPTIONS.map((style) => (
                        <option key={style.value} value={style.value}>{style.label}</option>
                      ))}
                    </Select>
                  </Field>
                  {taskStylePreset === "custom" && (
                    <Field label="自定义风格提示" htmlFor="trend-custom-style">
                      <Input
                        id="trend-custom-style"
                        value={customPromptPrefix}
                        onChange={(event) => setCustomPromptPrefix(event.target.value)}
                        placeholder="例如：复古胶片、低饱和纪实"
                        disabled={proposalClosed || isWorking}
                      />
                    </Field>
                  )}
                </div>
              )}

              <div className="grid gap-3 border-t border-primary/15 pt-3 sm:grid-cols-2">
                <Field label={<span className="flex items-center gap-1.5"><Volume2 className="h-3.5 w-3.5 text-primary" />旁白音色</span>} htmlFor="trend-voice">
                  <Select
                    id="trend-voice"
                    value={taskVoiceId}
                    onChange={(event) => setTaskVoiceId(event.target.value)}
                    disabled={proposalClosed || isWorking}
                  >
                    <option value="">使用系统默认音色</option>
                    {taskVoiceId && !taskVoices.some((voice) => voice.id === taskVoiceId) && (
                      <option value={taskVoiceId}>{taskVoiceId}</option>
                    )}
                    {taskVoices.map((voice) => (
                      <option key={voice.id} value={voice.id}>{voice.name} · {voice.locale}</option>
                    ))}
                  </Select>
                  {voicesQuery.isLoading ? (
                    <p className="text-[11px] text-muted-foreground">正在加载音色…</p>
                  ) : voicesQuery.isError ? (
                    <p className="flex items-center gap-1 text-[11px] text-destructive">
                      <span>音色列表读取失败，将使用系统默认音色。</span>
                      <button type="button" onClick={() => void voicesQuery.refetch()} className="underline">重试</button>
                    </p>
                  ) : null}
                </Field>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium leading-none text-foreground">语速</span>
                    <span className="font-mono text-[11px] text-muted-foreground">{taskSpeed.toFixed(1)}x</span>
                  </div>
                  <div className="flex items-center gap-1.5 pt-1">
                    {SPEED_PRESETS.map((speed) => (
                      <button
                        key={speed}
                        type="button"
                        onClick={() => setTaskSpeed(speed)}
                        aria-pressed={Math.abs(taskSpeed - speed) < 0.05}
                        disabled={proposalClosed || isWorking}
                        className={cn(
                          "flex-1 rounded-md border py-1.5 font-mono text-[11px] transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                          Math.abs(taskSpeed - speed) < 0.05
                            ? "border-primary bg-primary text-primary-foreground shadow-xs"
                            : "border-border bg-card text-muted-foreground hover:bg-secondary hover:text-foreground",
                        )}
                      >
                        {speed}x
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* 背景音乐 */}
            <div className="space-y-2.5 rounded-lg border border-border/60 bg-secondary/20 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                  <Music className="h-3.5 w-3.5 text-primary" />
                  背景音乐
                </span>
                <label htmlFor="trend-bgm-toggle" className="flex cursor-pointer items-center gap-1.5 text-[11px] text-muted-foreground">
                  <input
                    id="trend-bgm-toggle"
                    type="checkbox"
                    checked={bgmEnabled}
                    onChange={(event) => setBgmEnabled(event.target.checked)}
                    disabled={proposalClosed || isWorking}
                    className="h-4 w-4 cursor-pointer rounded border-border accent-primary"
                  />
                  启用
                </label>
              </div>
              {bgmEnabled && (
                <div className="space-y-2 rounded-md border border-border/70 bg-card/50 p-2.5">
                  <Select
                    id="trend-bgm-select"
                    value={bgmAssetId}
                    onChange={(event) => setBgmAssetId(event.target.value)}
                    disabled={proposalClosed || isWorking || bgmQuery.isLoading}
                  >
                    <option value="">使用项目默认背景音乐</option>
                    {projectBgm.map((asset) => (
                      <option key={asset.id} value={asset.id}>{asset.file_name}</option>
                    ))}
                  </Select>
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                    <span className="shrink-0">音量</span>
                    <input
                      type="range"
                      min="0"
                      max="0.5"
                      step="0.01"
                      value={bgmVolume}
                      onChange={(event) => setBgmVolume(Number(event.target.value))}
                      disabled={proposalClosed || isWorking}
                      className="h-1.5 flex-1 cursor-pointer appearance-none rounded-lg bg-secondary accent-primary disabled:cursor-not-allowed"
                    />
                    <span className="w-8 text-right font-mono font-medium text-foreground">{bgmVolume.toFixed(2)}</span>
                  </div>
                </div>
              )}
            </div>
          </section>
        ) : null}
      </SheetContent>

      <SheetFooter>
        {!hasSelectedProject ? (
          <p className="text-center text-xs text-muted-foreground">请在上方选择创作项目</p>
        ) : proposal?.status === "rejected" ? (
          <div className="rounded-lg border border-border/70 bg-secondary/35 p-2.5 text-center text-xs text-muted-foreground">
            该选题已被标记为暂不采用。
          </div>
        ) : taskCreated ? (
          <div className="space-y-2">
            <div className={cn("rounded-lg border p-2.5 text-xs text-center", proposal.status === "queue_failed" ? "border-warning/30 bg-warning/10 text-warning" : "border-success/30 bg-success/10 text-success")}>
              {proposal.status === "queue_failed"
                ? "任务已保存，排队暂未完成。"
                : "任务已创建并进入流水线。"}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onClose}
              >
                继续挑选
              </Button>
              {proposal.task_id ? (
                <Link
                  href={`/projects/${proposal.project_id}/tasks/${proposal.task_id}`}
                  className="inline-flex items-center justify-center rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow-xs hover:bg-primary/90"
                >
                  <span>进入故事板</span>
                  <ArrowRight className="ml-1 h-3.5 w-3.5" />
                </Link>
              ) : null}
            </div>
          </div>
        ) : proposal ? (
          <div className="space-y-2">
            {!canSubmitGeneration && (
              <p className="rounded-md border border-warning/25 bg-warning/10 px-2.5 py-2 text-center text-[11px] text-warning">
                {templatesQuery.isLoading
                  ? "正在准备排版模板…"
                  : contentMode === "uploaded_asset" && !sourceAssetId
                  ? "请选择要绑定的图片或视频素材。"
                  : "当前画面来源没有匹配模板，请切换来源后再试。"}
              </p>
            )}
            <div className="grid grid-cols-2 gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => actionMutation.mutate("create")}
                disabled={isWorking || !canSubmitGeneration}
                className="gap-1.5"
              >
                {actionMutation.isPending && actionInProgress === "create" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                保存草稿
              </Button>
              <Button
                type="button"
                onClick={() => actionMutation.mutate("generate")}
                disabled={isWorking || !canSubmitGeneration}
                className="gap-1.5 shadow-xs"
              >
                {actionMutation.isPending && actionInProgress === "generate" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5 fill-current" />}
                开始生成
              </Button>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => rejectMutation.mutate()}
              disabled={isWorking}
              className="w-full text-xs text-muted-foreground hover:text-foreground h-7"
            >
              {rejectMutation.isPending ? "记录中…" : "暂不采用"}
            </Button>
          </div>
        ) : null}
        <p className="text-center text-[11px] text-muted-foreground">
          生成完成后可在故事板选择发布方式。
        </p>
      </SheetFooter>
    </Sheet>
  );
}

// 关键词规则组件
function parsePreferenceTerms(value: string) {
  return Array.from(
    new Set(value.split(/[,，\s、]+/).map((term) => term.trim()).filter(Boolean)),
  ).slice(0, 100);
}

function TrendPreferencesCard({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [includeText, setIncludeText] = React.useState("");
  const [excludeText, setExcludeText] = React.useState("");

  const preferencesQuery = useQuery({
    queryKey: ["trend-preferences", projectId],
    queryFn: () => api.getTrendPreferences(projectId),
    enabled: Boolean(projectId && projectId !== "all"),
  });

  React.useEffect(() => {
    if (!preferencesQuery.data) return;
    setIncludeText(preferencesQuery.data.include_keywords.join("、"));
    setExcludeText(preferencesQuery.data.exclude_keywords.join("、"));
  }, [preferencesQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateTrendPreferences(projectId, {
        include_keywords: parsePreferenceTerms(includeText),
        exclude_keywords: parsePreferenceTerms(excludeText),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["trend-preferences", projectId], data);
      queryClient.invalidateQueries({ queryKey: ["trends"] });
      toast("关联规则已保存", "success");
    },
    onError: () => {
      toast("保存失败，请重试", "error");
    },
  });

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    saveMutation.mutate();
  };

  const parsedIncludes = React.useMemo(() => parsePreferenceTerms(includeText), [includeText]);
  const parsedExcludes = React.useMemo(() => parsePreferenceTerms(excludeText), [excludeText]);

  return (
    <Card className="glass-card">
      <CardHeader className="border-b border-border/60 pb-3.5">
        <CardTitle className="text-base flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          关联规则
        </CardTitle>
        <CardDescription>
          设置关键词评估热点与本项目的关联度，多个词用逗号或空格分隔。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 p-4 sm:p-5">
        {preferencesQuery.isLoading ? (
          <div className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            <span>读取规则…</span>
          </div>
        ) : preferencesQuery.isError ? (
          <div className="flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/10 p-2.5 text-xs text-destructive">
            <span>读取失败</span>
            <Button size="sm" variant="outline" onClick={() => preferencesQuery.refetch()}>重试</Button>
          </div>
        ) : (
          <form className="space-y-3.5" onSubmit={handleSubmit}>
            <div className="grid gap-3.5 md:grid-cols-2">
              <div className="space-y-1.5">
                <Field
                  label="包含词"
                  htmlFor="trend-include-keywords"
                  description="命中 2 个及以上为高关联，1 个为中关联"
                >
                  <Input
                    id="trend-include-keywords"
                    value={includeText}
                    onChange={(e) => setIncludeText(e.target.value)}
                    placeholder="例如：AI、科技、效率"
                    disabled={saveMutation.isPending}
                  />
                </Field>
                {parsedIncludes.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-0.5">
                    {parsedIncludes.map((term, i) => (
                      <span key={i} className="inline-flex items-center rounded-md bg-primary/10 border border-primary/20 px-2 py-0.5 text-[11px] font-medium text-primary">
                        +{term}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-1.5">
                <Field
                  label="排除词"
                  htmlFor="trend-exclude-keywords"
                  description="命中后标为低关联"
                >
                  <Input
                    id="trend-exclude-keywords"
                    value={excludeText}
                    onChange={(e) => setExcludeText(e.target.value)}
                    placeholder="例如：抽奖、广告"
                    disabled={saveMutation.isPending}
                  />
                </Field>
                {parsedExcludes.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-0.5">
                    {parsedExcludes.map((term, i) => (
                      <span key={i} className="inline-flex items-center rounded-md bg-destructive/10 border border-destructive/20 px-2 py-0.5 text-[11px] font-medium text-destructive">
                        -{term}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center justify-end pt-1">
              <Button type="submit" size="sm" disabled={saveMutation.isPending} className="gap-1.5 shadow-xs">
                {saveMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                保存规则
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

// 自动采集订阅组件
const SUBSCRIPTION_STATUS_LABELS: Record<string, string> = {
  active: "运行中",
  running: "采集中",
  paused: "已暂停",
  stale: "部分过期",
  failed: "失败",
  unavailable: "不可用",
};

function TrendSubscriptionCard({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [frequency, setFrequency] = React.useState<TrendSubscription["frequency"]>("1h");
  const [timezone, setTimezone] = React.useState("Asia/Shanghai");

  const subscriptionsQuery = useQuery({
    queryKey: ["trend-subscriptions", projectId],
    queryFn: () => api.listTrendSubscriptions(projectId),
    enabled: Boolean(projectId && projectId !== "all"),
  });
  const subscription = subscriptionsQuery.data?.[0];

  React.useEffect(() => {
    if (!subscription) return;
    setFrequency(subscription.frequency);
    setTimezone(subscription.timezone);
  }, [subscription]);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["trend-subscriptions", projectId] });
    queryClient.invalidateQueries({ queryKey: ["trends"] });
  };

  const createMutation = useMutation({
    mutationFn: () => api.createTrendSubscription({ project_id: projectId, frequency, timezone }),
    onSuccess: () => {
      refresh();
      toast("自动采集已开启", "success");
    },
    onError: () => toast("开启失败，请重试", "error"),
  });

  const updateMutation = useMutation({
    mutationFn: () => api.updateTrendSubscription(subscription!.id, { frequency, timezone }),
    onSuccess: () => {
      refresh();
      toast("设置已保存", "success");
    },
    onError: () => toast("保存失败", "error"),
  });

  const actionMutation = useMutation({
    mutationFn: (action: "pause" | "resume" | "run") =>
      action === "pause"
        ? api.updateTrendSubscription(subscription!.id, { enabled: false })
        : action === "resume"
        ? api.updateTrendSubscription(subscription!.id, { enabled: true })
        : api.runTrendSubscription(subscription!.id),
    onSuccess: (_, action) => {
      refresh();
      if (action === "run") toast("已触发采集", "success");
      else if (action === "pause") toast("已暂停", "default");
      else toast("已恢复", "success");
    },
    onError: () => toast("操作失败", "error"),
  });

  const isWorking = subscriptionsQuery.isLoading || createMutation.isPending || updateMutation.isPending || actionMutation.isPending;

  return (
    <Card className="glass-card">
      <CardHeader className="border-b border-border/60 pb-3.5">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Clock3 className="h-4 w-4 text-primary" />
              自动采集
            </CardTitle>
            <CardDescription>
              按设定周期自动拉取公开热榜并更新关联度。
            </CardDescription>
          </div>
          {subscription && (
            <div className="flex items-center gap-2">
              <StatusBadge
                label={SUBSCRIPTION_STATUS_LABELS[subscription.status] || subscription.status}
                tone={subscription.status === "active" ? "success" : ["failed", "unavailable"].includes(subscription.status) ? "destructive" : "warning"}
                showDot={false}
              />
              <span className="text-xs text-muted-foreground font-mono">
                {TREND_FREQUENCY_LABELS[subscription.frequency]}
              </span>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3.5 p-4 sm:p-5">
        {subscriptionsQuery.isLoading ? (
          <div className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            <span>读取调度…</span>
          </div>
        ) : subscriptionsQuery.isError ? (
          <div className="flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/10 p-2.5 text-xs text-destructive">
            <span>读取失败</span>
            <Button size="sm" variant="outline" onClick={() => subscriptionsQuery.refetch()}>重试</Button>
          </div>
        ) : !subscription ? (
          <div className="space-y-3 rounded-xl border border-dashed border-border/80 bg-secondary/20 p-3.5">
            <p className="text-xs text-muted-foreground">尚未开启当前项目的自动采集。</p>
            <div className="grid gap-3 sm:grid-cols-2 pt-1">
              <Field label="采集频率" htmlFor="sub-freq-new">
                <Select id="sub-freq-new" value={frequency} onChange={(e) => setFrequency(e.target.value as TrendSubscription["frequency"])}>
                  {TREND_FREQUENCY_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </Select>
              </Field>
              <Field label="时区" htmlFor="sub-tz-new">
                <Input id="sub-tz-new" value={timezone} onChange={(e) => setTimezone(e.target.value)} />
              </Field>
            </div>
            <Button type="button" size="sm" onClick={() => createMutation.mutate()} disabled={isWorking} className="gap-1.5">
              {createMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Clock3 className="h-3.5 w-3.5" />}
              开启自动采集
            </Button>
          </div>
        ) : (
          <div className="space-y-3.5">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="周期频率" htmlFor="sub-freq-exist">
                <Select id="sub-freq-exist" value={frequency} onChange={(e) => setFrequency(e.target.value as TrendSubscription["frequency"])}>
                  {TREND_FREQUENCY_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </Select>
              </Field>
              <Field label="时区" htmlFor="sub-tz-exist">
                <Input id="sub-tz-exist" value={timezone} onChange={(e) => setTimezone(e.target.value)} />
              </Field>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2.5 border-t border-border/60 pt-3 text-xs text-muted-foreground">
              <div className="flex items-center gap-4">
                <span>下次：<strong className="font-mono text-foreground font-medium">{subscription.next_run_at ? formatDate(subscription.next_run_at) : "暂停"}</strong></span>
                <span>最近成功：<strong className="font-mono text-foreground font-medium">{subscription.last_success_at ? formatDate(subscription.last_success_at) : "无"}</strong></span>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => actionMutation.mutate(subscription.enabled ? "pause" : "resume")}
                  disabled={isWorking}
                >
                  {subscription.enabled ? "暂停" : "恢复"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => actionMutation.mutate("run")}
                  disabled={isWorking || !subscription.enabled}
                  className="gap-1.5"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  手动采集
                </Button>
                <Button
                  type="button"
                  size="sm"
                  onClick={() => updateMutation.mutate()}
                  disabled={isWorking}
                >
                  保存设置
                </Button>
              </div>
            </div>

            {subscription.last_error && (
              <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 p-2.5 text-xs text-warning">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                <span>异常：{subscription.last_error}</span>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}


// 主页面组件
export default function TrendsPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [activeTab, setActiveTab] = React.useState("discovery");
  const [requestedProjectId, setRequestedProjectId] = React.useState<string | null>(null);
  const [projectId, setProjectId] = React.useState("all");
  const [platform, setPlatform] = React.useState("all");
  const [freshness, setFreshness] = React.useState<TrendFreshness>("24h");
  const [searchText, setSearchText] = React.useState("");
  const [selectedTrend, setSelectedTrend] = React.useState<TrendItem | null>(null);
  const initialProjectSelectionDone = React.useRef(false);

  // 1. 项目列表
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects(),
  });
  const projects = projectsQuery.data || [];

  React.useEffect(() => {
    setRequestedProjectId(new URLSearchParams(window.location.search).get("project"));
  }, []);

  React.useEffect(() => {
    if (initialProjectSelectionDone.current || !projectsQuery.isFetched) return;
    if (requestedProjectId && projects.some((project) => project.id === requestedProjectId)) {
      setProjectId(requestedProjectId);
    } else if (!requestedProjectId && projects.length === 1) {
      setProjectId(projects[0].id);
    }
    initialProjectSelectionDone.current = true;
  }, [projects, projectsQuery.isFetched, requestedProjectId]);

  // 2. 热点 Feed
  const trendsQuery = useQuery<TrendFeedResponse>({
    queryKey: ["trends", { projectId, platform, freshness }],
    queryFn: () => api.listTrends({ projectId: projectId === "all" ? undefined : projectId, platform, freshness }),
    retry: false,
    placeholderData: keepPreviousData,
  });

  // 3. 来源状态与运行信息（用于顶部 Pulse 统计）
  const sourcesQuery = useQuery<TrendSourceCatalog[]>({
    queryKey: ["trend-sources"],
    queryFn: () => api.listTrendSources(),
  });
  const runsQuery = useQuery<TrendRun[]>({
    queryKey: ["trend-runs", 5],
    queryFn: () => api.listTrendRuns(5),
  });
  const subscriptionsQuery = useQuery({
    queryKey: ["trend-subscriptions", projectId],
    queryFn: () => api.listTrendSubscriptions(projectId === "all" ? undefined : projectId),
    enabled: projectId !== "all",
  });

  // 4. 手动全局刷新
  const refreshMutation = useMutation({
    mutationFn: () => api.refreshTrends({ platforms: platform === "all" ? [] : [platform] }),
    onSuccess: async (run) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["trends"] }),
        queryClient.invalidateQueries({ queryKey: ["trend-sources"] }),
        queryClient.invalidateQueries({ queryKey: ["trend-runs"] }),
        queryClient.invalidateQueries({ queryKey: ["trend-subscriptions"] }),
      ]);
      if (run.status === "completed") {
        toast(`已更新 ${run.success_count} 个平台热榜`, "success");
      } else {
        toast(`已更新，有 ${run.error_count + run.stale_count} 个来源异常`, "warning");
      }
    },
    onError: (error) => {
      toast(error instanceof Error ? `更新失败: ${error.message}` : "更新失败，请重试", "error");
    },
  });

  const feed = trendsQuery.data;
  const items = feed?.items || [];
  const normalizedSearch = searchText.trim().toLocaleLowerCase();
  const visibleItems = normalizedSearch
    ? items.filter((item) => item.title.toLocaleLowerCase().includes(normalizedSearch))
    : items;

  const unavailable = trendsQuery.isError || feed?.status === "unavailable";
  const stateMessage = unavailable
    ? trendsQuery.isError
      ? errorCopy(trendsQuery.error)
      : feed?.source_message || "热点来源暂时不可用。"
    : feed?.status === "stale"
    ? feed.source_message || "已返回最近一次成功快照，数据可能已过期。"
    : "";

  const handleProjectChange = (nextProjectId: string) => {
    setProjectId(nextProjectId);
    const params = new URLSearchParams(window.location.search);
    if (nextProjectId === "all") {
      params.delete("project");
    } else {
      params.set("project", nextProjectId);
    }
    const query = params.toString();
    window.history.replaceState(
      window.history.state,
      "",
      `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`,
    );
  };

  const hasActiveFilters = Boolean(
    projectId !== "all" || platform !== "all" || freshness !== "24h" || searchText.trim(),
  );

  const clearFilters = () => {
    handleProjectChange("all");
    setPlatform("all");
    setFreshness("24h");
    setSearchText("");
  };

  // Studio Pulse 指标统计
  const highRelevanceCount = items.filter((item) => item.project_relevance === "high" || item.project_relevance === "medium").length;
  const latestRun = runsQuery.data?.[0];
  const activeSubscription = subscriptionsQuery.data?.[0];

  return (
    <PageContainer width="wide" className="space-y-6">
      <PageHeader
        title="热点中心"
        description="浏览全网热榜，按项目偏好匹配选题并快速生成短视频。"
        actions={(
          <Button
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending}
            className="gap-1.5 h-9 px-3.5 text-sm shadow-xs"
          >
            {refreshMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {refreshMutation.isPending ? "正在更新…" : "更新热榜"}
          </Button>
        )}
      />

      {/* 1. Studio Pulse 脉搏指标概览带 */}
      <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
        {/* 卡片 1: 全网热点 */}
        <div className="rounded-xl glass-card p-4 sm:p-5 flex flex-col justify-between hover:border-primary/40 transition-all">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="font-medium">全网热点</span>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/15 text-primary shadow-xs">
              <Flame className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3.5 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-foreground tabular-nums">
              {items.length}
            </span>
            <span className="text-xs text-muted-foreground">条热榜</span>
          </div>
        </div>

        {/* 卡片 2: 关联选题 */}
        <div className="rounded-xl glass-card p-4 sm:p-5 flex flex-col justify-between hover:border-success/40 transition-all">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="font-medium">关联选题</span>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-success/15 text-success shadow-xs">
              <Sparkles className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3.5 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-foreground tabular-nums">
              {projectId === "all" ? "—" : highRelevanceCount}
            </span>
            <span className="text-xs text-muted-foreground">
              {projectId === "all" ? "未选项目" : "条高/中关联"}
            </span>
          </div>
        </div>

        {/* 卡片 3: 监控平台 */}
        <button
          type="button"
          onClick={() => setActiveTab("sources")}
          className="w-full rounded-xl glass-card p-4 sm:p-5 text-left flex flex-col justify-between hover:border-primary/40 transition-all cursor-pointer group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="font-medium group-hover:text-foreground transition-colors">监控平台</span>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary/70 text-foreground shadow-xs">
              <Globe className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3.5 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-foreground tabular-nums">
              {sourcesQuery.isLoading || sourcesQuery.isError ? "—" : sourcesQuery.data?.length ?? 0}
            </span>
            <span className="text-xs text-muted-foreground">个平台</span>
          </div>
        </button>

        {/* 卡片 4: 自动采集 */}
        <button
          type="button"
          onClick={() => setActiveTab("settings")}
          className="w-full rounded-xl glass-card p-4 sm:p-5 text-left flex flex-col justify-between hover:border-primary/40 transition-all cursor-pointer group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="font-medium group-hover:text-foreground transition-colors">自动采集</span>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary/70 text-foreground shadow-xs">
              <Clock3 className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3.5 flex items-baseline gap-1.5">
            <span className="font-mono text-xl sm:text-2xl font-bold tracking-tight text-foreground tabular-nums">
              {activeSubscription?.enabled ? TREND_FREQUENCY_LABELS[activeSubscription.frequency] : "未开启"}
            </span>
            <span className="text-xs text-muted-foreground">
              {activeSubscription?.enabled ? "定时运行中" : "可配置"}
            </span>
          </div>
        </button>
      </div>

      {/* 2. 工作区选项卡 */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="discovery" className="gap-1.5">
            <Flame className="h-3.5 w-3.5 text-primary" />
            <span>发现热点</span>
            {items.length > 0 && (
              <span className="ml-1 rounded-full bg-secondary/80 px-1.5 py-0.2 font-mono text-[11px] text-muted-foreground">
                {visibleItems.length}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="settings" className="gap-1.5">
            <Settings2 className="h-3.5 w-3.5" />
            <span>偏好与订阅</span>
          </TabsTrigger>
          <TabsTrigger value="sources" className="gap-1.5">
            <Activity className="h-3.5 w-3.5" />
            <span>来源监控</span>
            {latestRun?.error_count ? (
              <span className="ml-1 h-2 w-2 rounded-full bg-destructive" />
            ) : null}
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: 发现热点 */}
        <TabsContent value="discovery" className="space-y-4">
          <Card className="glass-card">
            <CardHeader className="border-b border-border/60 pb-4">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">热点列表</CardTitle>
                {hasActiveFilters && (
                  <button
                    type="button"
                    onClick={clearFilters}
                    className="inline-flex min-h-8 items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                  >
                    <X aria-hidden="true" className="h-3.5 w-3.5" />
                    重置筛选
                  </button>
                )}
              </div>

              {/* 筛选行 1：项目与搜索 */}
              <div className="grid gap-3 pt-2 md:grid-cols-[minmax(14rem,18rem)_minmax(0,1fr)]">
                <Field
                  label="创作项目"
                  htmlFor="trend-project"
                  description={projectId === "all" ? "选定后评估关联度" : "已匹配项目规则"}
                >
                  <Select id="trend-project" value={projectId} onChange={(e) => handleProjectChange(e.target.value)} disabled={projectsQuery.isLoading}>
                    <option value="all">全部项目 (浏览模式)</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>{p.name} ({p.aspect_ratio})</option>
                    ))}
                  </Select>
                </Field>

                <Field label="搜索热点" htmlFor="trend-search">
                  <SearchInput
                    id="trend-search"
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    onClear={() => setSearchText("")}
                    placeholder="输入关键词搜索..."
                  />
                </Field>
              </div>

              {/* 筛选行 2：平台与时间 */}
              <div className="grid gap-3 border-t border-border/60 pt-3 md:grid-cols-[minmax(0,1fr)_11rem]">
                <Field label="平台">
                  <div className="inline-flex flex-wrap gap-1.5 rounded-lg glass-pill p-1 shadow-xs" role="radiogroup" aria-label="热点平台筛选">
                    {PLATFORM_OPTIONS.map((opt) => {
                      const isActive = platform === opt.value;
                      return (
                        <button
                          key={opt.value}
                          type="button"
                          role="radio"
                          aria-checked={isActive}
                          onClick={() => setPlatform(opt.value)}
                          className={cn(
                            "inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-all cursor-pointer",
                            isActive
                              ? "bg-card text-foreground shadow-xs font-semibold"
                              : "text-muted-foreground hover:text-foreground hover:bg-card/40"
                          )}
                        >
                          {opt.value !== "all" && (
                            <span className={cn("h-1.5 w-1.5 rounded-full", opt.dotClass)} />
                          )}
                          <span>{opt.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </Field>

                <Field label="时间范围" htmlFor="trend-freshness">
                  <Select id="trend-freshness" value={freshness} onChange={(e) => setFreshness(e.target.value as TrendFreshness)}>
                    {FRESHNESS_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </Select>
                </Field>
              </div>
            </CardHeader>

            <CardContent className="space-y-3 p-4 sm:p-5">
              {/* 头部状态 */}
              <div className="flex flex-col gap-2 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
                <SectionHeader
                  title="热点列表"
                  description={items.length ? `${visibleItems.length} / ${items.length} 条` : ""}
                />
                <div className="flex items-center gap-2">
                  {feed?.fetched_at && (
                    <span className="font-mono tabular-nums text-[11px]">
                      采集时间: {formatDate(feed.fetched_at)}
                    </span>
                  )}
                  {feed?.status === "stale" && (
                    <StatusBadge label="快照可能过期" tone="warning" showDot={false} />
                  )}
                  {trendsQuery.isFetching && !trendsQuery.isLoading && (
                    <span className="inline-flex items-center gap-1 text-primary text-[11px]">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      刷新中
                    </span>
                  )}
                </div>
              </div>

              {/* 异常状态提示条 */}
              {stateMessage && (
                <div
                  className={cn(
                    "flex items-center justify-between rounded-xl border px-3.5 py-2.5 text-xs",
                    feed?.status === "stale" ? "border-warning/30 bg-warning/10 text-warning" : "border-destructive/30 bg-destructive/10 text-destructive"
                  )}
                >
                  <div className="flex items-center gap-2">
                    {feed?.status === "stale" ? (
                      <AlertTriangle className="h-4 w-4 shrink-0" />
                    ) : (
                      <WifiOff className="h-4 w-4 shrink-0" />
                    )}
                    <span>{stateMessage}</span>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 text-xs px-2"
                    onClick={() => setActiveTab("sources")}
                  >
                    来源状态 →
                  </Button>
                </div>
              )}

              {/* 列表内容 */}
              {trendsQuery.isLoading ? (
                <TrendSkeleton />
              ) : unavailable ? (
                <EmptyState
                  icon={WifiOff}
                  title="热点服务暂不可用"
                  description={stateMessage}
                  action={
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => trendsQuery.refetch()}
                      disabled={trendsQuery.isFetching}
                      className="gap-1.5"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      重试连接
                    </Button>
                  }
                />
              ) : items.length === 0 ? (
                <EmptyState
                  icon={Flame}
                  title="暂无热点"
                  description="当前筛选条件下未返回数据。"
                  action={
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => refreshMutation.mutate()}
                      disabled={refreshMutation.isPending}
                      className="gap-1.5"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      采集热榜
                    </Button>
                  }
                />
              ) : visibleItems.length === 0 ? (
                <EmptyState
                  icon={Search}
                  title="未找到相关热点"
                  description={`未找到包含“${searchText.trim()}”的条目。`}
                  action={
                    <Button variant="outline" size="sm" onClick={() => setSearchText("")}>
                      清除搜索
                    </Button>
                  }
                />
              ) : (
                <div className="space-y-2" aria-label="热点列表">
                  {visibleItems.map((item) => (
                    <TrendRow
                      key={`${item.id}-${item.platform}`}
                      item={item}
                      onSelect={setSelectedTrend}
                      showRelation={projectId !== "all"}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: 偏好与订阅 */}
        <TabsContent value="settings" className="space-y-4">
          {projectId === "all" ? (
            <Card className="glass-card">
              <CardContent className="p-8 text-center">
                <Settings2 className="mx-auto h-8 w-8 text-muted-foreground" />
                <h3 className="mt-3 text-base font-semibold text-foreground">请先选择项目空间</h3>
                <p className="mt-1 text-xs text-muted-foreground max-w-sm mx-auto">
                  关联规则与自动采集均绑定于特定项目。
                </p>
                <div className="mt-4 max-w-xs mx-auto">
                  <Select value={projectId} onChange={(e) => handleProjectChange(e.target.value)}>
                    <option value="all">选择项目空间…</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>{p.name} ({p.aspect_ratio})</option>
                    ))}
                  </Select>
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between rounded-xl border border-border/80 bg-card/50 px-3.5 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">当前项目：</span>
                  <strong className="text-sm font-semibold text-foreground">
                    {projects.find((p) => p.id === projectId)?.name || projectId}
                  </strong>
                </div>
                <Button size="sm" variant="ghost" onClick={() => handleProjectChange("all")} className="text-xs h-7">
                  切换项目
                </Button>
              </div>
              <TrendPreferencesCard key={`pref-${projectId}`} projectId={projectId} />
              <TrendSubscriptionCard key={`sub-${projectId}`} projectId={projectId} />
            </div>
          )}
        </TabsContent>

        {/* Tab 3: 来源监控 */}
        <TabsContent value="sources" className="space-y-4">
              <TrendSourceMonitorCard
                onRefresh={() => refreshMutation.mutate()}
                isRefreshing={refreshMutation.isPending}
              />
        </TabsContent>
      </Tabs>

      {/* 3. 抽屉工作台 (Sheet) */}
      {selectedTrend && (
        <TrendDetailSheet
          item={selectedTrend}
          projectId={projectId}
          projects={projects}
          projectsLoading={projectsQuery.isLoading}
          projectsError={projectsQuery.isError}
          onProjectChange={handleProjectChange}
          onProjectsRetry={() => projectsQuery.refetch()}
          onClose={() => setSelectedTrend(null)}
        />
      )}
    </PageContainer>
  );
}
