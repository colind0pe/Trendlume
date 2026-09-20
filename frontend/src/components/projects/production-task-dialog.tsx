"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Wand2,
  Volume2,
  Palette,
  Music,
  ChevronDown,
  ChevronUp,
  Settings2,
  Film,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import { KnowledgeTaskForm } from "@/components/projects/knowledge-task-form";
import { CommerceTaskForm } from "@/components/projects/commerce-task-form";
import {
  HOOK_OPTIONS,
  SCENE_COUNT_MIN,
  SCENE_COUNT_PRESETS,
  STYLE_PRESET_OPTIONS,
  ASSET_TYPE_LABELS,
  CONTENT_MODE_GROUPS,
  CONTENT_MODE_LABELS,
  CONTENT_MODE_SPECS,
  formatTemplateName,
  SPEED_PRESETS,
} from "@/lib/ui-constants";
import {
  Asset,
  ContentMode,
  CreativeAngle,
  CreativePlan,
  Project,
  Product,
  SocialAccount,
  TemplateCatalogItem,
  VoiceInfo,
} from "@/lib/types";
import { buildGenerationOptions } from "@/lib/task-generation-state";

interface ComfyUIWorkflowItem {
  id: string;
  name: string;
  type: string;
  workflow_type?: string;
}

export interface ProductionTaskDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  project: Project;
  templates: TemplateCatalogItem[];
  assets: Asset[];
  projectBgm: Asset[];
  workflows: ComfyUIWorkflowItem[];
  publishableAccounts: SocialAccount[];
  taskVoices: VoiceInfo[];
  isVoicesLoading: boolean;
  isVoicesError: boolean;
  refetchVoices: () => void;
  canonicalTemplateId: (id?: string | null) => string;
}

const assetFileUrl = (filePath: string) =>
  `/api/v1/assets/files/${filePath.split("/").map(encodeURIComponent).join("/")}`;

