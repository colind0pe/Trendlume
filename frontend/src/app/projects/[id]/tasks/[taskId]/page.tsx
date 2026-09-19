"use client";
import {
  WorkflowMiniRail,
  WorkflowInspectorDialog,
  ScenePipelineStatus,
} from "@/components/workflow-stages";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Plus,
  Save,
  Trash2,
  MoveUp,
  MoveDown,
  Sparkles,
  Layers,
  CheckCircle2,
  Film,
  Search,
  Loader2,
  BookOpen,
  Play,
  RotateCcw,
  RefreshCw,
  StopCircle,
  AlertCircle,
  Share2,
  Copy,
  Clapperboard,
  Send,
  Check,
  Key,
  ChevronDown,
  ChevronUp,
  Info,
  ShieldAlert,
  Music,
  ExternalLink,
} from "lucide-react";
import { api } from "@/lib/api-client";
import {
  JOB_LIFECYCLE_EVENTS,
  TASK_LIFECYCLE_EVENTS,
  useTaskEvents,
  type TaskEvent,
} from "@/lib/use-task-events";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/field";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PageContainer, PageHeader } from "@/components/ui/page-shell";
import { StatusBadge } from "@/components/ui/status-badge";
import { ContentMode, KnowledgeBrief, ResearchSource, SceneCreate, StructuredScript, ResearchResponse, PlatformMetadata, TemplateCatalogItem, VisualRole } from "@/lib/types";
import { CommercePreflightCard } from "@/components/commerce/commerce-preflight-card";
import { generationStatus, isGenerationLifecycleEvent, isSourceMaterialMode } from "@/lib/task-generation-state";
import { VerificationModal } from "@/components/verification-modal";
import { useToast } from "@/components/ui/toast";
import {
  GENRE_OPTIONS,
  HOOK_OPTIONS,
  SCENE_COUNT_MAX,
  SCENE_COUNT_MIN,
  STYLE_PRESET_OPTIONS,
  ACTIVE_TASK_STATUSES,
  ASSET_TYPE_LABELS,
  CONTENT_MODE_LABELS,
  PLATFORM_LABELS,
  isTaskActive,
  TASK_STATUS_LABELS,
  getTaskStatusTone,
  PUBLISH_STATUS_LABELS,
  formatTemplateName,
  formatParamLabel,
  getContentModeSpec,
  VISUAL_ROLE_OPTIONS,
} from "@/lib/ui-constants";

const canonicalTemplateId = (id?: string | null) =>
  id || "image_gallery_matted";

const researchContextForScript = (research: ResearchResponse | null) => {
  if (!research || research.status !== "completed" || research.sources.length === 0) {
    return undefined;
  }
  return [
    research.summary,
    ...research.sources.map(
      (source, index) => `[${source.ref_id || `source-${index + 1}`}] ${source.title}\nURL: ${source.url}\n摘要：${source.snippet}`
    ),
  ].join("\n");
};

export default function TaskStoryboardPage() {
  const params = useParams();
  const queryClient = useQueryClient();
  const projectId = params.id as string;
  const taskId = params.taskId as string;
  const router = useRouter();
  const { toast } = useToast();
  const isDirtyRef = React.useRef(false);
  const [isDeckCollapsed, setIsDeckCollapsed] = React.useState(false);

  // Dropdown menu state with outside click handler for "更多操作"
  const [isMoreMenuOpen, setIsMoreMenuOpen] = React.useState(false);
  const moreMenuRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!isMoreMenuOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (moreMenuRef.current && !moreMenuRef.current.contains(event.target as Node)) {
        setIsMoreMenuOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsMoreMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMoreMenuOpen]);

  // Task Query
  const { data: task, isLoading: isTaskLoading } = useQuery({
    queryKey: ["task-detail", taskId],
    queryFn: () => api.getTask(taskId),
    refetchInterval: (query) => {
      const currentTask = query.state.data as {
        status?: string;
        active_job?: { status?: string } | null;
      } | undefined;
      const activeStatus = currentTask?.active_job?.status || currentTask?.status;
      return ACTIVE_TASK_STATUSES.has(activeStatus || "")
        ? 2000
        : false;
    },
  });

  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
    enabled: Boolean(projectId),
  });

  // The configuration center is the source of truth for readiness. A saved
  // Provider is intentionally not treated as reachable until it is tested.
  const { data: configSummary } = useQuery({
    queryKey: ["system-config-summary"],
    queryFn: () => api.getSystemConfigSummary(),
  });

  const categoryStatus = (type: string) =>
    configSummary?.categories.find((item) => item.type === type)?.status || "not_configured";

  const llmStatus = categoryStatus("llm");
  const searchStatus = categoryStatus("search");
  const imageStatus = categoryStatus("image");
  const videoStatus = categoryStatus("video");
  const materialStatus = categoryStatus("material");
  const ttsStatus = categoryStatus("tts");
  const pubStatus = categoryStatus("publishing");
  const llmConfigured = !["not_configured", "disabled"].includes(llmStatus);
  const searchConfigured = !["not_configured", "disabled"].includes(searchStatus);

  const configuredContentMode = task?.input_payload?.content_mode || "generated_image";
  const configuredContentModeSpec = getContentModeSpec(configuredContentMode);
  const isOnlineAssetMode = configuredContentModeSpec?.sourceKind === "online";
  const isGeneratedImageMode =
    configuredContentModeSpec?.sourceKind === "ai" && configuredContentModeSpec.visualKind === "image";
  const isGeneratedVideoMode =
    configuredContentModeSpec?.sourceKind === "ai" && configuredContentModeSpec.visualKind === "video";
  const sourceMaterialMode = isSourceMaterialMode(configuredContentMode);

  const visualReadinessItems = isOnlineAssetMode
    ? [
        {
          type: "material",
          title: "素材库视频 Provider",
          status: materialStatus,
          ready: materialStatus === "ready",
          critical: true,
          impact: "无法检索素材库实拍视频（需配置素材库 Provider）",
          solution: "当前为素材库视频模式，流水线将自动检索实拍视频；也可在各分镜中绑定我的素材。",
        },
      ]
    : isGeneratedVideoMode
    ? [
        {
          type: "video",
          title: "AI 视频生成 Provider",
          status: videoStatus,
          ready: videoStatus === "ready",
          critical: true,
          impact: "无法生成 AI 动态分镜视频片段。",
          solution: "请配置视频生成 Provider，或新建任务时改用 AI 图片、素材库视频或我的素材。",
        },
      ]
    : isGeneratedImageMode
    ? [
        {
          type: "image",
          title: "AI 图片生成 Provider",
          status: imageStatus,
          ready: imageStatus === "ready",
          critical: true,
          impact: "无法自动生成各分镜的静态画面素材。",
          solution: "请配置图像生成 Provider，或在各分镜中绑定我的素材。",
        },
      ]
    : [];

  const readinessItems = [
    {
      type: "llm",
      title: "大语言模型 Provider",
      status: llmStatus,
      ready: llmStatus === "ready",
      critical: true,
      impact: "无法使用 AI 自动提炼剧本与分镜故事板",
      solution: sourceMaterialMode
        ? "您仍可手动录入各分镜台词继续生成，或在设置中配置大语言模型 (LLM) Provider。"
        : "您仍可手动录入各分镜台词与画面提示词继续生成，或在设置中配置大语言模型 (LLM) Provider。",
    },
    {
      type: "search",
      title: "全网事实检索 Provider",
      status: searchStatus,
      ready: searchStatus === "ready",
      critical: false,
      impact: "无法进行全网实时热点事实调研（自动跳过）",
      solution: "AI 剧本生成将自动跳过联网搜索，直接基于语言模型已有知识创作，不阻塞流程。",
    },
    ...visualReadinessItems,
    {
      type: "tts",
      title: "旁白语音配音 Provider",
      status: ttsStatus,
      ready: ttsStatus === "ready",
      critical: true,
      impact: "无法自动为分镜台词合成旁白解说音频",
      solution: "可手动上传解说录音，或在设置中配置语音合成 Provider (Edge-TTS)。",
    },
    {
      type: "publishing",
      title: "抖音社交发布",
      status: pubStatus,
      ready: pubStatus === "ready",
      critical: false,
      impact: "无法一键自动发布至抖音开放平台（自动降级）",
      solution: "视频仍可在本地完成渲染并导出 MP4，成片后可手动下载视频文件自行分发。",
    },
  ];

  const missingItems = configSummary ? readinessItems.filter((item) => !item.ready) : [];
  const criticalMissing = missingItems.filter(
    (item) => item.critical && item.status !== "not_tested"
  );
  const pendingTestItems = missingItems.filter((item) => item.status === "not_tested");
  const [showReadinessDetails, setShowReadinessDetails] = React.useState(false);

  const activeJobIdRef = React.useRef<string | undefined>();
  const liveJobIdRef = React.useRef<string | undefined>();

  const { data: projectAssets = [] } = useQuery({
    queryKey: ["task-project-assets", task?.project_id],
    queryFn: () => api.listAssets(task?.project_id),
    enabled: Boolean(task?.project_id),
  });

  const { data: projectBgm = [] } = useQuery({
    queryKey: ["task-project-bgm", task?.project_id],
    queryFn: () => api.getProjectBgm(task!.project_id),
    enabled: Boolean(task?.project_id),
  });

  const { data: publishingAccounts = [] } = useQuery({
    queryKey: ["publishing-accounts"],
    queryFn: () => api.listAccounts("douyin"),
  });

  const { data: taskResearch } = useQuery<ResearchResponse>({
    queryKey: ["task-research", taskId],
    queryFn: () => api.getTaskResearch(taskId),
    refetchInterval: (query) => {
      const research = query.state.data;
      return task && isTaskActive(task) && research?.status === "pending"
        ? 2000
        : false;
    },
  });

  const { data: templates = [] } = useQuery<TemplateCatalogItem[]>({
    queryKey: ["template-catalog"],
    queryFn: () => api.listTemplates(),
  });

  const [isWorkflowInspectorOpen, setIsWorkflowInspectorOpen] = React.useState(false);
  const [retryingUnits, setRetryingUnits] = React.useState<Record<string, boolean>>({});

  const { data: workflowSnapshot } = useQuery({
    queryKey: ["task-workflow", taskId],
    queryFn: () => api.getWorkflow(taskId),
    refetchInterval: () => (task && isTaskActive(task) ? 2000 : false),
  });

  // Local state for editable scenes
  const [scenes, setScenes] = React.useState<SceneCreate[]>([]);
  const [taskTitle, setTaskTitle] = React.useState("");
  const [taskDesc, setTaskDesc] = React.useState("");
  const [isSaved, setIsSaved] = React.useState(false);
  const [isDirty, setIsDirty] = React.useState(false);
  const [missingConfigAlert, setMissingConfigAlert] = React.useState<string | null>(null);

  // Render settings are kept in the task input snapshot so that composition
  // and render-only rerender use the same values after a page refresh.
  const [renderTemplateId, setRenderTemplateId] = React.useState("image_gallery_matted");
  const [renderParams, setRenderParams] = React.useState<Record<string, any>>({});
  const [bgmEnabled, setBgmEnabled] = React.useState(false);
  const [bgmAssetId, setBgmAssetId] = React.useState("");
  const [bgmVolume, setBgmVolume] = React.useState(0.2);

  // Workflow Real-Time SSE State
  const [liveStatus, setLiveStatus] = React.useState<string | null>(null);
  const [liveProgress, setLiveProgress] = React.useState<number | null>(null);
  const [liveStepMessage, setLiveStepMessage] = React.useState<string | null>(null);
  const [liveCurrentScene, setLiveCurrentScene] = React.useState<number | null>(null);
  const [liveTotalScenes, setLiveTotalScenes] = React.useState<number | null>(null);
  const [liveVideoUrl, setLiveVideoUrl] = React.useState<string | null>(null);

  // AI Script Assistant Modal State
  const [isAIOpen, setIsAIOpen] = React.useState(false);
  const [isCancelConfirmOpen, setIsCancelConfirmOpen] = React.useState(false);
  const [sceneToDelete, setSceneToDelete] = React.useState<{ index: number; label: string } | null>(null);
  const [isApplyScriptConfirmOpen, setIsApplyScriptConfirmOpen] = React.useState(false);
  const [aiTopic, setAiTopic] = React.useState("");
  const [aiGenre, setAiGenre] = React.useState("auto");
  const [aiHookType, setAiHookType] = React.useState("auto");
  const [aiStylePreset, setAiStylePreset] = React.useState("stick_figure");
  const [aiSceneCount, setAiSceneCount] = React.useState(SCENE_COUNT_MIN);
  const [researchData, setResearchData] = React.useState<ResearchResponse | null>(null);
  const [generatedScript, setGeneratedScript] = React.useState<StructuredScript | null>(null);

  // Douyin Publishing Modal State
  const [isPublishOpen, setIsPublishOpen] = React.useState(false);
  const [pubTitle, setPubTitle] = React.useState("");
  const [pubDesc, setPubDesc] = React.useState("");
  const [pubTags, setPubTags] = React.useState("Trendlume, AI短视频, 科技科普");
  const [publishAccountId, setPublishAccountId] = React.useState("");
  const [publishCoverAssetId, setPublishCoverAssetId] = React.useState("");
  const [publishMode, setPublishMode] = React.useState<"now" | "schedule">("now");
  const [scheduledAt, setScheduledAt] = React.useState("");
  const [isRerenderOpen, setIsRerenderOpen] = React.useState(false);
  const [rerenderTemplateId, setRerenderTemplateId] = React.useState("image_gallery_matted");
  const [rerenderParams, setRerenderParams] = React.useState<Record<string, any>>({});
  const [rerenderBgmEnabled, setRerenderBgmEnabled] = React.useState(false);
  const [rerenderBgmAssetId, setRerenderBgmAssetId] = React.useState("");
  const [rerenderBgmVolume, setRerenderBgmVolume] = React.useState(0.2);

  // Per-scene generating status tracking
  const [generatingTTS, setGeneratingTTS] = React.useState<Record<string, boolean>>({});
  const [generatingImage, setGeneratingImage] = React.useState<Record<string, boolean>>({});
  const [generatingVideo, setGeneratingVideo] = React.useState<Record<string, boolean>>({});

  const resetLiveState = React.useCallback(() => {
    setLiveStatus(null);
    setLiveProgress(null);
    setLiveStepMessage(null);
    setLiveCurrentScene(null);
    setLiveTotalScenes(null);
  }, []);

  // Sync state from fetched task
  React.useEffect(() => {
    isDirtyRef.current = false;
    setIsDirty(false);
    liveJobIdRef.current = undefined;
    activeJobIdRef.current = undefined;
    resetLiveState();
    setMissingConfigAlert(null);
  }, [taskId]);

  React.useEffect(() => {
    if (task && ["completed", "failed", "cancelled"].includes(task.status)) resetLiveState();
  }, [task?.status, task?.updated_at, resetLiveState]);

  React.useEffect(() => {
    if (!task || isDirtyRef.current) return;

    const inputPayload = task.input_payload || {};
    const generatedMetadata = inputPayload.metadata as PlatformMetadata | undefined;
    const nextTemplateId = canonicalTemplateId(inputPayload.template_id);
    if (task) {
      setTaskTitle(task.title);
      setTaskDesc(task.description || "");
      setAiTopic((current) => current || task.title || "");
      setPubTitle(generatedMetadata?.title || task.title || "");
      setPubDesc(generatedMetadata?.description ?? task.description ?? "");
      setPubTags(
        Array.isArray(generatedMetadata?.tags) && generatedMetadata.tags.length > 0
          ? generatedMetadata.tags.slice(0, 5).join(", ")
          : "Trendlume, AI短视频, 科技科普"
      );
      setRenderTemplateId(nextTemplateId);
      setRenderParams(inputPayload.template_params || {});
      setBgmEnabled(Boolean(inputPayload.bgm_enabled ?? false));
      setBgmAssetId(inputPayload.bgm_asset_id || "");
      setBgmVolume(Number(inputPayload.bgm_volume ?? 0.2));
      setRerenderTemplateId(nextTemplateId);
      setRerenderParams(inputPayload.template_params || {});
      setRerenderBgmEnabled(Boolean(inputPayload.bgm_enabled ?? false));
      setRerenderBgmAssetId(inputPayload.bgm_asset_id || "");
      setRerenderBgmVolume(Number(inputPayload.bgm_volume ?? 0.2));
      const configuredSceneCount = Number(inputPayload.target_scene_count);
      if (Number.isFinite(configuredSceneCount)) {
        setAiSceneCount(
          Math.min(SCENE_COUNT_MAX, Math.max(SCENE_COUNT_MIN, Math.round(configuredSceneCount)))
        );
      }
      if (task.scenes && task.scenes.length > 0) {
        setScenes(
          task.scenes.map((s, idx) => ({
            sequence_index: s.sequence_index !== undefined ? s.sequence_index : idx,
            narration_text: s.narration_text || "",
            visual_prompt: s.visual_prompt || "",
            duration_seconds: s.duration_seconds || 4.0,
            layout_params: s.layout_params || {},
            visual_role: s.visual_role || "concept",
            claim_refs: s.claim_refs || [],
            source_refs: s.source_refs || [],
            production_metadata: s.production_metadata || {},
            audio_asset_id: s.audio_asset_id,
            media_asset_id: s.media_asset_id,
          }))
        );
      }
    }
  }, [task]);

  React.useEffect(() => {
    if (!publishAccountId && publishingAccounts.length > 0) {
      setPublishAccountId(publishingAccounts[0].id);
    }
  }, [publishAccountId, publishingAccounts]);

  React.useEffect(() => {
    if (!isDirty) return;

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty]);

  React.useEffect(() => {
    if (taskResearch && taskResearch.status !== "pending") {
      setResearchData(taskResearch);
    }
  }, [taskResearch]);

  React.useEffect(() => {
    const nextJobId = task?.active_job?.id;
    const previousJobId = activeJobIdRef.current;
    const liveEventJobId = liveJobIdRef.current;
    const jobChanged =
      Boolean(previousJobId && nextJobId && previousJobId !== nextJobId) ||
      Boolean(nextJobId && liveEventJobId && liveEventJobId !== nextJobId);

    activeJobIdRef.current = nextJobId;
    if (jobChanged) {
      liveJobIdRef.current = undefined;
      resetLiveState();
    }
  }, [resetLiveState, task?.active_job?.id]);

  const refreshActiveTaskQueries = React.useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["task-workflow", taskId] });
    queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
    queryClient.invalidateQueries({ queryKey: ["task-research", taskId] });
  }, [queryClient, taskId]);

  const handleTaskEvent = React.useCallback(
    (event: TaskEvent) => {
      const data = event.data || {};
      if (data.task_id && data.task_id !== taskId) return;

      // Publishing workflow events are tracked on task-detail
      if (data.stage === "publishing" || data.job_type === "publish") {
        queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
        return;
      }

      const currentJobId = activeJobIdRef.current;
      // If event belongs to this task and carries a job_id, adopt it if none is set or if a newer job has started
      if (data.job_id && (!currentJobId || data.job_id !== currentJobId)) {
        activeJobIdRef.current = data.job_id;
        liveJobIdRef.current = data.job_id;
      } else if (data.job_id) {
        liveJobIdRef.current = data.job_id;
      }

      const stage = String(data.stage || "").toLowerCase();
      const progress = typeof data.progress === "number" ? Math.max(0, Math.min(100, data.progress)) : null;
      const message = data.message;

      if (typeof data.current_scene === "number") setLiveCurrentScene(data.current_scene);
      if (typeof data.total_scenes === "number") setLiveTotalScenes(data.total_scenes);
      if (progress !== null) setLiveProgress(progress);
      if (message) setLiveStepMessage(message);

      const taskLifecycleEvent = TASK_LIFECYCLE_EVENTS.has(event.event);
      const currentJobLifecycleEvent = JOB_LIFECYCLE_EVENTS.has(event.event);
      if (isGenerationLifecycleEvent(event.event)) {
        if (event.event === "task.completed" || event.event === "job.completed") {
          setLiveStatus("completed");
          setLiveProgress(100);
          setLiveStepMessage(message || "视频生成与合成完毕");
          const completedUrl = data.preview_url || data.final_video_url;
          if (completedUrl) setLiveVideoUrl(completedUrl);
        } else if (event.event === "task.failed" || event.event === "job.failed") {
          setLiveStatus("failed");
          setLiveStepMessage(message || "生成失败");
        } else if (event.event === "task.cancelled" || event.event === "job.cancelled") {
          setLiveStatus("cancelled");
          setLiveStepMessage(message || "任务已取消");
        } else if (event.event === "job.retrying") {
          setLiveStatus("running");
          setLiveStepMessage(message || "任务将自动重试");
        } else {
          setLiveStatus("running");
        }
      }

      if (event.event === "video.preview_ready") {
        const previewUrl = data.preview_url || data.final_video_url;
        if (previewUrl) setLiveVideoUrl(previewUrl);
        setLiveStepMessage(message || "最终 MP4 预览已就绪");
      }
      if (event.event === "research.warning") {
        setLiveStepMessage(message || "实时资料未使用");
      }

      const researchStageEvent =
        event.event === "research.warning" ||
        ((event.event === "step.started" || event.event === "step.completed") && stage === "research");
      const shouldRefreshWorkflow =
        taskLifecycleEvent ||
        currentJobLifecycleEvent ||
        event.event === "step.started" ||
        event.event === "step.completed" ||
        event.event === "video.preview_ready";
      const shouldRefreshTask =
        taskLifecycleEvent ||
        currentJobLifecycleEvent ||
        event.event === "step.started" ||
        event.event === "step.completed" ||
        event.event === "scene.status_changed" ||
        event.event === "asset.created" ||
        event.event === "video.preview_ready";

      if (researchStageEvent) {
        queryClient.invalidateQueries({ queryKey: ["task-research", taskId] });
      }
      if (shouldRefreshWorkflow) {
        queryClient.invalidateQueries({ queryKey: ["task-workflow", taskId] });
      }
      if (shouldRefreshTask) {
        queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      }
      if (taskLifecycleEvent || currentJobLifecycleEvent || event.event === "step.completed") {
        queryClient.invalidateQueries({ queryKey: ["project-tasks", projectId] });
        queryClient.invalidateQueries({ queryKey: ["all-tasks"] });
      }
      if (event.event === "asset.created") {
        if (task?.project_id) {
          queryClient.invalidateQueries({ queryKey: ["task-project-assets", task.project_id] });
        }
        queryClient.invalidateQueries({ queryKey: ["project-assets", projectId] });
      }
    },
    [projectId, queryClient, task?.project_id, taskId]
  );

  React.useEffect(() => {
    activeJobIdRef.current = undefined;
    liveJobIdRef.current = undefined;
    resetLiveState();
    setLiveVideoUrl(null);
  }, [resetLiveState, taskId]);

  const { isConnected: isTaskEventsConnected } = useTaskEvents({
    taskId,
    onEvent: handleTaskEvent,
    onReconnect: refreshActiveTaskQueries,
  });

  const markDirty = () => {
    isDirtyRef.current = true;
    setIsDirty(true);
  };

  const requireSaved = () => {
    if (!isDirtyRef.current) return true;
    toast("有未保存的故事板或成片配置，请先点击“保存故事板”。", "warning");
    return false;
  };

  const errorMessage = (error: unknown, fallback: string) =>
    error instanceof Error && error.message ? error.message : fallback;

  const handleRetryWorkflowUnit = async (stepKey: "voice" | "assets", unitKey: string) => {
    if (!requireSaved()) return;
    const key = `${stepKey}-${unitKey}`;
    setRetryingUnits((prev) => ({ ...prev, [key]: true }));
    try {
      await api.retryWorkflowStep(taskId, stepKey, unitKey);
      queryClient.invalidateQueries({ queryKey: ["task-workflow", taskId] });
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      toast(`已触发分镜 ${stepKey === "voice" ? "配音" : "画面"} 重新生成（最小重算）`, "success");
    } catch (err: any) {
      setMissingConfigAlert(err.message || `重试 ${stepKey} 失败`);
    } finally {
      setRetryingUnits((prev) => ({ ...prev, [key]: false }));
    }
  };

  // Mutations
  const updateTaskMutation = useMutation({
    mutationFn: (data: { title: string; description: string; input_payload: Record<string, any> }) =>
      api.updateTask(taskId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      queryClient.invalidateQueries({ queryKey: ["project-tasks", projectId] });
    },
  });

  const regenerateMetadataMutation = useMutation({
    mutationFn: () => api.regenerateTaskMetadata(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      queryClient.invalidateQueries({ queryKey: ["project-tasks", projectId] });
      toast("标题、描述和话题已重新生成。", "success");
    },
    onError: (err: unknown) => toast(`发布信息生成失败：${errorMessage(err, "请稍后重试")}`, "error"),
  });

  const saveScenesMutation = useMutation({
    mutationFn: (scenesData: SceneCreate[]) =>
      api.batchUpdateTaskScenes(taskId, scenesData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      queryClient.invalidateQueries({ queryKey: ["commerce-preflight", taskId] });
    },
  });

  const generateWorkflowMutation = useMutation({
    mutationFn: () => api.generateTaskVideo(taskId),
    onMutate: () => {
      setMissingConfigAlert(null);
      resetLiveState();
      setLiveVideoUrl(null);
    },
    onSuccess: (res) => {
      const newJobId = (res as any)?.data?.id;
      if (newJobId) {
        activeJobIdRef.current = newJobId;
        liveJobIdRef.current = newJobId;
      }
      setLiveStatus("running");
      setLiveProgress(5);
      setLiveStepMessage("任务已进入排队队列…");
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      queryClient.invalidateQueries({ queryKey: ["task-workflow", taskId] });
    },
    onError: (err: any) => {
      resetLiveState();
      setMissingConfigAlert(err.message || "启动全自动生成失败，请检查 AI 模型凭证配置。");
    },
  });

  const cancelWorkflowMutation = useMutation({
    mutationFn: () => api.cancelTaskGeneration(taskId),
    onSuccess: () => {
      setLiveStatus("cancelled");
      setLiveStepMessage("正在取消任务…");
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
    },
  });

  const retryWorkflowMutation = useMutation({
    mutationFn: () => api.retryTaskGeneration(taskId),
    onMutate: () => {
      setMissingConfigAlert(null);
      resetLiveState();
      setLiveVideoUrl(null);
    },
    onSuccess: (res) => {
      const newJobId = (res as any)?.data?.id;
      if (newJobId) {
        activeJobIdRef.current = newJobId;
        liveJobIdRef.current = newJobId;
      }
      setLiveStatus("running");
      setLiveProgress(5);
      setLiveStepMessage("正在重新启动生成流程…");
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      queryClient.invalidateQueries({ queryKey: ["task-workflow", taskId] });
    },
    onError: (err: any) => {
      resetLiveState();
      setMissingConfigAlert(err.message || "重试生成失败，请检查相关 AI 配置。");
    },
  });

  const composeVideoMutation = useMutation({
    mutationFn: () => api.composeTaskVideo(taskId),
    onMutate: () => {
      setMissingConfigAlert(null);
      setLiveVideoUrl(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      queryClient.invalidateQueries({ queryKey: ["commerce-preflight", taskId] });
      queryClient.invalidateQueries({ queryKey: ["task-workflow", taskId] });
      toast("最终完整成片已合成完毕。", "success");
    },
    onError: (err: any) => {
      setMissingConfigAlert(err.message || "成片合成失败，请检查分镜素材与 FFmpeg 环境。");
    },
  });

  const publishMutation = useMutation({
    mutationFn: (payload: { account_id?: string; cover_asset_id?: string | null; title: string; description: string; tags: string[] }) =>
      api.publishTaskVideo(taskId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      queryClient.invalidateQueries({ queryKey: ["publishing-jobs"] });
      setIsPublishOpen(false);
      toast("已提交至抖音发布队列，正在跳转发布中心…", "success");
      router.push("/publishing");
    },
    onError: (err: any) => {
      toast(`发布失败：${errorMessage(err, "请检查账号和成片状态")}`, "error");
    },
  });

  const scheduleMutation = useMutation({
    mutationFn: (payload: { account_id?: string; cover_asset_id?: string | null; title: string; description: string; tags: string[]; scheduled_at: string }) =>
      api.scheduleTaskVideo(taskId, payload),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      queryClient.invalidateQueries({ queryKey: ["publishing-jobs"] });
      setIsPublishOpen(false);
      toast(
        `已安排抖音定时发布：${job.scheduled_at ? new Date(job.scheduled_at).toLocaleString() : ""}，正在跳转发布中心…`,
        "success"
      );
      router.push("/publishing");
    },
    onError: (err: any) => toast(`定时发布失败：${errorMessage(err, "请检查排期时间和账号状态")}`, "error"),
  });

  const cancelScheduledPublishMutation = useMutation({
    mutationFn: () => api.cancelScheduledPublish(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      queryClient.invalidateQueries({ queryKey: ["publishing-jobs"] });
      toast("已取消生成完成后的自动发布。", "success");
    },
    onError: (err: any) => toast(`取消自动发布失败：${errorMessage(err, "请稍后重试")}`, "error"),
  });

  const resumeMutation = useMutation({
    mutationFn: () => api.resumeTaskGeneration(taskId, task?.active_job?.id || undefined),
    onSuccess: (res) => {
      const newJobId = (res as any)?.data?.id;
      if (newJobId) {
        activeJobIdRef.current = newJobId;
        liveJobIdRef.current = newJobId;
      }
      setLiveStatus("running");
      setLiveStepMessage("已重新加入队列，将从最近检查点继续…");
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      queryClient.invalidateQueries({ queryKey: ["task-workflow", taskId] });
    },
    onError: (err: any) => setMissingConfigAlert(err.message || "恢复任务失败"),
  });

  const duplicateMutation = useMutation({
    mutationFn: () => api.duplicateTask(taskId),
    onSuccess: (copy) => {
      window.location.href = `/projects/${projectId}/tasks/${copy.id}`;
    },
    onError: (err: any) => setMissingConfigAlert(err.message || "复制任务失败"),
  });

  const rerenderMutation = useMutation({
    mutationFn: () => api.rerenderTask(taskId, {
      template_id: rerenderTemplateId,
      template_params: rerenderParams,
      bgm_enabled: rerenderBgmEnabled,
      bgm_asset_id: rerenderBgmEnabled ? (rerenderBgmAssetId || null) : null,
      bgm_volume: rerenderBgmVolume,
    }),
    onMutate: () => {
      setMissingConfigAlert(null);
      resetLiveState();
      setLiveVideoUrl(null);
      setLiveStatus("running");
      setLiveProgress(5);
      setLiveStepMessage("已创建重新渲染任务，将复用已有脚本和媒体素材…");
    },
    onSuccess: (res) => {
      setIsRerenderOpen(false);
      const newJobId = (res as any)?.data?.job?.id || (res as any)?.data?.id;
      if (newJobId) {
        activeJobIdRef.current = newJobId;
        liveJobIdRef.current = newJobId;
      }
      setLiveStatus("running");
      setLiveProgress(10);
      setLiveStepMessage("正在应用新模板并开始重新合成…");
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      queryClient.invalidateQueries({ queryKey: ["task-workflow", taskId] });
    },
    onError: (err: any) => {
      resetLiveState();
      setMissingConfigAlert(err.message || "重新渲染失败");
    },
  });

  const researchMutation = useMutation({
    mutationFn: () => {
      const persistedTopic = String(task?.input_payload?.topic || task?.title || "").trim();
      const requestedTopic = aiTopic.trim();
      return requestedTopic && requestedTopic !== persistedTopic
        ? api.researchTopic(requestedTopic)
        : api.researchTask(taskId);
    },
    onSuccess: (data) => {
      setResearchData(data);
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      queryClient.invalidateQueries({ queryKey: ["task-research", taskId] });
      toast(data.status === "completed" ? "研究资料已准备好。" : "研究请求已完成，请查看结果状态。", data.status === "completed" ? "success" : "warning");
    },
    onError: (err: any) => {
      toast(`全网调研失败：${errorMessage(err, "请检查事实检索 Provider 配置")}`, "error");
    },
  });

  const researchPending =
    researchMutation.isPending ||
    (taskResearch?.status === "pending" && Boolean(taskResearch.started_at));

  const generateScriptMutation = useMutation({
    mutationFn: (payload: {
      topic: string;
      research_context?: string;
      enable_research?: boolean;
      genre?: string;
      hook_type?: string;
      style_preset?: string;
      target_scene_count?: number;
      knowledge_brief?: KnowledgeBrief;
      research_sources?: ResearchSource[];
    }) => api.generateScript(payload),
    onSuccess: (data) => setGeneratedScript(data),
    onError: (err: any) => {
      setMissingConfigAlert(err.message || "生成脚本失败，请检查大语言模型 Provider 配置。");
    },
  });

  const applyScriptMutation = useMutation({
    mutationFn: (script: StructuredScript) => api.applyScriptToTask(taskId, script),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      setIsAIOpen(false);
      setResearchData(null);
      setGeneratedScript(null);
    },
  });

  // Scene Media Generation Helpers
  const handleGenerateTTS = async (sceneId: string, index: number) => {
    if (!requireSaved()) return;
    setGeneratingTTS((prev) => ({ ...prev, [sceneId || index]: true }));
    try {
      if (task?.scenes && task.scenes[index]?.id) {
        await api.generateSceneTTS(task.scenes[index].id, task.input_payload?.voice_id, Number(task.input_payload?.speed || 1));
        queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      } else {
        toast("请先保存故事板，再生成配音。", "warning");
      }
    } catch (e: any) {
      setMissingConfigAlert(e.message || "配音生成失败，请检查语音合成 Provider 配置。");
    } finally {
      setGeneratingTTS((prev) => ({ ...prev, [sceneId || index]: false }));
    }
  };

  const handleGenerateImage = async (sceneId: string, index: number) => {
    if (!requireSaved()) return;
    setGeneratingImage((prev) => ({ ...prev, [sceneId || index]: true }));
    try {
      if (task?.scenes && task.scenes[index]?.id) {
        await api.generateSceneImage(task.scenes[index].id);
        queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      } else {
        toast("请先保存故事板，再生成画面。", "warning");
      }
    } catch (e: any) {
      setMissingConfigAlert(e.message || "画面生成失败，请检查图像生成 Provider 配置。");
    } finally {
      setGeneratingImage((prev) => ({ ...prev, [sceneId || index]: false }));
    }
  };

  const handleGenerateVideo = async (sceneId: string, index: number) => {
    if (!requireSaved()) return;
    setGeneratingVideo((prev) => ({ ...prev, [sceneId || index]: true }));
    try {
      if (task?.scenes && task.scenes[index]?.id) {
        await api.generateSceneVideo(task.scenes[index].id);
        queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      } else {
        toast("请先保存故事板，再生成视频。", "warning");
      }
    } catch (e: any) {
      setMissingConfigAlert(e.message || "视频生成失败，请检查视频生成 Provider 配置。");
    } finally {
      setGeneratingVideo((prev) => ({ ...prev, [sceneId || index]: false }));
    }
  };

  // Scene manipulation
  const handleAddScene = () => {
    markDirty();
    setScenes([
      ...scenes,
      {
        sequence_index: scenes.length,
        narration_text: "",
        visual_prompt: "",
        duration_seconds: 4.0,
        layout_params: {},
        visual_role: "b_roll",
        claim_refs: [],
        source_refs: [],
        production_metadata: {},
      },
    ]);
  };

  const handleDeleteScene = (index: number) => {
    if (scenes.length <= 1) {
      toast("视频至少需要保留一个分镜片段。", "warning");
      return;
    }
    markDirty();
    const updated = scenes
      .filter((_, i) => i !== index)
      .map((sc, i) => ({ ...sc, sequence_index: i }));
    setScenes(updated);
  };

  const requestDeleteScene = (index: number) => {
    if (scenes.length <= 1) {
      toast("视频至少需要保留一个分镜片段。", "warning");
      return;
    }
    setSceneToDelete({ index, label: `分镜 ${index + 1}` });
  };

  const handleMoveUp = (index: number) => {
    if (index === 0) return;
    markDirty();
    const updated = [...scenes];
    const temp = updated[index - 1];
    updated[index - 1] = updated[index];
    updated[index] = temp;
    setScenes(updated.map((sc, i) => ({ ...sc, sequence_index: i })));
  };

  const handleMoveDown = (index: number) => {
    if (index === scenes.length - 1) return;
    markDirty();
    const updated = [...scenes];
    const temp = updated[index + 1];
    updated[index + 1] = updated[index];
    updated[index] = temp;
    setScenes(updated.map((sc, i) => ({ ...sc, sequence_index: i })));
  };

  const handleSceneChange = (
    index: number,
    field: keyof SceneCreate,
    value: any
  ) => {
    markDirty();
    const updated = [...scenes];
    updated[index] = { ...updated[index], [field]: value };
    setScenes(updated);
  };

  const handleSaveAll = async () => {
    if (!task) return;
    try {
      await Promise.all([
        updateTaskMutation.mutateAsync({
          title: taskTitle,
          description: taskDesc,
          input_payload: {
            ...task.input_payload,
            template_id: renderTemplateId,
            template_params: renderParams,
            bgm_enabled: bgmEnabled,
            bgm_asset_id: bgmEnabled ? bgmAssetId || null : null,
            bgm_volume: bgmVolume,
          },
        }),
        saveScenesMutation.mutateAsync(scenes),
      ]);
      isDirtyRef.current = false;
      setIsDirty(false);
      setIsSaved(true);
      window.setTimeout(() => setIsSaved(false), 2500);
      toast("故事板与成片配置已保存。", "success");
    } catch (error) {
      toast(`保存失败：${errorMessage(error, "请稍后重试")}`, "error");
    }
  };

  // Derived metrics
  const totalWords = scenes.reduce((acc, sc) => acc + (sc.narration_text?.length || 0), 0);

  const currentStatus = generationStatus(task || {}, liveStatus);
  const persistedProgress = Math.max(
    0,
    Math.min(100, Number(task?.active_job?.progress ?? task?.progress_percentage ?? 0))
  );
  const liveProgressForCurrentJob =
    liveProgress !== null &&
    (!task?.active_job?.id || !liveJobIdRef.current || liveJobIdRef.current === task.active_job.id)
      ? liveProgress
      : null;
  const currentProgress = task?.status === "completed"
    ? 100
    : Math.max(persistedProgress, liveProgressForCurrentJob ?? 0);
  const isRunning = currentStatus === "running" || currentStatus === "pending";
  const finalVideoUrl = liveVideoUrl || task?.result_payload?.final_video_url;
  const taskContentMode = configuredContentMode as ContentMode;
  const taskContentModeSpec = getContentModeSpec(taskContentMode);
  const usesVisualPrompt = taskContentModeSpec?.usesVisualPrompt === true;
  const taskMetadata = task?.input_payload?.metadata as PlatformMetadata | undefined;
  const scheduledPublish = task?.scheduled_publish || task?.input_payload?.scheduled_publish;
  const scheduledPublishStatus = String(scheduledPublish?.status || "pending");
  const canCancelScheduledPublish = ["pending", "scheduled", "queued", "publishing"].includes(scheduledPublishStatus);
  const projectAspect = project?.aspect_ratio || "9:16";
  const availableTemplates = React.useMemo(() => {
    return templates.filter((item) => {
      const matchesMode = item.supported_content_modes.includes(taskContentMode as any);
      const matchesAspect =
        item.aspect_ratio === projectAspect ||
        (!item.aspect_ratio && projectAspect === "9:16");
      return matchesMode && matchesAspect;
    });
  }, [templates, taskContentMode, projectAspect]);
  const selectedTemplate =
    availableTemplates.find((item) => item.id === renderTemplateId) ||
    templates.find((item) => item.id === renderTemplateId);
  const selectedTemplateName = formatTemplateName(
    renderTemplateId,
    selectedTemplate?.name || renderTemplateId
  );
  const taskContentModeLabel = CONTENT_MODE_LABELS[taskContentMode] || taskContentMode;

  React.useEffect(() => {
    if (isRerenderOpen && availableTemplates.length > 0) {
      const exists = availableTemplates.some((t) => t.id === rerenderTemplateId);
      if (!exists) {
        const fallback = availableTemplates[0];
        setRerenderTemplateId(fallback.id);
        setRerenderParams(fallback.default_params || {});
      }
    }
  }, [isRerenderOpen, availableTemplates, rerenderTemplateId]);
  const videoAspectClass =
    projectAspect === "16:9"
      ? "aspect-[16/9] w-full max-w-[500px]"
      : projectAspect === "1:1"
      ? "aspect-square w-full max-w-[340px]"
      : "aspect-[9/16] max-h-[380px]";
  const videoPlaceholderAspectClass =
    projectAspect === "16:9"
      ? "aspect-[16/9] w-full max-w-[420px]"
      : projectAspect === "1:1"
      ? "aspect-square w-full max-w-[280px]"
      : "aspect-[9/16] max-h-[280px]";
  const sceneThumbAspectClass =
    projectAspect === "16:9"
      ? "aspect-[16/9] h-20"
      : projectAspect === "1:1"
      ? "aspect-square h-20"
      : "aspect-[9/16] h-24";

  const selectedBgm = projectBgm.find((asset) => asset.id === bgmAssetId);
  const coverAssets = projectAssets.filter((asset) => asset.asset_type === "image");
  const readySceneCount = scenes.filter((_, index) => {
    const scene = task?.scenes?.[index];
    return Boolean(scene?.audio_asset_id && (scene?.media_asset_id || taskContentMode === "static"));
  }).length;
  const nextAction = isDirty
    ? "保存未完成的编辑"
    : !scenes.length
    ? "添加第一个分镜"
    : readySceneCount < scenes.length
    ? `补齐 ${scenes.length - readySceneCount} 个分镜素材`
    : !finalVideoUrl
    ? "合成最终成片"
    : "检查成片并发布";
  const primaryAction = isDirty
    ? "save"
    : isRunning
    ? "cancel"
    : task?.can_resume
    ? "resume"
    : finalVideoUrl
    ? "publish"
    : scenes.length > 0 && readySceneCount >= scenes.length
    ? "compose"
    : "generate";

  if (isTaskLoading) {
    return <PageContainer className="space-y-4"><div className="h-24 animate-pulse rounded-lg border border-border bg-card" /></PageContainer>;
  }

  if (!task) {
    return <PageContainer><EmptyState title="任务不存在或已被删除" /></PageContainer>;
  }

  return (
    <PageContainer width="full" data-testid="task-storyboard" className="space-y-5">
      {/* Top Header & Breadcrumb */}
      <PageHeader
        back={(
          <Link
            href={`/projects/${projectId}`}
            onClick={(event) => {
              if (isDirtyRef.current && !window.confirm("当前故事板有未保存修改，确定离开吗？")) event.preventDefault();
            }}
            className="mb-1 inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors group"
          >
            <ArrowLeft aria-hidden="true" className="h-3.5 w-3.5 transition-transform duration-150 group-hover:-translate-x-0.5" />
            <span>返回项目空间</span>
          </Link>
        )}
        title={(
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate">{taskTitle || "未命名视频任务"}</span>
            {isDirty && <StatusBadge label="未保存" tone="warning" />}
            <StatusBadge label={TASK_STATUS_LABELS[currentStatus] || currentStatus} tone={getTaskStatusTone(currentStatus)} />
          </span>
        )}
        description={
          taskContentMode === "online_asset"
            ? "调优分镜脚本、获取素材库视频与配音，控制视频渲染流水线。"
            : taskContentMode === "uploaded_asset"
            ? "调优分镜脚本、绑定我的素材与配音，控制视频渲染流水线。"
            : taskContentMode === "static"
            ? "调优分镜文本、动态版式与配音，控制视频渲染流水线。"
            : taskContentModeSpec?.description || "调优分镜脚本、画面与配音，控制视频渲染流水线。"
        }
        actions={(
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-muted-foreground">{scenes.length} 个分镜 · {currentProgress}%</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsDeckCollapsed((prev) => !prev)}
              className="h-7 text-xs gap-1.5 px-2.5"
            >
              {isDeckCollapsed ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />}
              <span>{isDeckCollapsed ? "展开概览" : "收起概览"}</span>
            </Button>
          </div>
        )}
      />

      {/* 复合式吸顶操作台：十阶段流水线与生成/保存操作栏一体化吸顶 */}
      <div className="sticky top-0 z-20 w-full rounded-xl glass-panel p-3 border border-border/80 shadow-xs space-y-2.5 backdrop-blur-xl bg-card/85 dark:bg-card/75">
        {/* Tier 1: 十阶段流水线微缩轨 */}
        <WorkflowMiniRail
          workflow={workflowSnapshot}
          busy={isRunning}
          onOpenDetails={() => setIsWorkflowInspectorOpen(true)}
          onResume={task?.can_resume ? () => resumeMutation.mutate() : undefined}
          isResumePending={resumeMutation.isPending}
          activeStageKey={String(task?.current_stage || task?.active_job?.current_stage || "").toLowerCase()}
          variant="integrated"
        />

        {/* Tier 2: 故事板生成与编辑控制工具栏 */}
        <div className="flex flex-wrap items-center justify-between gap-2.5 pt-1.5 border-t border-border/40">
        <div className="flex flex-wrap items-center gap-2">
          {primaryAction === "save" && (
            <Button onClick={handleSaveAll} disabled={saveScenesMutation.isPending || updateTaskMutation.isPending} className="gap-1.5 h-9 px-3.5 text-sm" aria-label="保存故事板">
              {isSaved ? <CheckCircle2 aria-hidden="true" className="h-4 w-4" /> : <Save aria-hidden="true" className="h-4 w-4" />}
              {isSaved ? "已保存" : saveScenesMutation.isPending ? "保存中…" : "保存故事板"}
            </Button>
          )}
          {primaryAction === "cancel" && (
            <Button variant="destructive" onClick={() => setIsCancelConfirmOpen(true)} disabled={cancelWorkflowMutation.isPending} className="gap-1.5 h-9 px-3.5 text-sm">
              <StopCircle aria-hidden="true" className="h-4 w-4" />取消生成
            </Button>
          )}
          {primaryAction === "resume" && (
            <Button onClick={() => resumeMutation.mutate()} disabled={resumeMutation.isPending} className="gap-1.5 h-9 px-3.5 text-sm">
              {resumeMutation.isPending ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : <RotateCcw aria-hidden="true" className="h-4 w-4" />}恢复任务
            </Button>
          )}
          {primaryAction === "generate" && (
            <Button onClick={() => { if (requireSaved()) generateWorkflowMutation.mutate(); }} disabled={generateWorkflowMutation.isPending} className="gap-1.5 h-9 px-4 text-sm font-medium shadow-sm">
              <Play aria-hidden="true" className="h-4 w-4 fill-current" />全自动生成
            </Button>
          )}
          {primaryAction === "compose" && (
            <Button onClick={() => { if (requireSaved()) composeVideoMutation.mutate(); }} disabled={composeVideoMutation.isPending || isRunning || scenes.length === 0 || isDirty} className="gap-1.5 h-9 px-4 text-sm font-medium shadow-sm">
              {composeVideoMutation.isPending ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : <Clapperboard aria-hidden="true" className="h-4 w-4" />}合成成片
            </Button>
          )}
          {primaryAction === "publish" && (
            <Button onClick={() => { if (requireSaved()) setIsPublishOpen(true); }} disabled={!finalVideoUrl || isDirty} className="gap-1.5 h-9 px-4 text-sm font-medium shadow-sm">
              <Share2 aria-hidden="true" className="h-4 w-4" />发布到抖音
            </Button>
          )}

          {primaryAction !== "save" && (
            <Button variant="outline" onClick={handleSaveAll} disabled={saveScenesMutation.isPending || updateTaskMutation.isPending} className="gap-1.5 h-9 px-3.5 text-sm" aria-label="保存故事板">
              {isSaved ? <CheckCircle2 aria-hidden="true" className="h-4 w-4" /> : <Save aria-hidden="true" className="h-4 w-4" />}
              {isSaved ? "已保存" : "保存故事板"}
            </Button>
          )}

          {task.production_mode === "knowledge" && <Button
            variant="outline"
            size="sm"
            onClick={() => {
              if (!requireSaved()) return;
              setAiTopic(taskTitle || "");
              setIsAIOpen(true);
            }}
            disabled={isRunning || researchPending}
            className="gap-1.5 h-9 px-3.5 text-sm"
          >
            <Sparkles aria-hidden="true" className="h-4 w-4 text-primary" />
            AI 生成脚本
          </Button>}

          <div ref={moreMenuRef} className="relative inline-block">
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-haspopup="true"
              aria-expanded={isMoreMenuOpen}
              onClick={() => setIsMoreMenuOpen((prev) => !prev)}
              className="gap-1.5 h-9 px-3 text-sm text-muted-foreground hover:text-foreground"
            >
              更多操作
              <ChevronDown aria-hidden="true" className={`h-3.5 w-3.5 transition-transform duration-150 ${isMoreMenuOpen ? "rotate-180" : ""}`} />
            </Button>
            {isMoreMenuOpen && (
              <div
                role="menu"
                className="absolute left-0 z-40 mt-1 flex min-w-44 flex-col gap-0.5 rounded-xl border border-border/80 bg-popover/95 backdrop-blur-xl p-1 shadow-glass-hover animate-in fade-in zoom-in-95 duration-100"
              >
                <Button
                  variant="ghost"
                  size="sm"
                  className="justify-start h-8 text-xs font-normal"
                  onClick={() => {
                    setIsMoreMenuOpen(false);
                    if (requireSaved()) {
                      const activeMatch = availableTemplates.some((t) => t.id === renderTemplateId);
                      const targetId = activeMatch ? renderTemplateId : (availableTemplates[0]?.id || renderTemplateId);
                      const targetTpl = availableTemplates.find((t) => t.id === targetId) || templates.find((t) => t.id === targetId);
                      setRerenderTemplateId(targetId);
                      setRerenderParams(activeMatch ? renderParams : (targetTpl?.default_params || {}));
                      setRerenderBgmEnabled(bgmEnabled);
                      setRerenderBgmAssetId(bgmAssetId);
                      setRerenderBgmVolume(bgmVolume);
                      setIsRerenderOpen(true);
                    }
                  }}
                  disabled={isRunning || isDirty}
                >
                  <Clapperboard aria-hidden="true" className="mr-1.5 h-3.5 w-3.5" />更换模板重渲染
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="justify-start h-8 text-xs font-normal"
                  onClick={() => {
                    setIsMoreMenuOpen(false);
                    duplicateMutation.mutate();
                  }}
                  disabled={duplicateMutation.isPending}
                >
                  {duplicateMutation.isPending ? <Loader2 aria-hidden="true" className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Copy aria-hidden="true" className="mr-1.5 h-3.5 w-3.5" />}复制任务
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Right side quick progress & fold indicator */}
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {isRunning && (
            <span className="flex items-center gap-1.5 text-primary font-medium">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span>{liveStepMessage || "生成中…"}</span>
            </span>
          )}
          <span className="hidden sm:inline font-mono">
            {readySceneCount}/{scenes.length} 分镜就绪
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setIsDeckCollapsed((prev) => !prev)}
            className="h-7 text-xs gap-1 px-2 text-muted-foreground hover:text-foreground"
          >
            {isDeckCollapsed ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
            <span>{isDeckCollapsed ? "展开概览" : "收起概览"}</span>
          </Button>
        </div>
      </div>
      </div>

      <WorkflowInspectorDialog
        open={isWorkflowInspectorOpen}
        onClose={() => setIsWorkflowInspectorOpen(false)}
        taskId={taskId}
        busy={isRunning}
        requireSaved={requireSaved}
      />

      {/* Critical Task Failure Alert Banner */}
      {currentStatus === "failed" && (
        <div className="rounded-lg border border-destructive/30 bg-destructive-soft p-4 space-y-3 motion-safe:animate-in motion-safe:fade-in">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
            <div className="flex items-start gap-2.5 min-w-0">
              <AlertCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
              <div className="space-y-1.5 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-destructive">任务生成失败</h3>
                  <Badge variant="destructive" className="text-xs">
                    失败
                  </Badge>
                </div>
                <p className="text-xs text-foreground font-mono leading-relaxed break-words bg-background/80 p-2.5 rounded border border-destructive/20 select-text">
                  {liveStepMessage || task?.error_message || "生成已中断，请检查 Provider 配置或网络连接。"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0 self-end sm:self-start">
              <Button
                size="sm"
                variant="default"
                onClick={() => retryWorkflowMutation.mutate()}
                disabled={retryWorkflowMutation.isPending || isRunning}
                className="gap-1 text-xs h-8"
              >
                {retryWorkflowMutation.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RotateCcw className="h-3.5 w-3.5" />
                )}
                重试全自动生成
              </Button>
              <Link href="/settings">
                 <Button size="sm" variant="outline" className="gap-1 text-xs h-8 border-destructive/30 text-destructive hover:bg-destructive-soft">
                  <Key className="h-3 w-3" />
                  检查设置
                </Button>
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* AI Dependency Readiness & Missing Key Impact Checklist Banner */}
      {criticalMissing.length > 0 && (
        <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 space-y-2.5 text-xs motion-safe:animate-in motion-safe:fade-in">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-warning shrink-0" />
              <div className="font-medium text-foreground flex items-center gap-2 flex-wrap">
                <span>Provider 配置诊断</span>
                <Badge variant="destructive" className="text-xs">
                  {criticalMissing.length} 项关键 Provider 未就绪
                </Badge>
                {missingItems.length - criticalMissing.length > 0 && (
                  <Badge variant="warning" className="text-xs">
                    {missingItems.length - criticalMissing.length} 项 Provider 需关注 · {pendingTestItems.length} 项待测试
                  </Badge>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-muted-foreground hover:text-foreground gap-1 px-2"
                onClick={() => setShowReadinessDetails(!showReadinessDetails)}
              >
                {showReadinessDetails ? (
                  <>
                    <ChevronUp className="h-3.5 w-3.5" />
                    收起详情
                  </>
                ) : (
                  <>
                    <ChevronDown className="h-3.5 w-3.5" />
                    查看详情 ({missingItems.length})
                  </>
                )}
              </Button>
              <Link href="/settings">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs gap-1 px-2.5"
                >
                  <Key className="h-3 w-3" />
                  去设置
                </Button>
              </Link>
            </div>
          </div>

          {/* Collapsible Details Table */}
          {showReadinessDetails && (
            <div className="pt-2 border-t border-border space-y-2">
              <div className="text-xs text-muted-foreground">
                已保存但未测试的 Provider 会单独标记；缺少关键 Provider 时，相关生成环节将无法执行。
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {readinessItems.map((item) => (
                  <div
                    key={item.type}
                    className={`p-2.5 rounded-md border text-xs flex items-start justify-between gap-2 ${
                      item.ready
                        ? "bg-success/5 border-success/20 text-foreground"
                        : item.status === "not_tested"
                        ? "bg-warning/5 border-warning/20 text-foreground"
                        : item.critical
                        ? "bg-destructive/5 border-destructive/20 text-foreground"
                        : "bg-warning/5 border-warning/20 text-foreground"
                    }`}
                  >
                    <div className="space-y-0.5 min-w-0">
                      <div className="flex items-center gap-1.5">
                        {item.ready ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-success shrink-0" />
                        ) : item.status === "not_tested" ? (
                          <Info className="h-3.5 w-3.5 text-warning shrink-0" />
                        ) : item.critical ? (
                          <AlertCircle className="h-3.5 w-3.5 text-destructive shrink-0" />
                        ) : (
                          <Info className="h-3.5 w-3.5 text-warning shrink-0" />
                        )}
                        <span className="font-semibold">{item.title}</span>
                        <Badge
                          variant="outline"
                          className={`text-xs ${
                            item.ready
                              ? "text-success border-success/30"
                              : item.status === "not_tested"
                              ? "text-warning border-warning/30"
                              : item.critical
                              ? "text-destructive border-destructive/30"
                              : "text-warning border-warning/30"
                          }`}
                        >
                          {item.ready ? "连接可用" : item.status === "not_tested" ? "已配置待测试" : item.status === "failed" ? "连接失败" : item.critical ? "未配置，无法执行" : "未配置，功能受限"}
                        </Badge>
                      </div>
                      {!item.ready && (
                        <div className="text-xs text-muted-foreground space-y-0.5 pl-5">
                          <div><span className="text-foreground font-medium">影响：</span>{item.impact}</div>
                          <div><span className="text-foreground font-medium">方案：</span>{item.solution}</div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {scheduledPublish && (
        <Card className="border-primary/25 bg-primary-soft/40">
          <CardContent className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-start gap-2.5">
              <Send aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <div className="min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-foreground">
                  <span>完成后自动发布</span>
                  <StatusBadge
                    label={PUBLISH_STATUS_LABELS[scheduledPublishStatus] || scheduledPublishStatus}
                    tone={scheduledPublishStatus === "published" ? "success" : scheduledPublishStatus === "failed" ? "destructive" : scheduledPublishStatus === "cancelled" ? "neutral" : "primary"}
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  {scheduledPublish.scheduled_at
                    ? `计划：${new Date(scheduledPublish.scheduled_at).toLocaleString("zh-CN", { timeZone: scheduledPublish.timezone || undefined })}`
                    : "生成完成后立即进入发布队列"}
                  {scheduledPublish.timezone ? ` · ${scheduledPublish.timezone}` : ""}
                  {scheduledPublish.account_id
                    ? ` · 账号：${publishingAccounts.find((account) => account.id === scheduledPublish.account_id)?.account_name || scheduledPublish.account_id}`
                    : ""}
                </p>
                {scheduledPublish.error_message && (
                  <p className="text-xs text-destructive">{scheduledPublish.error_message}</p>
                )}
              </div>
            </div>
            {canCancelScheduledPublish && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="shrink-0 gap-1.5"
                disabled={cancelScheduledPublishMutation.isPending}
                onClick={() => cancelScheduledPublishMutation.mutate()}
              >
                {cancelScheduledPublishMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <StopCircle aria-hidden="true" className="h-3.5 w-3.5" />}
                取消自动发布
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {task.production_mode === "commerce" && <CommercePreflightCard taskId={taskId} busy={isRunning} />}

      {/* Top Workspace Grid: Left Video Preview / Center Pipeline / Right Metadata (Collapsible) */}
      {isDeckCollapsed ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card/60 px-4 py-2.5 text-xs">
          <div className="flex flex-wrap items-center gap-3">
            <span className="font-semibold text-foreground">工作区概览已收起</span>
            <span className="text-border">|</span>
            <span className="text-muted-foreground">
              排版模板：<strong className="text-foreground">{selectedTemplateName}</strong>
            </span>
            <span className="text-border">·</span>
            <span className="text-muted-foreground">
              画面来源：<strong className="text-foreground">{taskContentModeLabel}</strong>
            </span>
            {finalVideoUrl ? (
              <a
                href={finalVideoUrl}
                target="_blank"
                rel="noreferrer"
                download
                className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
              >
                <Film className="h-3.5 w-3.5" />
                成片已就绪（点击下载 MP4）
              </a>
            ) : (
              <span className="text-muted-foreground">成片未合成</span>
            )}
            {currentStatus === "failed" && (
              <Badge variant="destructive" className="text-xs gap-1">
                <AlertCircle className="h-3 w-3" />
                生成中断
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono font-medium text-foreground">{currentProgress}%</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsDeckCollapsed(false)}
              className="h-6 px-2.5 text-xs gap-1"
            >
              <ChevronDown className="h-3 w-3" />
              展开概览
            </Button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3.5">
        {/* Left: Video Preview Player if ready or placeholder */}
        <Card className="flex flex-col justify-between overflow-hidden">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                 成片预览
              </CardTitle>
              {finalVideoUrl && (
                 <StatusBadge label="已就绪" tone="success" />
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {finalVideoUrl ? (
              <div className="space-y-3">
                <div className={`${videoAspectClass} mx-auto bg-black rounded-lg overflow-hidden flex items-center justify-center border border-border shadow-sm`}>
                  <video
                    key={finalVideoUrl}
                    src={finalVideoUrl}
                    controls
                    playsInline
                    preload="metadata"
                    className="h-full w-full object-contain"
                  />
                </div>
                <div className="pt-1">
                  <div className="flex items-center justify-between text-xs">
                    <a
                      href={finalVideoUrl}
                      target="_blank"
                      rel="noreferrer"
                      download
                      className="text-primary hover:underline text-xs font-medium inline-flex items-center gap-1 font-mono truncate max-w-[180px]"
                    >
                      <ExternalLink className="h-3 w-3 shrink-0" />
                      下载成片 MP4
                    </a>
                  </div>
                </div>
              </div>
            ) : isRunning ? (
              <div className={`${videoPlaceholderAspectClass} mx-auto bg-secondary/40 rounded-lg border border-dashed border-border flex flex-col items-center justify-center p-4 text-center text-muted-foreground animate-pulse`}>
                <Loader2 className="h-7 w-7 mb-2 animate-spin text-primary" />
                <p className="text-xs font-medium text-foreground">{liveStepMessage || "正在重新合成视频…"}</p>
                <p className="text-xs opacity-70 mt-0.5">将自动载入新模板成片预览</p>
              </div>
            ) : (
              <div className={`${videoPlaceholderAspectClass} mx-auto bg-secondary/40 rounded-lg border border-dashed border-border flex flex-col items-center justify-center p-4 text-center text-muted-foreground`}>
                <Film className="h-7 w-7 mb-1.5 opacity-50" />
                <p className="text-xs font-medium">成片尚未合成</p>
                <p className="text-xs opacity-70 mt-0.5">点击上方“合成成片”生成视频</p>
              </div>
            )}
          </CardContent>
          <div className="border-t border-border/60 px-3 py-2.5">
            <Button size="sm" variant="outline" className="gap-1.5" disabled={isRunning || isDirty || regenerateMetadataMutation.isPending} onClick={() => regenerateMetadataMutation.mutate()}>
              {regenerateMetadataMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              {regenerateMetadataMutation.isPending ? "正在生成发布信息…" : "重新生成标题、描述和话题"}
            </Button>
          </div>
          {taskMetadata && (
             <div className="border-t border-border/60 px-3 py-2.5 space-y-1.5 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-foreground">平台发布信息</span>
                <span className="text-muted-foreground">{PLATFORM_LABELS[taskMetadata.platform || "douyin"] || taskMetadata.platform || "抖音"}</span>
              </div>
              {taskMetadata.description && (
                <p className="text-muted-foreground leading-relaxed">{taskMetadata.description}</p>
              )}
              {Array.isArray(taskMetadata.tags) && taskMetadata.tags.length > 0 && (
                <div className="flex flex-wrap gap-1">
                   {taskMetadata.tags.map((tag) => (
                     <Badge key={tag} variant="outline" className="text-xs px-1.5 py-0">
                      #{tag}
                    </Badge>
                  ))}
                </div>
              )}
              {taskMetadata.declaration && (
                 <p className="text-xs text-muted-foreground">内容声明：{taskMetadata.declaration}</p>
              )}
            </div>
          )}
           <div className="border-t border-border/60 bg-secondary/30 p-3 text-xs text-muted-foreground flex justify-between">
            <span>旁白字数: {totalWords} 字</span>
          </div>
        </Card>

        {/* Center & Right: Task Status & Creative Config */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold">任务概览与创作信息</CardTitle>
                <div className="flex items-center gap-2">
                  <Badge variant={isTaskEventsConnected ? "success" : "warning"} className="text-xs">
                    {isTaskEventsConnected ? "实时连接" : "重连中"}
                  </Badge>
                  <span className="text-xs font-mono font-semibold text-foreground">
                    {currentProgress}%
                  </span>
                </div>
              </div>
              <CardDescription className={currentStatus === "failed" ? "text-destructive font-medium" : ""}>
                {liveStepMessage ||
                  (currentStatus === "failed"
                    ? (task?.error_message || "任务生成中断，请查看上方失败详情")
                    : currentStatus === "completed"
                    ? "视频生成与合成完成，故事板已就绪"
                    : "就绪，等待启动全自动生成")}
              </CardDescription>
              {task.active_job && (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground pt-1">
                  <span>
                    阶段：
                    <strong className="text-foreground">
                      {task.current_stage_label || task.current_stage || task.active_job.current_stage || "排队中"}
                    </strong>
                  </span>
                  {(task.resume_count || task.active_job.retry_count) > 0 && (
                    <Badge variant="outline" className="text-xs">
                      重试：{task.resume_count || task.active_job.retry_count}/{task.active_job.max_retries}
                    </Badge>
                  )}
                  {liveCurrentScene && liveTotalScenes && <span>当前分镜：{liveCurrentScene}/{liveTotalScenes}</span>}
                  {task.can_resume && <Badge variant="outline" className="text-xs">可恢复</Badge>}
                </div>
              )}
              <div className="text-xs text-muted-foreground">
                模板：<strong className="text-foreground">{selectedTemplateName}</strong>
                <span className="mx-1.5">·</span>
                画面来源：<strong className="text-foreground">{taskContentModeLabel}</strong>
              </div>
              <div className="flex items-center justify-between gap-3 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs">
                <div className="min-w-0">
                  <span className="text-muted-foreground">下一步：</span>
                  <strong className="text-foreground">{nextAction}</strong>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs font-mono text-muted-foreground">
                    {readySceneCount}/{scenes.length || 0} 分镜就绪
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setIsWorkflowInspectorOpen(true)}
                    className="h-7 text-xs px-2.5 gap-1.5 font-medium"
                  >
                    <span>流水线与制品库</span>
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3.5">
              <Progress value={currentProgress} className="h-1.5" />

              {/* Task Title & Hook Edit */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3 border-t border-border/40">
                <div className="space-y-1">
                  <label htmlFor="task-title" className="text-xs font-medium text-foreground">视频标题</label>
                  <Input
                    id="task-title"
                    value={taskTitle}
                    onChange={(e) => {
                      setTaskTitle(e.target.value);
                      markDirty();
                    }}
                    placeholder="例如：第 1 集：什么是量子纠缠？"
                  />
                </div>
                <div className="space-y-1">
                   <label htmlFor="task-description" className="text-xs font-medium text-foreground">前 3 秒开场钩子</label>
                  <Input
                    id="task-description"
                    value={taskDesc}
                    onChange={(e) => {
                      setTaskDesc(e.target.value);
                      markDirty();
                    }}
                    placeholder="例如：你知道吗？90% 的人都不知道这个物理真相！"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <CardTitle className="flex items-center gap-1.5 text-sm font-semibold">
                    <Layers className="h-3.5 w-3.5 text-primary" />
                    成片配置
                  </CardTitle>
                </div>
                   {isDirty && <span className="text-xs text-warning">待保存</span>}
              </div>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_auto]">
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <label htmlFor="render-template" className="text-xs font-medium text-foreground">排版模板</label>
                  <Select
                    id="render-template"
                    value={renderTemplateId}
                    onChange={(event) => {
                      const next = event.target.value;
                      const item = templates.find((candidate) => candidate.id === next);
                      setRenderTemplateId(next);
                      setRenderParams(item?.default_params || {});
                      markDirty();
                    }}
                  >
                    {availableTemplates.map((item) => (
                      <option key={item.id} value={item.id}>{formatTemplateName(item.id, item.name)}</option>
                    ))}
                  </Select>
                </div>

                {selectedTemplate && selectedTemplate.parameter_schema.length > 0 && (
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {selectedTemplate.parameter_schema.map((parameter) => (
                      <div key={parameter.name} className="space-y-1.5">
                        <label htmlFor={`render-param-${parameter.name}`} className="text-xs text-muted-foreground">
                          {formatParamLabel(parameter.name, parameter.label)}
                        </label>
                        <Input
                          id={`render-param-${parameter.name}`}
                          value={String(renderParams[parameter.name] ?? parameter.default ?? "")}
                          type={parameter.type === "number" ? "number" : parameter.type === "color" ? "text" : "text"}
                          onChange={(event) => {
                            setRenderParams((current) => ({
                              ...current,
                              [parameter.name]: event.target.value,
                            }));
                            markDirty();
                          }}
                          className="h-8 text-xs"
                        />
                      </div>
                    ))}
                  </div>
                )}

                <div className="space-y-2 rounded-md border border-border/60 bg-secondary/20 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <label htmlFor="render-bgm-enabled" className="flex items-center gap-2 text-xs font-medium text-foreground">
                      <input
                        id="render-bgm-enabled"
                        type="checkbox"
                        checked={bgmEnabled}
                        onChange={(event) => {
                          setBgmEnabled(event.target.checked);
                          markDirty();
                        }}
                        className="rounded border-border text-primary focus:ring-primary"
                      />
                      <Music className="h-3.5 w-3.5 text-primary" />
                      背景音乐
                    </label>
                    <span className="text-xs text-muted-foreground">{bgmEnabled ? "混入成片" : "关闭"}</span>
                  </div>
                  <Select
                    id="render-bgm"
                    value={bgmAssetId}
                    disabled={!bgmEnabled}
                    onChange={(event) => {
                      setBgmAssetId(event.target.value);
                      markDirty();
                    }}
                  >
                    <option value="">使用项目默认背景音乐</option>
                    {projectBgm.map((asset) => (
                      <option key={asset.id} value={asset.id}>{asset.file_name}</option>
                    ))}
                  </Select>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>音量</span>
                    <input
                      aria-label="背景音乐音量"
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={bgmVolume}
                      disabled={!bgmEnabled}
                      onChange={(event) => {
                        setBgmVolume(parseFloat(event.target.value));
                        markDirty();
                      }}
                      className="h-1.5 flex-1 accent-primary"
                    />
                    <span className="w-8 text-right font-mono text-xs">{Math.round(bgmVolume * 100)}%</span>
                  </div>
                  {selectedBgm && (
                    <audio
                      controls
                      preload="none"
                      src={`/api/v1/assets/${selectedBgm.id}/file`}
                      className="h-8 w-full"
                    />
                  )}
                </div>
              </div>

              <div className="flex flex-col items-center gap-2">
                <span className="self-start text-xs font-medium text-foreground">模板预览</span>
                <div className={`overflow-hidden rounded-md border border-border bg-black ${
                  projectAspect === "16:9"
                    ? "w-44 h-25 aspect-video"
                    : projectAspect === "1:1"
                    ? "w-32 h-32 aspect-square"
                    : "w-24 h-44 aspect-[9/16]"
                }`}>
                  <img
                    src={`/api/v1/templates/previews/${encodeURIComponent(renderTemplateId)}`}
                    alt={selectedTemplate ? `${selectedTemplateName} 预览` : "模板预览"}
                    className="h-full w-full object-cover"
                  />
                </div>
                <span className="text-center text-xs text-muted-foreground font-mono">
                  {selectedTemplate?.width || (projectAspect === "16:9" ? 1920 : 1080)} × {selectedTemplate?.height || (projectAspect === "16:9" ? 1080 : 1920)}
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
      )}

      {/* Storyboard Scenes List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold tracking-tight text-foreground">
            故事板分镜（{scenes.length} 个片段）
          </h2>
          <Button size="sm" variant="outline" onClick={handleAddScene} className="gap-1.5 text-sm h-9 px-3.5">
            <Plus aria-hidden="true" className="h-4 w-4" />
            添加分镜
          </Button>
        </div>

        <div className="space-y-3">
          {scenes.map((scene, index) => {
            const dbScene = task?.scenes?.[index];
            const hasAudio = Boolean(dbScene?.audio_asset_id);
            const hasImage = Boolean(dbScene?.media_asset_id);
            const hasVideo = Boolean(dbScene?.rendered_segment_asset_id || (dbScene?.media_asset_id && dbScene?.layout_params?.media_type === "video"));
            const contentMode = task?.input_payload?.content_mode || "generated_image";
            const sceneAsset = projectAssets.find((asset) => asset.id === dbScene?.media_asset_id);
            const sceneMediaType = dbScene?.layout_params?.media_type || sceneAsset?.asset_type;
            const sceneMediaSource = dbScene?.layout_params?.media_source;
            const isManualSceneAsset = Boolean(
              dbScene?.media_asset_id &&
              (contentMode === "uploaded_asset" ||
                sceneMediaSource === "manual" ||
                sceneMediaSource === "uploaded")
            );

            return (
              <Card
                key={index}
                data-testid="scene-card"
                className="glass-card rounded-xl hover:border-primary/40 hover:shadow-glass-hover transition-all duration-200 overflow-hidden"
              >
                <div className="flex flex-col md:flex-row md:items-stretch">
                  {/* Left Column: Sequence Index and Reorder Controls */}
                  <div className="p-3.5 bg-card/40 backdrop-blur-md md:w-16 flex md:flex-col items-center justify-between border-b md:border-b-0 md:border-r border-border/70 shrink-0">
                    <span className="rounded bg-background/90 px-2 py-1 text-xs font-mono font-bold text-foreground border border-border/60">
                      #{String(index + 1).padStart(2, "0")}
                    </span>

                    <div className="flex md:flex-col items-center gap-1.5">
                      <button
                        type="button"
                        disabled={index === 0}
                        onClick={() => handleMoveUp(index)}
                        aria-label={`上移第 ${index + 1} 个分镜`}
                        className="h-7 w-7 inline-flex items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground disabled:opacity-20 transition-colors cursor-pointer"
                        title="上移分镜"
                      >
                        <MoveUp aria-hidden="true" className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        disabled={index === scenes.length - 1}
                        onClick={() => handleMoveDown(index)}
                        aria-label={`下移第 ${index + 1} 个分镜`}
                        className="h-7 w-7 inline-flex items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground disabled:opacity-20 transition-colors cursor-pointer"
                        title="下移分镜"
                      >
                        <MoveDown aria-hidden="true" className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => requestDeleteScene(index)}
                        aria-label={`删除第 ${index + 1} 个分镜`}
                        className="h-7 w-7 inline-flex items-center justify-center rounded text-muted-foreground hover:bg-destructive-soft hover:text-destructive transition-colors cursor-pointer"
                        title="删除分镜"
                      >
                        <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Right Column: Scene Content & Editor */}
                  <div className="p-4 flex-1 space-y-3">
                    {/* Media Preview Strip if available */}
                    {(hasImage || hasVideo || hasAudio || contentMode === "static") && dbScene && (
                      <div className="flex flex-wrap items-center gap-3 rounded-md border border-border/60 bg-secondary/15 p-2.5">
                        {(hasImage || hasVideo || contentMode === "static") && (
                          <div className={`relative ${sceneThumbAspectClass} overflow-hidden rounded-md border border-border bg-black shrink-0`}>
                            {contentMode === "static" ? (
                              <img
                                src={`/api/v1/templates/previews/${encodeURIComponent(renderTemplateId)}`}
                                alt={`分镜 ${index + 1} 模板预览`}
                                className="h-full w-full object-cover"
                              />
                            ) : sceneMediaType === "video" ? (
                              <video
                                src={`/api/v1/assets/${dbScene.media_asset_id}/file`}
                                controls
                                className="h-full w-full object-cover"
                              />
                            ) : (
                              <img
                                src={`/api/v1/assets/${dbScene.media_asset_id}/file`}
                                alt={`分镜 ${index + 1}`}
                                className="h-full w-full object-cover"
                              />
                            )}
                          </div>
                        )}
                        {hasAudio && (
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground">配音试听:</span>
                            <audio
                              controls
                              preload="none"
                              src={`/api/v1/assets/${dbScene.audio_asset_id}/file`}
                              className="h-8 max-w-[240px]"
                            />
                          </div>
                        )}
                      </div>
                    )}

                    <div className="space-y-2 rounded-lg border border-primary/15 bg-primary/[0.03] p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-foreground">信息逻辑</span>
                        <div className="flex flex-wrap justify-end gap-1">
                          {(scene.source_refs || []).map((sourceRef) => (
                            <Badge key={sourceRef} variant="outline" className="max-w-[180px] truncate font-mono text-[10px]">
                              来源 {sourceRef}
                            </Badge>
                          ))}
                        </div>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                        <div className="space-y-1.5">
                          <label htmlFor={`scene-${index}-visual-role`} className="text-xs font-medium text-muted-foreground">
                            视觉角色
                          </label>
                          <Select
                            id={`scene-${index}-visual-role`}
                            value={scene.visual_role || "concept"}
                            onChange={(event) => handleSceneChange(index, "visual_role", event.target.value as VisualRole)}
                            className="h-9 text-sm"
                          >
                            {VISUAL_ROLE_OPTIONS.map((role) => (
                              <option key={role.value} value={role.value}>{role.label}</option>
                            ))}
                          </Select>
                        </div>
                        <div className="space-y-1.5">
                          <label htmlFor={`scene-${index}-claim-refs`} className="text-xs font-medium text-muted-foreground">
                            对应主张 ID
                          </label>
                          <Input
                            id={`scene-${index}-claim-refs`}
                            value={(scene.claim_refs || []).join(", ")}
                            onChange={(event) =>
                              handleSceneChange(
                                index,
                                "claim_refs",
                                event.target.value.split(",").map((value) => value.trim()).filter(Boolean),
                              )
                            }
                            placeholder="claim-1, claim-2"
                            className="h-9 text-sm font-mono"
                          />
                        </div>
                        <div className="space-y-1.5">
                          <label htmlFor={`scene-${index}-source-refs`} className="text-xs font-medium text-muted-foreground">
                            来源 ID
                          </label>
                          <Input
                            id={`scene-${index}-source-refs`}
                            value={(scene.source_refs || []).join(", ")}
                            onChange={(event) =>
                              handleSceneChange(
                                index,
                                "source_refs",
                                event.target.value.split(",").map((value) => value.trim()).filter(Boolean),
                              )
                            }
                            placeholder="source-a1b2c3"
                            className="h-9 text-sm font-mono"
                          />
                        </div>
                      </div>
                      <p className="text-[11px] leading-relaxed text-muted-foreground">
                        视觉角色决定画面应如何解释信息；主张和来源 ID 会随故事板保存，不再塞进排版参数。
                      </p>
                    </div>

                    {/* Narration Textarea */}
                    <div className="space-y-1.5">
                      <div className="flex justify-between items-center text-xs">
                        <label htmlFor={`scene-${index}-narration`} className="text-sm font-medium text-foreground">分镜旁白</label>
                        <span className="text-xs font-mono text-muted-foreground">
                          {scene.narration_text?.length || 0} 字
                        </span>
                      </div>
                      <Textarea
                        id={`scene-${index}-narration`}
                        placeholder="输入此分镜对应的配音解说词…"
                        value={scene.narration_text}
                        onChange={(e) =>
                          handleSceneChange(index, "narration_text", e.target.value)
                        }
                        rows={3}
                        className="text-sm leading-relaxed resize-y p-3"
                      />
                    </div>

                    {/* Visual Prompt, Duration & Bound Asset */}
                    <div className="grid grid-cols-1 sm:grid-cols-12 gap-3">
                      {usesVisualPrompt && (
                        <div className="sm:col-span-6 space-y-1.5">
                          <label htmlFor={`scene-${index}-prompt`} className="text-xs font-medium text-muted-foreground">画面提示词</label>
                          <Input
                            id={`scene-${index}-prompt`}
                            placeholder="例如：发光处理器特写，实验室环境，低机位中景，冷色侧光，主体清晰入镜"
                            value={scene.visual_prompt}
                            onChange={(e) =>
                              handleSceneChange(index, "visual_prompt", e.target.value)
                            }
                            className="text-sm font-mono h-9"
                          />
                        </div>
                      )}

                      <div className={`${usesVisualPrompt ? "sm:col-span-2" : "sm:col-span-4"} space-y-1.5`}>
                        <label htmlFor={`scene-${index}-duration`} className="text-xs font-medium text-muted-foreground">时长（秒）</label>
                        <Input
                          id={`scene-${index}-duration`}
                          type="number"
                          step="0.5"
                          min="1"
                          max="60"
                          value={scene.duration_seconds}
                          onChange={(e) =>
                            handleSceneChange(
                              index,
                              "duration_seconds",
                              parseFloat(e.target.value) || 4.0
                            )
                          }
                          className="text-sm h-9"
                        />
                      </div>

                      <div className={`${usesVisualPrompt ? "sm:col-span-4" : "sm:col-span-8"} space-y-1.5`}>
                        <label htmlFor={`scene-${index}-asset`} className="text-xs font-medium text-muted-foreground">
                          {contentMode === "uploaded_asset" ? "本镜头素材" : "本镜头覆盖素材（可选）"}
                        </label>
                        <Select
                          id={`scene-${index}-asset`}
                          value={scene.media_asset_id || ""}
                          className="text-sm h-9"
                          onChange={(e) => {
                            const selected = projectAssets.find((asset) => asset.id === e.target.value);
                            const updated = [...scenes];
                            updated[index] = {
                              ...updated[index],
                              media_asset_id: e.target.value || null,
                              layout_params: {
                                ...(updated[index].layout_params || {}),
                                media_type: selected?.asset_type || undefined,
                              },
                            };
                            markDirty();
                            setScenes(updated);
                          }}
                          >
                            <option value="">
                              {taskContentMode === "online_asset"
                                ? "自动匹配素材库视频"
                                : taskContentMode === "static"
                                ? "文字排版（无需素材）"
                                : taskContentMode === "uploaded_asset"
                                ? "请选择我的素材"
                                : taskContentMode === "generated_video"
                                ? "使用 AI 生成视频"
                                : "使用 AI 生成图片"}
                            </option>
                          {projectAssets.filter((asset) => asset.asset_type === "image" || asset.asset_type === "video").map((asset) => (
                            <option key={asset.id} value={asset.id}>{asset.file_name}（{ASSET_TYPE_LABELS[asset.asset_type] || asset.asset_type}）</option>
                          ))}
                        </Select>
                      </div>
                    </div>

                    {/* 统一分镜流水线单元控制条：融合生成触发、流水线状态、失效重试、手工保护与产物下载 */}
                    <ScenePipelineStatus
                      taskId={taskId}
                      sceneId={dbScene?.id}
                      sceneIndex={index}
                      workflow={workflowSnapshot}
                      busy={isRunning}
                      isManualAsset={isManualSceneAsset}
                      onRetryUnit={handleRetryWorkflowUnit}
                      isUnitRetrying={Boolean(
                        retryingUnits[`voice-${dbScene?.id}`] || retryingUnits[`assets-${dbScene?.id}`]
                      )}
                      onGenerateTTS={() => handleGenerateTTS(dbScene?.id || "", index)}
                      onGenerateImage={() => handleGenerateImage(dbScene?.id || "", index)}
                      onGenerateVideo={() => handleGenerateVideo(dbScene?.id || "", index)}
                      isGeneratingTTS={generatingTTS[dbScene?.id || index]}
                      isGeneratingImage={generatingImage[dbScene?.id || index]}
                      isGeneratingVideo={generatingVideo[dbScene?.id || index]}
                      contentMode={taskContentMode}
                      hasAudio={hasAudio}
                      hasVisual={hasImage || hasVideo}
                      hasVideo={hasVideo}
                      canGenerateVoice={Boolean(scene.narration_text)}
                      canGenerateVisual={Boolean(scene.visual_prompt || scene.narration_text)}
                      measuredDuration={Number(dbScene?.layout_params?.video_actual_duration_seconds) || null}
                      errorMessage={dbScene?.layout_params?.image_error || dbScene?.layout_params?.video_error || dbScene?.layout_params?.tts_error || null}
                    />
                  </div>
                </div>
              </Card>
            );
          })}
        </div>

      </div>

      {/* AI Script Assistant Dialog */}
      <Dialog open={isAIOpen} onClose={() => setIsAIOpen(false)} className="max-w-2xl max-h-[88vh]">
        <DialogHeader>
          <DialogTitle>AI 知识脚本生成</DialogTitle>
          <DialogDescription>
            基于主题、Knowledge Brief 和来源，生成带视觉角色与出处关系的结构化分镜。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Missing LLM Prompt inside Dialog */}
          {!llmConfigured && (
            <div className="space-y-1.5 rounded-md border border-warning/30 bg-warning-soft p-3 text-sm text-warning">
              <div className="flex items-center gap-1.5 font-medium">
                <AlertCircle aria-hidden="true" className="h-4 w-4 shrink-0" />
                未配置大语言模型 Provider 或缺少 API 密钥
              </div>
              <p className="text-xs leading-5 text-muted-foreground">
                AI 剧本创作需要语言模型 Provider。请前往设置中心配置大语言模型 (LLM)，也可以关闭窗口手动录入台词与画面提示词。
              </p>
              <Link href="/settings" className="inline-block pt-1">
                <Button size="sm" variant="outline" className="gap-1 border-warning/40 text-warning hover:bg-warning-soft">
                  <Key aria-hidden="true" className="h-3.5 w-3.5" />
                  前往设置中心
                </Button>
              </Link>
            </div>
          )}

          <div className="space-y-1">
            <label htmlFor="ai-topic" className="text-xs font-semibold text-foreground">视频标题</label>
            <div className="flex gap-2">
              <Input
                id="ai-topic"
                value={aiTopic}
                onChange={(e) => setAiTopic(e.target.value)}
                placeholder="例如：为什么量子隐形传态颠覆了传统通信？"
              />
              <Button
                type="button"
                variant="outline"
                disabled={researchPending || isRunning || !aiTopic.trim()}
                onClick={() => researchMutation.mutate()}
                className="gap-1 shrink-0 text-xs"
              >
                {researchMutation.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Search className="h-3.5 w-3.5" />
                )}
                全网调研
              </Button>
            </div>
            {!searchConfigured && (
              <p className="flex items-center gap-1 pt-0.5 text-xs text-muted-foreground">
                <Info aria-hidden="true" className="h-3.5 w-3.5 text-info shrink-0" />
                未配置事实检索 Provider：全网调研会跳过外部检索，直接基于语言模型已有知识生成。
              </p>
            )}
            {taskResearch && (
              <div className={`rounded border px-2 py-1.5 text-xs ${
                taskResearch.status === "completed"
                  ? "border-success/30 bg-success-soft text-success"
                  : taskResearch.status === "pending"
                  ? "border-info/30 bg-info-soft text-info"
                  : "border-warning/30 bg-warning-soft text-warning"
              }`}>
                {taskResearch.status === "completed"
                  ? `已使用 ${taskResearch.provider || "检索 Provider"} 的实时资料`
                  : taskResearch.status === "pending" && taskResearch.started_at
                  ? "正在联网搜索，搜索完成后才能生成脚本"
                  : taskResearch.error_message || taskResearch.summary}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label htmlFor="ai-genre" className="text-xs font-semibold text-foreground">知识方向</label>
              <Select
                id="ai-genre"
                value={aiGenre}
                onChange={(e) => setAiGenre(e.target.value)}
              >
                {GENRE_OPTIONS.map((g) => (
                  <option key={g.value} value={g.value}>
                    {g.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <label htmlFor="ai-hook" className="text-xs font-semibold text-foreground">开场钩子</label>
              <Select
                id="ai-hook"
                value={aiHookType}
                onChange={(e) => setAiHookType(e.target.value)}
              >
                {HOOK_OPTIONS.map((h) => (
                  <option key={h.value} value={h.value}>
                    {h.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {usesVisualPrompt ? (
              <div className="space-y-1">
                <label htmlFor="ai-style" className="text-xs font-semibold text-foreground">视觉风格</label>
                <Select
                  id="ai-style"
                  value={aiStylePreset}
                  onChange={(e) => setAiStylePreset(e.target.value)}
                >
                  {STYLE_PRESET_OPTIONS.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </Select>
              </div>
            ) : (
              <div className="space-y-1">
                <span className="text-xs font-semibold text-foreground">素材媒介模式</span>
                <div className="h-9 rounded-md border border-border bg-secondary/40 px-3 flex items-center text-xs text-muted-foreground font-medium">
                  {taskContentMode === "online_asset" ? "素材库实拍视频（不使用 AI 兜底）" : taskContentMode === "uploaded_asset" ? "我的素材（用户绑定后保持不变）" : "文字排版字效"}
                </div>
              </div>
            )}
            <div className="space-y-1">
              <label htmlFor="ai-scene-count" className="text-xs font-semibold text-foreground">期望分镜数量</label>
              <Input
                id="ai-scene-count"
                type="number"
                min={SCENE_COUNT_MIN}
                max={SCENE_COUNT_MAX}
                value={aiSceneCount}
                onChange={(e) =>
                  setAiSceneCount(
                    Math.min(
                      SCENE_COUNT_MAX,
                      Math.max(SCENE_COUNT_MIN, parseInt(e.target.value) || SCENE_COUNT_MIN)
                    )
                  )
                }
              />
              <p className="text-xs text-muted-foreground">建议 8–20 段，生成后可在故事板中继续调整。</p>
            </div>
          </div>

          {/* Research Results Snippet */}
          {researchData && (
            <div className="p-3 bg-secondary/50 rounded-md space-y-1.5 text-xs">
              <div className="font-semibold text-foreground flex items-center gap-1.5">
                <BookOpen className="h-3.5 w-3.5 text-primary" />
                调研结果概要 {researchData.from_cache ? "（已复用）" : ""}：
              </div>
              <p className="text-xs text-muted-foreground">
                检索 Provider：{researchData.provider || "未配置"} · 状态：{researchData.status === "completed" ? "已完成" : researchData.status === "pending" ? "进行中" : "未完成"}
              </p>
              {researchData.queries.length > 0 && (
                <p className="text-xs text-muted-foreground">查询词：{researchData.queries.join(" / ")}</p>
              )}
              <p className="text-muted-foreground leading-relaxed">{researchData.summary}</p>
              {researchData.error_message && (
                <p className="text-warning">{researchData.error_message}</p>
              )}
              {researchData.warnings && researchData.warnings.length > 0 && (
                <div className="space-y-0.5 text-warning">
                  {researchData.warnings.map((warning, index) => (
                    <p key={`${warning}-${index}`}>提示：{warning}</p>
                  ))}
                </div>
              )}
              {researchData.sources.length > 0 && (
                <div className="pt-1 border-t border-border/50 space-y-1">
                  {researchData.sources.map((source) => (
                    <div key={source.url} className="space-y-0.5">
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noreferrer"
                        className="block truncate text-primary hover:underline"
                      >
                        {source.title}
                      </a>
                      {source.snippet && (
                        <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">
                          {source.snippet}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <Button
            type="button"
            disabled={generateScriptMutation.isPending || researchPending || isRunning || !aiTopic.trim()}
            onClick={() =>
              generateScriptMutation.mutate({
                topic: aiTopic,
                research_context: researchContextForScript(researchData),
                enable_research: !researchData,
                genre: aiGenre,
                hook_type: aiHookType,
                style_preset: aiStylePreset,
                target_scene_count: aiSceneCount,
                knowledge_brief: task?.input_payload?.knowledge_brief as KnowledgeBrief | undefined,
                research_sources: researchData?.sources || taskResearch?.sources || [],
              })
            }
            className="w-full gap-1.5"
          >
            {generateScriptMutation.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                正在生成结构化脚本…
              </>
            ) : (
              <>
                <Sparkles className="h-3.5 w-3.5" />
                {researchPending ? "等待联网搜索完成…" : "生成结构化分镜脚本"}
              </>
            )}
          </Button>

          {/* Generated Structured Script Preview */}
          {generatedScript && (
            <div className="p-3.5 bg-secondary/30 rounded-lg border border-border space-y-3 text-xs">
              <div>
                <span className="text-xs font-semibold text-muted-foreground">推荐标题</span>
                <h4 className="text-xs font-semibold text-foreground mt-0.5">{generatedScript.title}</h4>
              </div>
              <div>
                <span className="text-xs font-semibold text-muted-foreground">黄金吸睛钩子</span>
                <p className="text-muted-foreground mt-0.5">{generatedScript.hook}</p>
              </div>

              {generatedScript.knowledge_brief && (
                <div className="space-y-1.5 pt-2 border-t border-border/40">
                  <span className="text-xs font-semibold text-muted-foreground">知识 Brief</span>
                  <p className="text-muted-foreground">
                    面向：{generatedScript.knowledge_brief.audience || "未指定"}
                  </p>
                  <p className="text-foreground">
                    主张：{generatedScript.knowledge_brief.thesis || "将由脚本整理"}
                  </p>
                  <p className="text-muted-foreground">
                    带走：{generatedScript.knowledge_brief.viewer_takeaway || "将由脚本整理"}
                  </p>
                  {generatedScript.knowledge_brief.source_refs?.length > 0 && (
                    <p className="font-mono text-[11px] text-primary">
                      来源：{generatedScript.knowledge_brief.source_refs.join(", ")}
                    </p>
                  )}
                </div>
              )}

              {generatedScript.metadata && (
                <div className="space-y-1.5 pt-2 border-t border-border/40">
                  <span className="text-xs font-semibold text-muted-foreground">平台发布信息</span>
                  <p className="text-muted-foreground leading-relaxed">
                    {generatedScript.metadata.description || "未生成发布描述，将使用钩子文案兜底。"}
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {(generatedScript.metadata.tags || []).map((tag) => (
                      <Badge key={tag} variant="outline">
                        #{tag}
                      </Badge>
                    ))}
                  </div>
                  {generatedScript.metadata.declaration && (
                    <p className="text-xs text-muted-foreground">
                      内容声明：{generatedScript.metadata.declaration}
                    </p>
                  )}
                </div>
              )}

              <div className="space-y-1.5 pt-2 border-t border-border/40">
                <span className="text-xs font-semibold text-muted-foreground">
                  分镜序列（{generatedScript.scenes.length} 个）
                </span>
                {generatedScript.scenes.map((sc, i) => (
                    <div key={i} className="p-2 bg-background rounded border border-border/60 space-y-1">
                      <div className="flex justify-between font-medium">
                        <span>
                          #{i + 1} {sc.badge_text || "分镜"}
                          {sc.visual_role && (
                            <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 py-0">
                              {VISUAL_ROLE_OPTIONS.find((role) => role.value === sc.visual_role)?.label || sc.visual_role}
                            </Badge>
                          )}
                        </span>
                      </div>
                      <p className="text-foreground">{sc.narration_text}</p>
                      {(sc.claim_refs?.length || sc.source_refs?.length) ? (
                        <p className="font-mono text-[11px] text-primary">
                          {[...(sc.claim_refs || []).map((ref) => `主张:${ref}`), ...(sc.source_refs || []).map((ref) => `来源:${ref}`)].join(" · ")}
                        </p>
                      ) : null}
                    {usesVisualPrompt && sc.visual_prompt && (
                      <p className="text-xs font-mono text-muted-foreground">{sc.visual_prompt}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setIsAIOpen(false)}>
            取消
          </Button>
          {generatedScript && (
            <Button
              type="button"
              disabled={applyScriptMutation.isPending}
              onClick={() => {
                setIsApplyScriptConfirmOpen(true)
              }}
              className="gap-1.5"
            >
              <Check className="h-3.5 w-3.5" />
              {applyScriptMutation.isPending ? "应用中..." : "一键应用到故事板"}
            </Button>
          )}
        </DialogFooter>
      </Dialog>

      {/* Template switch / rerender dialog */}
      <Dialog open={isRerenderOpen} onClose={() => setIsRerenderOpen(false)} className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-base sm:text-lg font-semibold">更换模板重新渲染</DialogTitle>
          <DialogDescription>保留现有旁白配音与分镜素材，仅重新合成排版与字幕。</DialogDescription>
        </DialogHeader>
        <div className="space-y-3.5 py-2">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label htmlFor="rerender-template" className="text-xs font-semibold">目标模板</label>
              <span className="text-xs font-mono text-muted-foreground px-2 py-0.5 rounded-md glass-pill border border-border/60">
                {projectAspect} 画幅 · {taskContentModeLabel}
              </span>
            </div>
            {availableTemplates.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border/80 p-4 text-center text-xs text-muted-foreground glass-pill">
                当前画幅与画面来源下暂无可适配的排版模板
              </div>
            ) : (
              <Select
                id="rerender-template"
                value={rerenderTemplateId}
                onChange={(e) => {
                  const next = e.target.value;
                  setRerenderTemplateId(next);
                  const item = availableTemplates.find((candidate) => candidate.id === next) || templates.find((candidate) => candidate.id === next);
                  setRerenderParams(item?.default_params || {});
                }}
              >
                {availableTemplates.map((item) => (
                  <option key={item.id} value={item.id}>
                    {formatTemplateName(item.id, item.name)}
                  </option>
                ))}
              </Select>
            )}

            {/* Target Template Live Preview Card */}
            {(() => {
              const currentRerenderTpl =
                availableTemplates.find((t) => t.id === rerenderTemplateId) ||
                templates.find((t) => t.id === rerenderTemplateId);
              if (!currentRerenderTpl) return null;
              const thumbAspect =
                projectAspect === "16:9"
                  ? "aspect-[16/9] w-28"
                  : projectAspect === "1:1"
                  ? "aspect-square w-20"
                  : "aspect-[9/16] w-16";
              return (
                <div className="flex items-center gap-3 rounded-xl glass-pill p-3 border border-border/70 shadow-xs">
                  <div className={`${thumbAspect} shrink-0 overflow-hidden rounded-lg border border-border/80 bg-black`}>
                    <img
                      src={`/api/v1/templates/previews/${encodeURIComponent(currentRerenderTpl.id)}`}
                      alt={`${formatTemplateName(currentRerenderTpl.id, currentRerenderTpl.name)} 预览`}
                      className="h-full w-full object-cover"
                    />
                  </div>
                  <div className="flex-1 min-w-0 space-y-1 text-xs">
                    <div className="font-semibold text-foreground truncate">
                      {formatTemplateName(currentRerenderTpl.id, currentRerenderTpl.name)}
                    </div>
                    <div className="text-xs font-mono text-muted-foreground">
                      规格: {currentRerenderTpl.width}×{currentRerenderTpl.height} · {currentRerenderTpl.aspect_ratio || "9:16"}
                    </div>
                    <div className="text-xs text-muted-foreground line-clamp-1">
                      适配画面来源：{taskContentModeLabel}
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
          {(availableTemplates.find((item) => item.id === rerenderTemplateId) || templates.find((item) => item.id === rerenderTemplateId))?.parameter_schema.map((parameter) => (
            <div key={parameter.name} className="space-y-1.5">
              <label htmlFor={`rerender-param-${parameter.name}`} className="text-xs text-muted-foreground">
                {formatParamLabel(parameter.name, parameter.label)}
              </label>
              <Input
                id={`rerender-param-${parameter.name}`}
                value={String(rerenderParams[parameter.name] ?? parameter.default ?? "")}
                onChange={(e) => setRerenderParams((current) => ({ ...current, [parameter.name]: e.target.value }))}
                className="h-8 text-xs"
              />
            </div>
          ))}
          <div className="space-y-2 border-t border-border/50 pt-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold">重新渲染时的背景音乐</span>
              <label htmlFor="rerender-bgm-enabled" className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <input
                  id="rerender-bgm-enabled"
                  type="checkbox"
                  checked={rerenderBgmEnabled}
                  onChange={(e) => setRerenderBgmEnabled(e.target.checked)}
                  className="rounded border-border text-primary focus:ring-primary"
                />
                启用
              </label>
            </div>
            <Select
              id="rerender-bgm"
              value={rerenderBgmAssetId}
              onChange={(e) => setRerenderBgmAssetId(e.target.value)}
              disabled={!rerenderBgmEnabled}
            >
              <option value="">使用项目默认背景音乐</option>
              {projectBgm.map((asset) => (
                <option key={asset.id} value={asset.id}>{asset.file_name}</option>
              ))}
            </Select>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>音量</span>
              <label htmlFor="rerender-bgm-volume" className="sr-only">背景音乐音量</label>
              <input
                id="rerender-bgm-volume"
                type="range"
                min="0"
                max="0.5"
                step="0.01"
                value={rerenderBgmVolume}
                onChange={(e) => setRerenderBgmVolume(Number(e.target.value))}
                disabled={!rerenderBgmEnabled}
                className="flex-1"
              />
              <span className="font-mono w-8 text-right">{rerenderBgmVolume.toFixed(2)}</span>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setIsRerenderOpen(false)}>取消</Button>
          <Button type="button" onClick={() => rerenderMutation.mutate()} disabled={rerenderMutation.isPending || !rerenderTemplateId || availableTemplates.length === 0}>
            {rerenderMutation.isPending ? "提交中..." : "确认重新渲染"}
          </Button>
        </DialogFooter>
      </Dialog>

      {/* Douyin Publishing Dialog */}
      <Dialog open={isPublishOpen} onClose={() => setIsPublishOpen(false)} className="max-w-xl max-h-[88vh]">
        <DialogHeader>
          <DialogTitle>发布到抖音</DialogTitle>
          <DialogDescription>
            设置成片标题、话题标签与发布排期。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className={`rounded-xl border px-3.5 py-2.5 text-sm ${
            publishingAccounts.length > 0
              ? "border-success/30 bg-success-soft"
              : "border-warning/40 bg-warning-soft"
          }`}>
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium text-foreground">
                {publishingAccounts.length > 0 ? "抖音账号已连接" : "尚未绑定抖音账号"}
              </span>
              <Link href="/settings" className="text-primary hover:underline text-xs sm:text-sm font-medium">
                {publishingAccounts.length > 0 ? "管理账号" : "前往扫码绑定"}
              </Link>
            </div>
            {publishingAccounts.length === 0 && (
              <p className="mt-1 text-xs text-muted-foreground">请先在设置中心完成 QR 扫码授权，发布时会使用托管的 Cookie。</p>
            )}
          </div>

          {publishingAccounts.length > 0 && (
            <div className="space-y-1.5">
              <label htmlFor="publish-account" className="text-sm font-medium text-foreground">发布账号</label>
              <Select
                id="publish-account"
                aria-label="发布账号"
                value={publishAccountId}
                onChange={(event) => setPublishAccountId(event.target.value)}
              >
                {publishingAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.account_name}{account.username ? ` · ${account.username}` : ""}（{account.status === "active" ? "已连接" : "待检测"}）
                  </option>
                ))}
              </Select>
            </div>
          )}

          <div className="space-y-1.5">
            <label htmlFor="publish-cover" className="text-sm font-medium text-foreground">视频封面（可选）</label>
            <Select
              id="publish-cover"
              aria-label="视频封面"
              value={publishCoverAssetId}
              onChange={(event) => setPublishCoverAssetId(event.target.value)}
            >
              <option value="">使用平台默认封面</option>
              {coverAssets.map((asset) => (
                <option key={asset.id} value={asset.id}>{asset.file_name}</option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="publish-mode" className="text-sm font-medium text-foreground">发布方式</label>
            <Select
              id="publish-mode"
              value={publishMode}
              onChange={(e) => setPublishMode(e.target.value as "now" | "schedule")}
            >
              <option value="now">立即发布（加入队列）</option>
              <option value="schedule">定时发布（按本地时区）</option>
            </Select>
          </div>

          {publishMode === "schedule" && (
            <div className="space-y-1.5">
              <label htmlFor="publish-scheduled-at" className="text-sm font-medium text-foreground">计划发布时间</label>
              <Input
                id="publish-scheduled-at"
                type="datetime-local"
                value={scheduledAt}
                min={new Date(Date.now() + 60_000).toISOString().slice(0, 16)}
                onChange={(e) => setScheduledAt(e.target.value)}
              />
            </div>
          )}

          <div className="space-y-1.5">
            <label htmlFor="publish-title" className="text-sm font-medium text-foreground">视频标题</label>
            <Input
              id="publish-title"
              value={pubTitle}
              onChange={(e) => setPubTitle(e.target.value)}
              placeholder="请输入抖音视频标题"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="publish-description" className="text-xs font-semibold text-foreground">视频文案与话题描述</label>
            <Textarea
              id="publish-description"
              rows={3}
              value={pubDesc}
              onChange={(e) => setPubDesc(e.target.value)}
              placeholder="添加吸睛文案与话题..."
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="publish-tags" className="text-xs font-semibold text-foreground">话题标签（用逗号或空格分隔，最多5个）</label>
            <Input
              id="publish-tags"
              value={pubTags}
              onChange={(e) => setPubTags(e.target.value)}
              placeholder="例如：Trendlume, 量子力学, 科技前沿, 科普"
            />
          </div>

        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setIsPublishOpen(false)}>
            取消
          </Button>
          <Button
            type="button"
            disabled={publishMutation.isPending || scheduleMutation.isPending || !publishAccountId || !pubTitle.trim() || (publishMode === "schedule" && !scheduledAt)}
            onClick={() => {
              const tagsArray = pubTags
                .split(/[,，\s]+/)
                .map((t) => t.trim())
                .filter(Boolean)
                .slice(0, 5);
              if (publishMode === "schedule") {
                scheduleMutation.mutate({
                  account_id: publishAccountId,
                  cover_asset_id: publishCoverAssetId || null,
                  title: pubTitle,
                  description: pubDesc,
                  tags: tagsArray,
                  scheduled_at: new Date(scheduledAt).toISOString(),
                });
              } else {
                publishMutation.mutate({
                  account_id: publishAccountId,
                  cover_asset_id: publishCoverAssetId || null,
                  title: pubTitle,
                  description: pubDesc,
                  tags: tagsArray,
                });
              }
            }}
            className="gap-1.5"
          >
            {publishMutation.isPending || scheduleMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Send className="h-3.5 w-3.5" />
            )}
            {publishMode === "schedule" ? "确认定时发布" : "立即提交发布"}
          </Button>
        </DialogFooter>
      </Dialog>

      {/* Missing Configuration Action Modal Dialog */}
      <Dialog
        open={!!missingConfigAlert}
        onOpenChange={(open: boolean) => !open && setMissingConfigAlert(null)}
      >
        <DialogHeader>
          <DialogTitle className="text-sm font-semibold flex items-center gap-2 text-destructive">
            <AlertCircle className="h-4 w-4 text-destructive" />
            AI Provider 凭据缺失或未就绪
          </DialogTitle>
          <DialogDescription className="text-xs">
            执行此项创作需要先在本地配置对应的 Provider 凭据。
          </DialogDescription>
        </DialogHeader>

        <div className="py-3">
          <div className="bg-destructive-soft border border-destructive/20 rounded p-3 text-xs text-foreground leading-relaxed whitespace-pre-wrap">
            {missingConfigAlert}
          </div>
        </div>

        <DialogFooter className="flex justify-between sm:justify-between items-center w-full">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setMissingConfigAlert(null)}
          >
            关闭
          </Button>
          <Link href="/settings">
            <Button size="sm" className="gap-1.5 bg-primary">
              <Key className="h-3.5 w-3.5" />
              前往【设置中心】配置
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </Link>
        </DialogFooter>
      </Dialog>

      <ConfirmDialog
        open={isCancelConfirmOpen}
        onOpenChange={setIsCancelConfirmOpen}
        title="取消当前生成？"
        description="当前任务将停止继续生成，已经完成的素材会保留。"
        confirmLabel="确认取消"
        variant="destructive"
        onConfirm={async () => {
          await cancelWorkflowMutation.mutateAsync();
        }}
      />
      <ConfirmDialog
        open={Boolean(sceneToDelete)}
        onOpenChange={(open) => {
          if (!open) setSceneToDelete(null);
        }}
        title="删除分镜？"
        description={sceneToDelete ? `“${sceneToDelete.label}”的台词、${isSourceMaterialMode(taskContentMode) ? "来源素材匹配" : taskContentMode === "uploaded_asset" ? "我的素材绑定" : taskContentMode === "static" ? "文字排版内容" : "画面提示词"}和排序将从当前故事板中移除。` : undefined}
        confirmLabel="确认删除"
        variant="destructive"
        onConfirm={async () => {
          if (sceneToDelete) {
            handleDeleteScene(sceneToDelete.index);
            setSceneToDelete(null);
          }
        }}
      />
      <ConfirmDialog
        open={isApplyScriptConfirmOpen}
        onOpenChange={setIsApplyScriptConfirmOpen}
        title="应用新脚本？"
        description={isSourceMaterialMode(taskContentMode) ? "当前故事板中的旁白台词会被新脚本替换，并重新匹配来源素材。" : taskContentMode === "uploaded_asset" ? "当前故事板中的旁白台词会被新脚本替换，保留我的素材绑定。" : taskContentMode === "static" ? "当前故事板中的旁白台词会被新脚本替换，保留文字排版。" : "当前故事板中的旁白和画面提示词会被新脚本替换。"}
        confirmLabel="确认应用"
        onConfirm={async () => {
          if (generatedScript) await applyScriptMutation.mutateAsync(generatedScript);
        }}
      />

      {/* Interactive SMS / 2FA Verification Modal */}
      <VerificationModal />
    </PageContainer>
  );
}