export function ProductionTaskDialog({
  open,
  onOpenChange,
  projectId,
  project,
  templates,
  assets,
  projectBgm,
  workflows,
  publishableAccounts,
  taskVoices,
  isVoicesLoading,
  isVoicesError,
  refetchVoices,
  canonicalTemplateId,
}: ProductionTaskDialogProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  // Mode: AI generation vs Fixed raw text
  const [creationMode, setCreationMode] = React.useState<"generate" | "fixed">("generate");
  const [taskTitle, setTaskTitle] = React.useState("");
  const [rawScript, setRawScript] = React.useState("");
  const [splitMode, setSplitMode] = React.useState<"paragraph" | "line" | "sentence">("paragraph");

  // Creative direction (AI mode)
  const [taskGenre, setTaskGenre] = React.useState("auto");
  const [taskHookType, setTaskHookType] = React.useState("auto");
  const [targetSceneCount, setTargetSceneCount] = React.useState(SCENE_COUNT_MIN);
  const [enableResearch, setEnableResearch] = React.useState(true);
  const [knowledgeAudience, setKnowledgeAudience] = React.useState("");
  const [knowledgeThesis, setKnowledgeThesis] = React.useState("");
  const [knowledgeViewerTakeaway, setKnowledgeViewerTakeaway] = React.useState("");
  const [productId, setProductId] = React.useState("");
  const [creativePlanId, setCreativePlanId] = React.useState("");
  const [creativeAngle, setCreativeAngle] = React.useState<CreativeAngle>("direct");

  // Visual style
  const [taskStylePreset, setTaskStylePreset] = React.useState("stick_figure");
  const [customPromptPrefix, setCustomPromptPrefix] = React.useState("");

  // Content mode & template
  const [contentMode, setContentMode] = React.useState<ContentMode>("generated_image");
  const [selectedTemplateId, setSelectedTemplateId] = React.useState("");
  const [templateParams, setTemplateParams] = React.useState<Record<string, any>>({});
  const [sourceAssetId, setSourceAssetId] = React.useState("");

  const projectAspect = project?.aspect_ratio || "9:16";
  const productionMode = project.primary_production_mode;
  const isCommerce = productionMode === "commerce";

  const { data: products = [], isLoading: productsLoading } = useQuery<Product[]>({
    queryKey: ["products"],
    queryFn: () => api.listProducts(),
    enabled: open && isCommerce,
  });
  const selectedProduct = products.find((product) => product.id === productId);
  const { data: creativePlans = [], isLoading: creativePlansLoading } = useQuery<CreativePlan[]>({
    queryKey: ["creative-plans", productId],
    queryFn: () => api.listCreativePlans(productId),
    enabled: open && isCommerce && Boolean(productId),
  });
  const selectedCreativePlan = creativePlans.find((plan) => plan.id === creativePlanId);

  // Filter templates strictly matching project's aspect ratio and current content mode
  const availableTemplates = React.useMemo(() => {
    return templates.filter((item) => {
      const matchesAspect =
        item.aspect_ratio === projectAspect ||
        (!item.aspect_ratio && projectAspect === "9:16");
      const matchesMode = item.supported_content_modes.includes(contentMode);
      return matchesAspect && matchesMode;
    });
  }, [templates, projectAspect, contentMode]);

  // Audio settings
  const [taskVoiceId, setTaskVoiceId] = React.useState("");
  const [taskSpeed, setTaskSpeed] = React.useState(1.0);
  const [bgmAssetId, setBgmAssetId] = React.useState("");
  const [bgmEnabled, setBgmEnabled] = React.useState(true);
  const [bgmVolume, setBgmVolume] = React.useState(0.2);

  // Advanced: Workflows & Automated publishing
  const [showAdvanced, setShowAdvanced] = React.useState(false);
  const [imageWorkflowId, setImageWorkflowId] = React.useState("");
  const [videoWorkflowId, setVideoWorkflowId] = React.useState("");
  const [autoSchedulePublish, setAutoSchedulePublish] = React.useState(false);
  const [scheduleAccountId, setScheduleAccountId] = React.useState("");
  const [scheduleAt, setScheduleAt] = React.useState("");

  // Sync default BGM from project when available
  React.useEffect(() => {
    if (project?.bgm_asset_id) {
      setBgmAssetId(project.bgm_asset_id);
    }
  }, [project]);

  // Keep selected template synchronized with project settings and available templates
  React.useEffect(() => {
    if (!open) return;

    if (availableTemplates.length === 0) {
      if (selectedTemplateId !== "") {
        setSelectedTemplateId("");
        setTemplateParams({});
      }
      return;
    }

    // Check if current selection is already valid in availableTemplates
    const isCurrentValid = availableTemplates.some((t) => t.id === selectedTemplateId);
    if (isCurrentValid) {
      return;
    }

    // Try project's default template if it is in availableTemplates
    const projectTplId = project?.template?.template_id
      ? canonicalTemplateId(project.template.template_id)
      : "";
    const matchedProjectTpl = availableTemplates.find((t) => t.id === projectTplId);

    if (matchedProjectTpl) {
      setSelectedTemplateId(matchedProjectTpl.id);
      setTemplateParams(project.template?.params || matchedProjectTpl.default_params || {});
    } else {
      setSelectedTemplateId(availableTemplates[0].id);
      setTemplateParams(availableTemplates[0].default_params || {});
    }
  }, [open, availableTemplates, selectedTemplateId, project, canonicalTemplateId]);

  React.useEffect(() => {
    if (!open || !isCommerce) return;
    if (!productId && products.length > 0) setProductId(products[0].id);
  }, [open, isCommerce, productId, products]);

  React.useEffect(() => {
    if (!isCommerce || !productId) {
      setCreativePlanId("");
      return;
    }
    if (creativePlans.length === 0) {
      setCreativePlanId("");
      return;
    }
    if (!creativePlans.some((plan) => plan.id === creativePlanId && plan.status !== "archived")) {
      setCreativePlanId(
        creativePlans.find((plan) => plan.status === "selected")?.id ||
        creativePlans.find((plan) => plan.status !== "archived")?.id ||
        "",
      );
    }
  }, [creativePlans, creativePlanId, isCommerce, productId]);

  // Creation mutation
  const createTaskMutation = useMutation({
    mutationFn: async () => {
      const finalTitle =
        taskTitle.trim() ||
        (isCommerce
          ? selectedProduct?.title || "未命名商品视频任务"
          : creationMode === "fixed" ? rawScript.slice(0, 20) : "未命名短视频任务");

      if (isCommerce && !productId) {
        throw new Error("请先选择商品事实卡。 ");
      }
      if (isCommerce && !creativePlanId) {
        throw new Error("请先在商品库生成并选择一个 Creative Plan。");
      }

      if (autoSchedulePublish && (!scheduleAccountId || !scheduleAt)) {
        throw new Error("请先选择发布账号和计划发布时间。");
      }

      const scheduledPublish = autoSchedulePublish
        ? {
            account_id: scheduleAccountId,
            scheduled_at: new Date(scheduleAt).toISOString(),
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
          }
        : null;

      const generationOptions = buildGenerationOptions({
        targetSceneCount,
        enableResearch,
        contentMode,
        templateId: selectedTemplateId,
        genre: taskGenre,
        hookType: taskHookType,
        stylePreset: taskStylePreset,
        promptPrefix: customPromptPrefix,
        voiceId: taskVoiceId,
        speed: taskSpeed,
        bgmEnabled,
        bgmAssetId,
        bgmVolume,
        sourceAssetId,
      });

      return api.createProjectTask(projectId, {
        title: finalTitle,
        description:
          isCommerce
            ? `商品视频：${selectedProduct?.title || finalTitle} · Creative Plan：${selectedCreativePlan?.variant_label || creativeAngle}`
            : creationMode === "fixed"
            ? rawScript.slice(0, 200)
            : `知识主题: ${finalTitle}, 面向: ${knowledgeAudience.trim() || "普通观众"}`,
        job_type: "video_composition",
        product_id: isCommerce ? productId : undefined,
        creative_plan_id: isCommerce ? creativePlanId : undefined,
        creative_angle: isCommerce ? creativeAngle : undefined,
        ...(!isCommerce ? {
          knowledge_brief: {
            audience: knowledgeAudience.trim(),
            thesis: knowledgeThesis.trim(),
            viewer_takeaway: knowledgeViewerTakeaway.trim(),
            key_claims: [],
            source_refs: [],
            genre: taskGenre,
          },
        } : {}),
        input_payload: {
          mode: creationMode,
          topic: finalTitle,
          raw_script: rawScript,
          split_mode: splitMode,
          ...(!isCommerce ? {
            knowledge_brief: {
              audience: knowledgeAudience.trim(),
              thesis: knowledgeThesis.trim(),
              viewer_takeaway: knowledgeViewerTakeaway.trim(),
              key_claims: [],
              source_refs: [],
              genre: taskGenre,
            },
          } : {}),
          ...generationOptions,
          template_params: templateParams,
          scheduled_publish: scheduledPublish,
          image_workflow_id: imageWorkflowId || null,
          video_workflow_id: videoWorkflowId || null,
        },
        template_id: selectedTemplateId,
        bgm_asset_id: bgmEnabled ? bgmAssetId || null : null,
        bgm_enabled: bgmEnabled,
        bgm_volume: bgmVolume,
        voice_id: taskVoiceId,
        speed: taskSpeed,
        content_mode: contentMode,
        template_params: templateParams,
        source_asset_id: contentMode === "uploaded_asset" ? sourceAssetId || null : null,
        enable_research: enableResearch,
        image_workflow_id: imageWorkflowId || null,
        video_workflow_id: videoWorkflowId || null,
        target_scene_count: targetSceneCount,
        scheduled_publish: scheduledPublish,
      });
    },
    onSuccess: (newTask) => {
      queryClient.invalidateQueries({ queryKey: ["project-tasks", projectId] });
      toast(`${isCommerce ? "商品视频" : "知识视频"}任务创建成功！正在进入工作台…`, "success");
      onOpenChange(false);
      // Reset main inputs
      setTaskTitle("");
      setRawScript("");
      setSourceAssetId("");
      setTargetSceneCount(SCENE_COUNT_MIN);
      setAutoSchedulePublish(false);
      setScheduleAccountId("");
      setScheduleAt("");
      setKnowledgeAudience("");
      setKnowledgeThesis("");
      setKnowledgeViewerTakeaway("");
      setProductId("");
      setCreativePlanId("");
      setCreativeAngle("direct");
      router.push(`/projects/${projectId}/tasks/${newTask.id}`);
    },
    onError: (error: any) => {
      toast(`创建任务失败：${error?.message || "请稍后重试"}`, "error");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createTaskMutation.mutate();
  };

  const selectedVoice = taskVoices.find((v) => v.id === taskVoiceId);
  const voiceDisplayName = selectedVoice
    ? `${selectedVoice.name}`
    : taskVoiceId || "系统默认音色";

  const selectedTemplate =
    availableTemplates.find((t) => t.id === selectedTemplateId) ||
    templates.find((t) => t.id === selectedTemplateId);
  const selectedStyle = STYLE_PRESET_OPTIONS.find((s) => s.value === taskStylePreset);
  const contentModeSpec = CONTENT_MODE_SPECS[contentMode];
  const usesAiVisualStyle = contentModeSpec.usesVisualPrompt;

  const isFormValid =
    (isCommerce
      ? Boolean(productId) && Boolean(creativePlanId)
      : (creationMode === "generate" ? Boolean(taskTitle.trim()) : Boolean(rawScript.trim()))) &&
    (!contentModeSpec.requiresSourceAsset || Boolean(sourceAssetId)) &&
    (!autoSchedulePublish || (Boolean(scheduleAccountId) && Boolean(scheduleAt))) &&
    Boolean(selectedTemplateId);

  return (
    <Dialog
      open={open}
      onClose={() => onOpenChange(false)}
      className="max-w-5xl xl:max-w-6xl w-full p-0 overflow-hidden sm:max-h-[90vh] flex flex-col rounded-2xl"
    >
      {/* Studio Header */}
      <div className="px-6 py-4 border-b border-border bg-card/90 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0">
            <Wand2 className="h-4.5 w-4.5" />
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h2 className="text-base font-bold text-foreground">新建 Production Task</h2>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              所属空间：《{project.name}》· {project.aspect_ratio} 画幅
            </p>
          </div>
        </div>
      </div>

      <div className="border-b border-border bg-card/60 px-5 py-4 sm:px-6">
        <div className="flex flex-wrap items-center gap-2" role="status" aria-live="polite">
          <span className="text-sm font-semibold text-foreground">Project 模式</span>
          <span className="rounded-full border border-primary/20 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
            {productionMode}
          </span>
          <span className="text-xs text-muted-foreground">
            Task 会继承此模式，创建后不能在 Task 级别切换。
          </span>
        </div>
      </div>

      {/* Studio Two-Column Body */}
      <form onSubmit={handleSubmit} className="flex-1 flex flex-col min-h-0 overflow-hidden">
        <div className="flex-1 overflow-y-auto min-h-0">
            <div className="grid grid-cols-1 lg:grid-cols-12 divide-y lg:divide-y-0 lg:divide-x divide-border">
            {/* Left Column: Creative Core (58%) */}
            <div className="lg:col-span-7 p-5 sm:p-6 space-y-5">
              {isCommerce ? (
                <CommerceTaskForm
                  products={products}
                  productsLoading={productsLoading}
                  productId={productId}
                  onProductIdChange={setProductId}
                  creativePlans={creativePlans}
                  creativePlansLoading={creativePlansLoading}
                  creativePlanId={creativePlanId}
                  onCreativePlanIdChange={setCreativePlanId}
                  creativeAngle={creativeAngle}
                  onCreativeAngleChange={setCreativeAngle}
                  taskTitle={taskTitle}
                  onTaskTitleChange={setTaskTitle}
                />
              ) : (
                <KnowledgeTaskForm
                  creationMode={creationMode}
                  onCreationModeChange={setCreationMode}
                  taskTitle={taskTitle}
                  onTaskTitleChange={setTaskTitle}
                  rawScript={rawScript}
                  onRawScriptChange={setRawScript}
                  splitMode={splitMode}
                  onSplitModeChange={setSplitMode}
                  taskGenre={taskGenre}
                  onTaskGenreChange={setTaskGenre}
                  audience={knowledgeAudience}
                  onAudienceChange={setKnowledgeAudience}
                  thesis={knowledgeThesis}
                  onThesisChange={setKnowledgeThesis}
                  viewerTakeaway={knowledgeViewerTakeaway}
                  onViewerTakeawayChange={setKnowledgeViewerTakeaway}
                  enableResearch={enableResearch}
                  onEnableResearchChange={setEnableResearch}
                />
              )}

              {/* Visual Style Preset Selection */}
              {showAdvanced && usesAiVisualStyle && (
                <div className="space-y-2.5 pt-3 border-t border-border">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-foreground flex items-center gap-2">
                      <Palette className="h-4 w-4 text-primary" />
                      <span>视觉美学风格预设</span>
                    </label>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {STYLE_PRESET_OPTIONS.map((style) => (
                      <button
                        key={style.value}
                        type="button"
                        onClick={() => setTaskStylePreset(style.value)}
                        aria-pressed={taskStylePreset === style.value}
                        className={`p-2.5 rounded-lg border text-left transition-all cursor-pointer ${
                          taskStylePreset === style.value
                            ? "border-primary bg-primary/10 text-foreground ring-1 ring-primary/80 shadow-xs"
                            : "border-border bg-card text-muted-foreground hover:bg-secondary/40 hover:text-foreground"
                        }`}
                      >
                        <div className="text-sm font-medium text-foreground leading-snug">{style.label}</div>
                        <div className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
                          {style.desc}
                        </div>
                      </button>
                    ))}
                  </div>

                  {taskStylePreset === "custom" && (
                    <div className="pt-1.5">
                      <Input
                        id="studio-custom-style"
                        placeholder="输入自定义风格提示词，例如：赛博朋克、新海诚唯美风、复古工笔画"
                        value={customPromptPrefix}
                        onChange={(e) => setCustomPromptPrefix(e.target.value)}
                        className="h-9 text-sm"
                      />
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Right Column: Spec, Voice & Settings (42%) */}
            <div className="lg:col-span-5 p-5 sm:p-6 bg-secondary/10 space-y-5 flex flex-col justify-between">
              <div className="space-y-4">
                {/* Live Spec Board */}
                <div className="rounded-xl border border-border bg-card p-4 space-y-3 shadow-xs">
                  <div className="flex items-center justify-between border-b border-border/60 pb-2">
                    <span className="font-semibold text-sm text-foreground flex items-center gap-2">
                      <Film className="h-4 w-4 text-primary" />
                      任务规格预览
                    </span>
                    <Badge variant="outline" className="font-mono text-xs px-2 py-0.5">
                      {project.aspect_ratio} 画幅
                    </Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div className="space-y-0.5">
                      <span className="text-xs text-muted-foreground">镜头规划</span>
                      <p className="font-mono font-medium text-foreground">
                        {productionMode === "knowledge"
                          ? creationMode === "generate" ? `${targetSceneCount} 镜` : "文本拆分计算"
                          : `${selectedCreativePlan?.scene_outline.length || 0} 个方案节拍`}
                      </p>
                    </div>
                    <div className="space-y-0.5">
                      <span className="text-xs text-muted-foreground">画面来源</span>
                      <p className="font-medium text-foreground">{CONTENT_MODE_LABELS[contentMode]}</p>
                    </div>
                    <div className="space-y-0.5">
                      <span className="text-xs text-muted-foreground">配音发音人</span>
                      <p className="font-medium text-foreground truncate">{voiceDisplayName}</p>
                    </div>
                    {usesAiVisualStyle && (
                      <div className="space-y-0.5">
                        <span className="text-xs text-muted-foreground">视觉风格</span>
                        <p className="font-medium text-foreground truncate">{selectedStyle?.label || "火柴人"}</p>
                      </div>
                    )}
                  </div>
                </div>

                {/* TTS Voice & Speed */}
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between">
                    <label htmlFor="studio-voice" className="text-sm font-medium text-foreground flex items-center gap-2">
                      <Volume2 className="h-4 w-4 text-primary" />
                      <span>旁白配音音色</span>
                    </label>
                    <span className="font-mono text-xs text-muted-foreground">{taskSpeed.toFixed(1)}x 语速</span>
                  </div>
                  <Select
                    id="studio-voice"
                    value={taskVoiceId}
                    onChange={(e) => setTaskVoiceId(e.target.value)}
                    className="h-9 text-sm"
                  >
                    <option value="">使用系统默认音色</option>
                    {taskVoiceId && !taskVoices.some((v) => v.id === taskVoiceId) && (
                      <option value={taskVoiceId}>{taskVoiceId}</option>
                    )}
                    {taskVoices.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name} · {v.locale}
                      </option>
                    ))}
                  </Select>
                  {isVoicesLoading && <p className="text-xs text-muted-foreground">加载发音人音色列表中…</p>}
                  {isVoicesError && (
                    <p className="text-xs text-destructive flex items-center gap-1">
                      <span>音色列表加载失败</span>
                      <button type="button" onClick={() => refetchVoices()} className="underline ml-1">重试</button>
                    </p>
                  )}

                  {/* Speed selector chips */}
                  <div className="flex items-center gap-2 pt-0.5">
                    {SPEED_PRESETS.map((spd) => (
                      <button
                        key={spd}
                        type="button"
                        onClick={() => setTaskSpeed(spd)}
                        aria-pressed={Math.abs(taskSpeed - spd) < 0.05}
                        className={`flex-1 py-1.5 rounded-md text-xs font-mono transition-colors cursor-pointer ${
                          Math.abs(taskSpeed - spd) < 0.05
                            ? "bg-primary text-primary-foreground font-semibold shadow-xs"
                            : "bg-card text-muted-foreground hover:bg-secondary hover:text-foreground border border-border"
                        }`}
                      >
                        {spd}x
                      </button>
                    ))}
                  </div>
                </div>

                {/* Visual Mode & Template */}
                {showAdvanced && <div className="space-y-2.5 pt-3 border-t border-border">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <label htmlFor="studio-content-mode" className="text-sm font-medium text-foreground">
                        画面来源
                      </label>
                      <Select
                        id="studio-content-mode"
                        value={contentMode}
                        aria-describedby="studio-content-mode-description"
                        onChange={(e) => {
                          const next = e.target.value as ContentMode;
                          setContentMode(next);
                        }}
                        className="h-9 text-sm"
                      >
                        {CONTENT_MODE_GROUPS.map((group) => (
                          <optgroup key={group.value} label={group.label}>
                            {group.modes.map((mode) => (
                              <option key={mode} value={mode}>
                                {CONTENT_MODE_SPECS[mode].label}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </Select>
                      <p id="studio-content-mode-description" className="text-xs text-muted-foreground">
                        {CONTENT_MODE_SPECS[contentMode].selectionHint}
                      </p>
                    </div>

                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label htmlFor="studio-template" className="text-sm font-medium text-foreground">
                          排版模板
                        </label>
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 border-border text-muted-foreground font-mono">
                          {projectAspect} 画幅
                        </Badge>
                      </div>
                      <Select
                        id="studio-template"
                        value={selectedTemplateId}
                        onChange={(e) => {
                          const next = e.target.value;
                          setSelectedTemplateId(next);
                          const item = availableTemplates.find((candidate) => candidate.id === next) ||
                            templates.find((candidate) => candidate.id === next);
                          setTemplateParams(item?.default_params || {});
                        }}
                        className="h-9 text-sm"
                        disabled={availableTemplates.length === 0}
                      >
                        {availableTemplates.length === 0 ? (
                          <option value="">当前画幅暂无可用模板</option>
                        ) : (
                          availableTemplates.map((item) => (
                            <option key={item.id} value={item.id}>
                              {formatTemplateName(item.id, item.name)}
                            </option>
                          ))
                        )}
                      </Select>
                    </div>
                  </div>

                  {/* Selected Template Compact Preview */}
                  {selectedTemplate && (
                    <div className="flex items-center gap-3 p-2.5 rounded-lg border border-border bg-card/60">
                      <div className={`relative shrink-0 rounded-md overflow-hidden bg-secondary/40 border border-border flex items-center justify-center ${
                        projectAspect === "16:9"
                          ? "w-20 aspect-[16/9]"
                          : projectAspect === "1:1"
                          ? "w-14 aspect-square"
                          : "w-11 aspect-[9/16]"
                      }`}>
                        <img
                          src={`/api/v1/templates/previews/${encodeURIComponent(selectedTemplate.id)}`}
                          alt={`${formatTemplateName(selectedTemplate.id, selectedTemplate.name)} 预览`}
                          className="h-full w-full object-cover"
                          onError={(e) => {
                            (e.currentTarget as HTMLElement).style.display = "none";
                          }}
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <p className="text-xs font-medium text-foreground truncate">
                            {formatTemplateName(selectedTemplate.id, selectedTemplate.name)}
                          </p>
                          <Badge variant="secondary" className="text-[10px] px-1 py-0 h-4 shrink-0 font-mono">
                            {selectedTemplate.aspect_ratio || projectAspect}
                          </Badge>
                        </div>
                        <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
                          {selectedTemplate.parameter_schema?.length
                            ? `${selectedTemplate.parameter_schema.length} 项可调参数 · 支持 ${selectedTemplate.supported_content_modes.length} 种画面来源`
                            : `支持 ${selectedTemplate.supported_content_modes.length} 种画面来源`}
                        </p>
                      </div>
                    </div>
                  )}

                  {availableTemplates.length === 0 && (
                    <p className="text-xs text-amber-500/90 dark:text-amber-400/90 bg-amber-500/10 border border-amber-500/20 rounded-md p-2">
                      当前项目画幅（{projectAspect}）下未找到匹配“{CONTENT_MODE_LABELS[contentMode]}”模式的排版模板，请切换画面来源或联系管理员添加模板。
                    </p>
                  )}

                  {/* If uploaded_asset is chosen */}
                  {contentMode === "uploaded_asset" && (
                    <div className="space-y-1.5">
                      <label htmlFor="studio-source-asset" className="text-sm font-medium text-foreground">
                        默认绑定我的素材 <span className="text-destructive">*</span>
                      </label>
                      <Select
                        id="studio-source-asset"
                        value={sourceAssetId}
                        onChange={(e) => setSourceAssetId(e.target.value)}
                        required
                        className="h-9 text-sm"
                      >
                        <option value="">请选择图片或视频素材</option>
                        {assets
                          .filter((asset) => asset.asset_type === "image" || asset.asset_type === "video")
                          .map((asset) => (
                            <option key={asset.id} value={asset.id}>
                              {asset.file_name}（{ASSET_TYPE_LABELS[asset.asset_type] || asset.asset_type}）
                            </option>
                          ))}
                      </Select>
                    </div>
                  )}
                </div>}

                {/* Background Music Section */}
                {showAdvanced && <div className="space-y-2.5 pt-3 border-t border-border">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-foreground flex items-center gap-2">
                      <Music className="h-4 w-4 text-primary" />
                      <span>背景音乐</span>
                    </label>
                    <label htmlFor="studio-bgm-toggle" className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
                      <input
                        id="studio-bgm-toggle"
                        type="checkbox"
                        checked={bgmEnabled}
                        onChange={(e) => setBgmEnabled(e.target.checked)}
                        className="rounded border-border text-primary focus:ring-primary h-4 w-4 cursor-pointer"
                      />
                      <span>启用</span>
                    </label>
                  </div>

                  {bgmEnabled && (
                    <div className="space-y-2.5 rounded-lg bg-card/80 p-3 border border-border">
                      <Select
                        id="studio-bgm-select"
                        value={bgmAssetId}
                        onChange={(e) => setBgmAssetId(e.target.value)}
                        className="h-9 text-sm"
                      >
                        <option value="">使用项目默认背景音乐</option>
                        {projectBgm.map((asset) => (
                          <option key={asset.id} value={asset.id}>
                            {asset.file_name}
                          </option>
                        ))}
                      </Select>

                      <div className="flex items-center gap-2.5 text-xs text-muted-foreground">
                        <span className="shrink-0">音量</span>
                        <input
                          type="range"
                          min="0"
                          max="0.5"
                          step="0.01"
                          value={bgmVolume}
                          onChange={(e) => setBgmVolume(Number(e.target.value))}
                          className="flex-1 h-1.5 bg-secondary rounded-lg appearance-none cursor-pointer accent-primary"
                        />
                        <span className="font-mono w-8 text-right text-foreground font-medium">
                          {bgmVolume.toFixed(2)}
                        </span>
                      </div>

                      {bgmAssetId && projectBgm.find((a) => a.id === bgmAssetId) && (
                        <audio
                          controls
                          preload="none"
                          className="h-8 w-full mt-1"
                          src={assetFileUrl(projectBgm.find((a) => a.id === bgmAssetId)!.file_path)}
                        />
                      )}
                    </div>
                  )}
                </div>}

                {/* Progressive Disclosure: Advanced Settings */}
                <div className="pt-3 border-t border-border">
                  <button
                    type="button"
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    className="w-full flex items-center justify-between py-1 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                  >
                    <div className="flex items-center gap-2">
                      <Settings2 className="h-4 w-4 text-primary" />
                      <span>高级配置与自动化</span>
                      {(Boolean(imageWorkflowId) || Boolean(videoWorkflowId) || autoSchedulePublish) && (
                        <span className="h-2 w-2 rounded-full bg-primary" />
                      )}
                    </div>
                    {showAdvanced ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </button>

                  {showAdvanced && (
                    <div className="mt-3 space-y-3 rounded-lg border border-border bg-card/80 p-3.5">
                      {/* Knowledge planning controls */}
                      {productionMode === "knowledge" && creationMode === "generate" && (
                        <div className="space-y-2.5 pb-2.5 border-b border-border/60">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-medium text-foreground">分镜规划</span>
                            <span className="font-mono text-[11px] text-primary font-medium">
                              目标 {targetSceneCount} 镜 · 约 {targetSceneCount * 4} 秒
                            </span>
                          </div>
                          <div className="grid grid-cols-5 gap-2">
                            {SCENE_COUNT_PRESETS.map((preset) => (
                              <button
                                key={preset.count}
                                type="button"
                                onClick={() => setTargetSceneCount(preset.count)}
                                aria-pressed={targetSceneCount === preset.count}
                                className={`py-2 px-1.5 rounded-lg text-center border transition-all cursor-pointer select-none ${
                                  targetSceneCount === preset.count
                                    ? "bg-primary text-primary-foreground border-primary shadow-xs font-semibold"
                                    : "bg-card text-muted-foreground border-border hover:bg-secondary hover:text-foreground"
                                }`}
                              >
                                <div className="text-xs font-bold font-mono">{preset.count} 镜</div>
                                <div className="text-[10px] opacity-80 mt-0.5">{preset.desc.split(" ")[0]}</div>
                              </button>
                            ))}
                          </div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div className="space-y-1.5">
                              <label htmlFor="studio-hook" className="text-xs text-muted-foreground">开场表达</label>
                              <Select
                                id="studio-hook"
                                value={taskHookType}
                                onChange={(event) => setTaskHookType(event.target.value)}
                                className="h-9 text-sm"
                              >
                                {HOOK_OPTIONS.map((hook) => (
                                  <option key={hook.value} value={hook.value}>{hook.label}</option>
                                ))}
                              </Select>
                            </div>
                            <div className="flex items-end text-xs leading-relaxed text-muted-foreground">
                              镜头数只影响规划目标；最终场景会根据旁白和信息量调整。
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Workflows */}
                      <div className="space-y-1.5">
                        <label htmlFor="studio-img-workflow" className="text-xs text-muted-foreground">
                          ComfyUI 图像工作流
                        </label>
                        <Select
                          id="studio-img-workflow"
                          value={imageWorkflowId}
                          onChange={(e) => setImageWorkflowId(e.target.value)}
                          disabled={contentMode !== "generated_image"}
                          className="h-9 text-sm"
                        >
                          <option value="">使用图像 Provider 默认工作流</option>
                          {workflows
                            .filter((w) => w.type === "image")
                            .map((w) => (
                              <option key={w.id} value={w.id}>
                                {w.name}
                              </option>
                            ))}
                        </Select>
                      </div>

                      <div className="space-y-1.5">
                        <label htmlFor="studio-video-workflow" className="text-xs text-muted-foreground">
                          ComfyUI 视频工作流
                        </label>
                        <Select
                          id="studio-video-workflow"
                          value={videoWorkflowId}
                          onChange={(e) => setVideoWorkflowId(e.target.value)}
                          disabled={contentMode !== "generated_video"}
                          className="h-9 text-sm"
                        >
                          <option value="">使用视频 Provider 默认工作流</option>
                          {workflows
                            .filter((w) => w.type === "video")
                            .map((w) => (
                              <option key={w.id} value={w.id}>
                                {w.name}
                              </option>
                            ))}
                        </Select>
                      </div>

                      {/* Auto-schedule publishing */}
                      <div className="space-y-2.5 pt-2.5 border-t border-border/60">
                        <label htmlFor="studio-auto-publish" className="flex items-center gap-2 text-sm font-medium text-foreground cursor-pointer">
                          <input
                            id="studio-auto-publish"
                            type="checkbox"
                            checked={autoSchedulePublish}
                            onChange={(e) => setAutoSchedulePublish(e.target.checked)}
                            className="rounded border-border text-primary focus:ring-primary h-4 w-4 cursor-pointer"
                          />
                          <span>视频渲染完成后自动发布</span>
                        </label>

                        {autoSchedulePublish && (
                          <div className="space-y-2.5 pl-6">
                            <Select
                              id="studio-schedule-account"
                              value={scheduleAccountId}
                              onChange={(e) => setScheduleAccountId(e.target.value)}
                              required={autoSchedulePublish}
                              className="h-9 text-sm"
                            >
                              <option value="">请选择授权的抖音账号</option>
                              {publishableAccounts.map((account) => (
                                <option key={account.id} value={account.id}>
                                  {account.account_name}
                                  {account.username ? ` (${account.username})` : ""}
                                </option>
                              ))}
                            </Select>
                            {publishableAccounts.length === 0 && (
                              <Link href="/publishing" className="text-xs text-primary hover:underline block">
                                暂无可用账号，前往发布中心扫码授权
                              </Link>
                            )}

                            <Input
                              id="studio-schedule-at"
                              type="datetime-local"
                              value={scheduleAt}
                              onChange={(e) => setScheduleAt(e.target.value)}
                              min={new Date(Date.now() + 60_000 - new Date().getTimezoneOffset() * 60_000)
                                .toISOString()
                                .slice(0, 16)}
                              required={autoSchedulePublish}
                              className="h-9 text-sm"
                            />
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
            </div>
          </div>
        {/* Studio Dialog Footer */}
        <div className="px-6 py-3.5 border-t border-border bg-card/90 flex items-center justify-end gap-3 shrink-0">
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={createTaskMutation.isPending}
            className="h-9 text-sm px-4"
          >
            取消
          </Button>
          <Button
            type="submit"
            disabled={createTaskMutation.isPending || !isFormValid}
            className="h-9 text-sm px-5 gap-2 font-medium"
          >
            <Wand2 className="h-4 w-4" />
            <span>{createTaskMutation.isPending ? "正在创建任务…" : "创建并进入工作台"}</span>
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
