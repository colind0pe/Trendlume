"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Wand2,
  Volume2,
  Palette,
  Music,
  ChevronDown,
  Settings2,
  Film,
  Users,
  MapPin,
  Package,
  Check,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { api } from "@/lib/api-client";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import { KnowledgeTaskForm } from "@/components/projects/knowledge-task-form";
import { CommerceTaskForm } from "@/components/projects/commerce-task-form";
import {
  PRODUCTION_MODE_SPECS,
  SCENE_COUNT_MIN,
  SCENE_COUNT_PRESETS,
  STYLE_PRESET_OPTIONS,
  ASSET_TYPE_LABELS,
  CONTENT_MODE_GROUPS,
  CONTENT_MODE_LABELS,
  CONTENT_MODE_SPECS,
  formatTemplateName,
  isContentMode,
  SPEED_PRESETS,
} from "@/lib/ui-constants";
import {
  Asset,
  ContentMode,
  CreativeAngle,
  Project,
  ProductionRecipe,
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
  taskVoices: VoiceInfo[];
  isVoicesLoading: boolean;
  isVoicesError: boolean;
  refetchVoices: () => void;
  canonicalTemplateId: (id?: string | null) => string;
}

const assetFileUrl = (filePath: string) =>
  `/api/v1/assets/files/${filePath.split("/").map(encodeURIComponent).join("/")}`;

function DramaResourcePicker({
  icon: Icon,
  label,
  items,
  selected,
  onChange,
}: {
  icon: LucideIcon;
  label: string;
  items: Array<{ id: string; name: string; approval_status: string }>;
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const approvedItems = items.filter((item) => item.approval_status === "approved");
  return (
    <fieldset className="space-y-2">
      <legend className="flex items-center gap-2 text-sm font-medium">
        <Icon aria-hidden="true" className="h-4 w-4 text-primary" />
        {label}
      </legend>
      {approvedItems.length === 0 ? (
        <p className="text-xs text-muted-foreground">暂无可用的已审批资源。</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {approvedItems.map((item) => {
            const checked = selected.includes(item.id);
            return (
              <button
                key={item.id}
                type="button"
                aria-pressed={checked}
                onClick={() => onChange(checked ? selected.filter((id) => id !== item.id) : [...selected, item.id])}
                className={`min-h-11 rounded-full border px-3 text-sm transition-colors ${checked ? "border-primary bg-primary/10 text-primary" : "border-border bg-card text-muted-foreground hover:text-foreground"}`}
              >
                {item.name}
              </button>
            );
          })}
        </div>
      )}
    </fieldset>
  );
}

export function ProductionTaskDialog({
  open,
  onOpenChange,
  projectId,
  project,
  templates,
  assets,
  projectBgm,
  workflows,
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
  const [creativeAngle, setCreativeAngle] = React.useState<CreativeAngle>("direct");
  const [episodeNumber, setEpisodeNumber] = React.useState(1);
  const [episodeSynopsis, setEpisodeSynopsis] = React.useState("");
  const [episodeConflict, setEpisodeConflict] = React.useState("");
  const [episodeHook, setEpisodeHook] = React.useState("");
  const [selectedCharacterIds, setSelectedCharacterIds] = React.useState<string[]>([]);
  const [selectedLocationIds, setSelectedLocationIds] = React.useState<string[]>([]);
  const [selectedPropIds, setSelectedPropIds] = React.useState<string[]>([]);
  const [showDramaAdditional, setShowDramaAdditional] = React.useState(false);

  // Visual style
  const [taskStylePreset, setTaskStylePreset] = React.useState("stick_figure");
  const [customPromptPrefix, setCustomPromptPrefix] = React.useState("");

  // Content mode & template
  const [contentMode, setContentMode] = React.useState<ContentMode>("generated_image");
  const [selectedTemplateId, setSelectedTemplateId] = React.useState("");
  const [templateParams, setTemplateParams] = React.useState<Record<string, any>>({});
  const [sourceAssetId, setSourceAssetId] = React.useState("");

  const projectAspect = project?.aspect_ratio || "9:16";
  const productionMode = project.mode;
  const [recipeId, setRecipeId] = React.useState("");
  const isCommerce = productionMode === "commerce";
  const isDrama = productionMode === "drama";
  const modeLabel = isCommerce ? "商品视频" : isDrama ? "短剧" : "知识视频";
  const { data: recipes = [] } = useQuery({
    queryKey: ["production-recipes", productionMode],
    queryFn: () => api.listProductionRecipes(productionMode),
    enabled: open,
  });
  React.useEffect(() => {
    if (!open || recipes.length === 0) return;
    const preferred = productionMode === "knowledge"
      ? "knowledge_smart_mix"
      : productionMode === "commerce"
      ? "commerce_product_showcase"
      : "drama_reference_i2v";
    if (!recipes.some((item) => item.recipe_id === recipeId)) {
      setRecipeId(recipes.find((item) => item.recipe_id === preferred)?.recipe_id || recipes[0].recipe_id);
    }
  }, [open, productionMode, recipeId, recipes]);
  const { data: dramaCharacters = [] } = useQuery({
    queryKey: ["drama-characters", projectId],
    queryFn: () => api.listDramaCharacters(projectId),
    enabled: open && isDrama,
  });
  const { data: dramaLocations = [] } = useQuery({
    queryKey: ["drama-locations", projectId],
    queryFn: () => api.listDramaLocations(projectId),
    enabled: open && isDrama,
  });
  const { data: dramaProps = [] } = useQuery({
    queryKey: ["drama-props", projectId],
    queryFn: () => api.listDramaProps(projectId),
    enabled: open && isDrama,
  });
  const dramaResourcesReady =
    dramaCharacters.length > 0 && dramaLocations.length > 0 && dramaProps.length > 0 &&
    [...dramaCharacters, ...dramaLocations, ...dramaProps].every((item) => item.approval_status === "approved");

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

  // Advanced: provider workflows
  const [showAdvanced, setShowAdvanced] = React.useState(false);
  const [imageWorkflowId, setImageWorkflowId] = React.useState("");
  const [videoWorkflowId, setVideoWorkflowId] = React.useState("");

  React.useEffect(() => {
    if (open) return;
    setShowAdvanced(false);
    setShowDramaAdditional(false);
    setRecipeId("");
    setSelectedTemplateId("");
    setTemplateParams({});
    setImageWorkflowId("");
    setVideoWorkflowId("");
  }, [open]);

  // Reset production options to project or system defaults each time the dialog opens.
  React.useEffect(() => {
    if (!open) return;
    const defaults = project?.default_production_settings || {};
    setContentMode(
      isContentMode(defaults.content_mode)
        ? defaults.content_mode
        : "generated_image",
    );
    setTaskVoiceId(
      typeof defaults.voice_id === "string" ? defaults.voice_id : "",
    );
    setTaskSpeed(typeof defaults.speed === "number" ? defaults.speed : 1.0);
    setTaskStylePreset(
      typeof defaults.style_preset === "string" &&
        STYLE_PRESET_OPTIONS.some(
          (item) => item.value === defaults.style_preset,
        )
        ? defaults.style_preset
        : "stick_figure",
    );
    setBgmAssetId(defaults.bgm_asset_id ? String(defaults.bgm_asset_id) : "");
    setBgmEnabled(
      typeof defaults.bgm_enabled === "boolean" ? defaults.bgm_enabled : true,
    );
    setBgmVolume(
      typeof defaults.bgm_volume === "number" ? defaults.bgm_volume : 0.2,
    );
  }, [open, project]);

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
    const projectTplId = project?.default_production_settings?.template_id
      ? canonicalTemplateId(String(project.default_production_settings.template_id))
      : "";
    const matchedProjectTpl = availableTemplates.find((t) => t.id === projectTplId);

    if (matchedProjectTpl) {
      setSelectedTemplateId(matchedProjectTpl.id);
      setTemplateParams(
        project.default_production_settings?.template_params ||
          matchedProjectTpl.default_params ||
          {},
      );
    } else {
      setSelectedTemplateId(availableTemplates[0].id);
      setTemplateParams(availableTemplates[0].default_params || {});
    }
  }, [open, availableTemplates, selectedTemplateId, project, canonicalTemplateId]);

  // Creation mutation
  const createTaskMutation = useMutation({
    mutationFn: async () => {
      const finalTitle =
        taskTitle.trim() ||
        (isCommerce
          ? "未命名商品视频任务"
          : isDrama
          ? `第 ${episodeNumber} 集`
          : creationMode === "fixed" ? rawScript.slice(0, 20) : "未命名短视频任务");

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

      const detail = productionMode === "commerce"
        ? {
            type: "commerce" as const,
            creative_angle: creativeAngle,
            hook: "",
            audience: "",
            core_message: "",
            cta: "",
          }
        : productionMode === "drama"
        ? {
            type: "drama" as const,
            episode_number: episodeNumber,
            synopsis: episodeSynopsis.trim(),
            script_text: creationMode === "fixed" ? rawScript.trim() : "",
            continuity_data: {
              character_ids: selectedCharacterIds,
              location_ids: selectedLocationIds,
              prop_ids: selectedPropIds,
              core_conflict: episodeConflict.trim(),
              ending_hook: episodeHook.trim(),
            },
          }
        : {
            type: "knowledge" as const,
            topic: finalTitle,
            audience: knowledgeAudience.trim(),
            thesis: knowledgeThesis.trim(),
            takeaway: knowledgeViewerTakeaway.trim(),
            genre: taskGenre,
          };
      return api.createProjectTask(projectId, {
        title: finalTitle,
        description:
          isCommerce
            ? `主商品营销视频 · 创意角度：${creativeAngle}`
            : isDrama
            ? `短剧第 ${episodeNumber} 集`
            : creationMode === "fixed"
            ? rawScript.slice(0, 200)
            : `知识主题：${finalTitle}，面向：${knowledgeAudience.trim() || "普通观众"}`,
        detail,
        generation_settings: {
          recipe_id: recipeId,
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
          image_workflow_id: imageWorkflowId || null,
          video_workflow_id: videoWorkflowId || null,
        },
      });
    },
    onSuccess: (newTask) => {
      queryClient.invalidateQueries({ queryKey: ["project-tasks", projectId] });
      toast(`${modeLabel}创建成功，正在进入工作台…`, "success");
      onOpenChange(false);
      // Reset main inputs
      setTaskTitle("");
      setRawScript("");
      setSourceAssetId("");
      setTargetSceneCount(SCENE_COUNT_MIN);
      setKnowledgeAudience("");
      setKnowledgeThesis("");
      setKnowledgeViewerTakeaway("");
      setCreativeAngle("direct");
      setEpisodeNumber(1);
      setEpisodeSynopsis("");
      setEpisodeConflict("");
      setEpisodeHook("");
      setSelectedCharacterIds([]);
      setSelectedLocationIds([]);
      setSelectedPropIds([]);
      setShowAdvanced(false);
      setShowDramaAdditional(false);
      router.push(`/projects/${projectId}/tasks/${newTask.id}`);
    },
    onError: (error: any) => {
      toast(`创建${modeLabel}失败：${error?.message || "请稍后重试"}`, "error");
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
      ? true
      : isDrama
      ? episodeNumber > 0 && Boolean(episodeSynopsis.trim()) && dramaResourcesReady
      : (creationMode === "generate" ? Boolean(taskTitle.trim()) : Boolean(rawScript.trim()))) &&
    (!contentModeSpec.requiresSourceAsset || Boolean(sourceAssetId)) &&
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
              <h2 className="text-base font-bold text-foreground">新建{modeLabel}</h2>
              {PRODUCTION_MODE_SPECS[productionMode]?.badge && (
                <Badge
                  variant="warning"
                  className="text-[10px] font-medium tracking-wide uppercase px-1.5 py-0 rounded"
                >
                  {PRODUCTION_MODE_SPECS[productionMode].badge}
                </Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              项目：《{project.name}》· {project.aspect_ratio} 画幅
            </p>
          </div>
        </div>
      </div>

      {/* Studio Two-Column Body */}
      <form onSubmit={handleSubmit} className="flex-1 flex flex-col min-h-0 overflow-hidden">
        <div className="flex-1 overflow-y-auto min-h-0">
          {productionMode !== "knowledge" && (
            <div className="border-b border-border px-5 py-3 sm:px-6">
              <button
                type="button"
                onClick={() => setShowAdvanced((value) => !value)}
                aria-expanded={showAdvanced}
                aria-controls={`production-setting-recipes production-setting-voice production-setting-visual production-setting-bgm production-setting-generation${usesAiVisualStyle ? " production-setting-style" : ""}`}
                className="flex min-h-11 w-full items-center justify-between rounded-lg text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
              >
                <span className="flex items-center gap-2"><Settings2 aria-hidden="true" className="h-4 w-4 text-primary" />制作设置</span>
                <ChevronDown aria-hidden="true" className={`h-4 w-4 transition-transform ${showAdvanced ? "rotate-180" : ""}`} />
              </button>
            </div>
          )}
          <div>
            <div className="grid grid-cols-1 lg:grid-cols-12 divide-y lg:divide-y-0 lg:divide-x divide-border">
            {/* Left Column: Creative Core (58%) */}
            <div className="lg:col-span-7 p-5 sm:p-6 space-y-5">
              {showAdvanced && productionMode !== "knowledge" && <section id="production-setting-recipes" className="space-y-2.5 rounded-xl border border-border bg-card/40 p-4" aria-labelledby="recipe-heading">
                <div>
                  <h3 id="recipe-heading" className="text-sm font-semibold">选择成片方案</h3>
                  <p className="mt-1 text-xs text-muted-foreground">默认使用推荐方案，也可在这里更改。</p>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {recipes.map((recipe: ProductionRecipe) => (
                    <button
                      key={recipe.recipe_id}
                      type="button"
                      aria-pressed={recipeId === recipe.recipe_id}
                      onClick={() => setRecipeId(recipe.recipe_id)}
                      className={`rounded-xl border p-3 text-left transition-colors ${recipeId === recipe.recipe_id ? "border-primary bg-primary/10" : "border-border bg-card hover:bg-secondary/40"}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium">{recipe.name}</span>
                        <Badge variant="outline">{recipe.cost_tier === "high" ? "较高成本" : recipe.cost_tier === "medium" ? "中等成本" : "低成本"}</Badge>
                      </div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">{recipe.description}</p>
                      <p className="mt-2 text-[11px] text-muted-foreground">
                        {recipe.requires_reference_assets ? "需要参考/真实素材" : "可不提供参考素材"}
                        {recipe.required_capabilities.length ? ` · 需要 ${recipe.required_capabilities.join(" / ")} 生成能力` : " · 无额外生成能力要求"}
                      </p>
                    </button>
                  ))}
                </div>
              </section>}
              {isCommerce ? (
                <CommerceTaskForm
                  creativeAngle={creativeAngle}
                  onCreativeAngleChange={setCreativeAngle}
                  taskTitle={taskTitle}
                  onTaskTitleChange={setTaskTitle}
                />
              ) : isDrama ? (
                <div className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-[120px_1fr]">
                    <label className="space-y-1.5 text-sm font-medium" htmlFor="episode-number"><span>集数</span><Input id="episode-number" type="number" min={1} value={episodeNumber} onChange={(event) => setEpisodeNumber(Math.max(1, Number(event.target.value)))} /></label>
                    <label className="space-y-1.5 text-sm font-medium" htmlFor="episode-synopsis"><span>本集梗概 <span className="text-destructive">*</span></span><Textarea id="episode-synopsis" value={episodeSynopsis} onChange={(event) => setEpisodeSynopsis(event.target.value)} rows={4} required placeholder="主角想做什么、遇到什么阻碍、结果如何变化？" /></label>
                  </div>
                  {!dramaResourcesReady && <p role="alert" className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs leading-5 text-warning">请先在连续性资料库中补齐并审批人物、地点和道具。</p>}
                  <div className="border-t border-border pt-3">
                    <button type="button" onClick={() => setShowDramaAdditional((value) => !value)} aria-expanded={showDramaAdditional} aria-controls="drama-additional-fields" className="flex min-h-11 w-full items-center justify-between text-sm font-medium text-muted-foreground hover:text-foreground"><span>补充要求</span><ChevronDown aria-hidden="true" className={`h-4 w-4 transition-transform ${showDramaAdditional ? "rotate-180" : ""}`} /></button>
                    {showDramaAdditional && <div id="drama-additional-fields" className="mt-3 space-y-4 rounded-xl border border-border bg-card/40 p-4">
                      <label className="block space-y-1.5 text-sm font-medium" htmlFor="episode-title"><span>本集标题（可选）</span><Input id="episode-title" value={taskTitle} onChange={(event) => setTaskTitle(event.target.value)} placeholder={`默认：第 ${episodeNumber} 集`} /></label>
                      <div className="grid gap-4 sm:grid-cols-2">
                        <label className="space-y-1.5 text-sm font-medium" htmlFor="episode-conflict"><span>核心冲突</span><Textarea id="episode-conflict" value={episodeConflict} onChange={(event) => setEpisodeConflict(event.target.value)} rows={3} placeholder="人物目标与阻力" /></label>
                        <label className="space-y-1.5 text-sm font-medium" htmlFor="episode-hook"><span>结尾钩子</span><Textarea id="episode-hook" value={episodeHook} onChange={(event) => setEpisodeHook(event.target.value)} rows={3} placeholder="下一集的悬念" /></label>
                      </div>
                      <DramaResourcePicker icon={Users} label="本集人物" items={dramaCharacters} selected={selectedCharacterIds} onChange={setSelectedCharacterIds} />
                      <DramaResourcePicker icon={MapPin} label="主要地点" items={dramaLocations} selected={selectedLocationIds} onChange={setSelectedLocationIds} />
                      <DramaResourcePicker icon={Package} label="关键道具" items={dramaProps} selected={selectedPropIds} onChange={setSelectedPropIds} />
                    </div>}
                  </div>
                </div>
              ) : (
                <KnowledgeTaskForm
                  key={open ? `open-${projectId}` : "closed"}
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
                  hookType={taskHookType}
                  onHookTypeChange={setTaskHookType}
                  enableResearch={enableResearch}
                  onEnableResearchChange={setEnableResearch}
                  audience={knowledgeAudience}
                  onAudienceChange={setKnowledgeAudience}
                  thesis={knowledgeThesis}
                  onThesisChange={setKnowledgeThesis}
                  viewerTakeaway={knowledgeViewerTakeaway}
                  onViewerTakeawayChange={setKnowledgeViewerTakeaway}
                />
              )}

              {/* Visual Style Preset Selection */}
              {(productionMode === "knowledge" ? usesAiVisualStyle : (showAdvanced && usesAiVisualStyle)) && (
                <div id="production-setting-style" className="space-y-2.5 pt-3 border-t border-border">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-foreground flex items-center gap-2">
                      <Palette className="h-4 w-4 text-primary" />
                      <span>画面视觉风格</span>
                    </label>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {STYLE_PRESET_OPTIONS.map((style) => (
                      <button
                        key={style.value}
                        type="button"
                        onClick={() => setTaskStylePreset(style.value)}
                        aria-pressed={taskStylePreset === style.value}
                        className={`relative p-2.5 rounded-xl border text-left transition-all cursor-pointer ${
                          taskStylePreset === style.value
                            ? "border-primary bg-primary/10 text-foreground ring-1 ring-primary/80 shadow-xs"
                            : "border-border bg-card text-muted-foreground hover:bg-secondary/40 hover:text-foreground"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1">
                          <span className="text-sm font-semibold text-foreground leading-snug">{style.label}</span>
                          {taskStylePreset === style.value && (
                            <span className="h-4 w-4 rounded-full bg-primary flex items-center justify-center text-primary-foreground shrink-0">
                              <Check className="h-2.5 w-2.5 stroke-[3]" />
                            </span>
                          )}
                        </div>
                        <div className="mt-1 line-clamp-2 text-xs text-muted-foreground leading-relaxed">
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
                      成片规格画像
                    </span>
                    <Badge variant="outline" className="font-mono text-xs px-2 py-0.5">
                      {project.aspect_ratio} 画幅
                    </Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div className="space-y-0.5">
                      <span className="text-xs text-muted-foreground">分镜篇幅</span>
                      <p className="font-medium text-foreground truncate">
                        {productionMode === "knowledge"
                          ? creationMode === "generate" ? `${targetSceneCount} 镜 · 约 ${targetSceneCount * 4}s` : "文案拆解计算"
                          : productionMode === "drama" ? `第 ${episodeNumber} 集` : "创意角度驱动"}
                      </p>
                    </div>
                    <div className="space-y-0.5">
                      <span className="text-xs text-muted-foreground">画面风格</span>
                      <p className="font-medium text-foreground truncate">{selectedStyle?.label || "简约火柴人"}</p>
                    </div>
                    <div className="space-y-0.5">
                      <span className="text-xs text-muted-foreground">旁白音色</span>
                      <p className="font-medium text-foreground truncate">{voiceDisplayName}</p>
                    </div>
                    <div className="space-y-0.5">
                      <span className="text-xs text-muted-foreground">事实核验</span>
                      <p className={`font-medium truncate ${enableResearch ? "text-primary" : "text-muted-foreground"}`}>
                        {enableResearch ? "已开启联网核对" : "未开启"}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Knowledge Mode: Target Scene Count (Core spec) */}
                {productionMode === "knowledge" && creationMode === "generate" && (
                  <div className="space-y-2.5 rounded-xl border border-border bg-card/60 p-3.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-foreground">分镜篇幅规划</span>
                      <span className="font-mono text-xs text-primary font-medium">
                        目标 {targetSceneCount} 镜 · 约 {targetSceneCount * 4} 秒
                      </span>
                    </div>
                    <div className="grid grid-cols-5 gap-1.5">
                      {SCENE_COUNT_PRESETS.map((preset) => (
                        <button
                          key={preset.count}
                          type="button"
                          onClick={() => setTargetSceneCount(preset.count)}
                          aria-pressed={targetSceneCount === preset.count}
                          className={`min-h-11 px-1 rounded-lg text-center border transition-all cursor-pointer select-none ${
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
                  </div>
                )}

                {/* TTS Voice & Speed (Visible in knowledge, or when showAdvanced in other modes) */}
                {(productionMode === "knowledge" || showAdvanced) && (
                  <div id="production-setting-voice" className="space-y-2.5 border-t border-border pt-3">
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
                          className={`min-h-9 flex-1 rounded-md text-xs font-mono transition-colors cursor-pointer ${
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
                )}

                {/* Advanced Technical Settings: Collapsible in Knowledge mode, or expanded in other modes when showAdvanced */}
                {productionMode === "knowledge" ? (
                  <div className="border-t border-border pt-3">
                    <button
                      type="button"
                      onClick={() => setShowAdvanced((v) => !v)}
                      aria-expanded={showAdvanced}
                      className="flex min-h-11 w-full items-center justify-between rounded-xl border border-border/80 bg-card/60 px-3.5 py-2.5 text-left text-sm font-medium transition-colors hover:bg-card hover:text-foreground cursor-pointer"
                    >
                      <span className="flex items-center gap-2">
                        <Settings2 aria-hidden="true" className="h-4 w-4 text-primary" />
                        <span>高级制作设置</span>
                      </span>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground font-normal hidden sm:inline truncate max-w-[180px]">
                          {CONTENT_MODE_LABELS[contentMode]} · {bgmEnabled ? "含BGM" : "无BGM"}
                        </span>
                        <ChevronDown
                          aria-hidden="true"
                          className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${
                            showAdvanced ? "rotate-180" : ""
                          }`}
                        />
                      </div>
                    </button>
                    {showAdvanced && (
                      <div className="mt-3 space-y-4 rounded-xl border border-border/80 bg-card/40 p-3.5">
                        {/* Visual Mode & Template */}
                        <div id="production-setting-visual" className="space-y-2.5">
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div className="space-y-1.5">
                              <label htmlFor="studio-content-mode" className="text-xs font-medium text-foreground">
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
                              <p id="studio-content-mode-description" className="text-[11px] text-muted-foreground">
                                {CONTENT_MODE_SPECS[contentMode].selectionHint}
                              </p>
                            </div>

                            <div className="space-y-1.5">
                              <div className="flex items-center justify-between">
                                <label htmlFor="studio-template" className="text-xs font-medium text-foreground">
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
                                  ? "w-16 aspect-[16/9]"
                                  : projectAspect === "1:1"
                                  ? "w-12 aspect-square"
                                  : "w-10 aspect-[9/16]"
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

                          {contentMode === "uploaded_asset" && (
                            <div className="space-y-1.5">
                              <label htmlFor="studio-source-asset" className="text-xs font-medium text-foreground">
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
                        </div>

                        {/* Background Music Section */}
                        <div id="production-setting-bgm" className="space-y-2 border-t border-border/80 pt-3">
                          <div className="flex items-center justify-between">
                            <label className="text-xs font-medium text-foreground flex items-center gap-1.5">
                              <Music className="h-3.5 w-3.5 text-primary" />
                              <span>背景音乐</span>
                            </label>
                            <label htmlFor="studio-bgm-toggle" className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
                              <input
                                id="studio-bgm-toggle"
                                type="checkbox"
                                checked={bgmEnabled}
                                onChange={(e) => setBgmEnabled(e.target.checked)}
                                className="rounded border-border text-primary focus:ring-primary h-3.5 w-3.5 cursor-pointer accent-primary"
                              />
                              <span>启用</span>
                            </label>
                          </div>

                          {bgmEnabled && (
                            <div className="space-y-2 rounded-lg bg-card/80 p-2.5 border border-border">
                              <Select
                                id="studio-bgm-select"
                                value={bgmAssetId}
                                onChange={(e) => setBgmAssetId(e.target.value)}
                                className="h-8 text-xs"
                              >
                                <option value="">使用项目默认背景音乐</option>
                                {projectBgm.map((asset) => (
                                  <option key={asset.id} value={asset.id}>
                                    {asset.file_name}
                                  </option>
                                ))}
                              </Select>

                              <div className="flex items-center gap-2 text-xs text-muted-foreground">
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
                                <span className="font-mono w-7 text-right text-foreground font-medium">
                                  {bgmVolume.toFixed(2)}
                                </span>
                              </div>

                              {bgmAssetId && projectBgm.find((a) => a.id === bgmAssetId) && (
                                <audio
                                  controls
                                  preload="none"
                                  className="h-7 w-full mt-1"
                                  src={assetFileUrl(projectBgm.find((a) => a.id === bgmAssetId)!.file_path)}
                                />
                              )}
                            </div>
                          )}
                        </div>

                        {/* ComfyUI Workflows */}
                        <div id="production-setting-generation" className="space-y-2 border-t border-border/80 pt-3">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-foreground">底层生成工作流</span>
                            <span className="text-[10px] text-muted-foreground font-normal">仅限 ComfyUI 专用</span>
                          </div>

                          <div className="space-y-1">
                            <label htmlFor="studio-img-workflow" className="text-[11px] text-muted-foreground">
                              图像生成工作流
                            </label>
                            <Select
                              id="studio-img-workflow"
                              value={imageWorkflowId}
                              onChange={(e) => setImageWorkflowId(e.target.value)}
                              disabled={contentMode !== "generated_image"}
                              className="h-8 text-xs"
                            >
                              <option value="">使用默认图像工作流</option>
                              {workflows
                                .filter((w) => w.type === "image")
                                .map((w) => (
                                  <option key={w.id} value={w.id}>
                                    {w.name}
                                  </option>
                                ))}
                            </Select>
                          </div>

                          <div className="space-y-1">
                            <label htmlFor="studio-video-workflow" className="text-[11px] text-muted-foreground">
                              视频生成工作流
                            </label>
                            <Select
                              id="studio-video-workflow"
                              value={videoWorkflowId}
                              onChange={(e) => setVideoWorkflowId(e.target.value)}
                              disabled={contentMode !== "generated_video"}
                              className="h-8 text-xs"
                            >
                              <option value="">使用默认视频工作流</option>
                              {workflows
                                .filter((w) => w.type === "video")
                                .map((w) => (
                                  <option key={w.id} value={w.id}>
                                    {w.name}
                                  </option>
                                ))}
                            </Select>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  showAdvanced && (
                    <>
                      {/* Visual Mode & Template */}
                      <div id="production-setting-visual" className="space-y-2.5 pt-3 border-t border-border">
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
                      </div>

                      {/* Background Music Section */}
                      <div id="production-setting-bgm" className="space-y-2.5 pt-3 border-t border-border">
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
                      </div>

                      {/* Additional generation settings */}
                      <div id="production-setting-generation" className="mt-3 space-y-3 rounded-lg border border-border bg-card/80 p-3.5">
                        <div className="space-y-1.5">
                          <label htmlFor="studio-img-workflow" className="text-xs text-muted-foreground">
                            图像生成工作流
                          </label>
                          <Select
                            id="studio-img-workflow"
                            value={imageWorkflowId}
                            onChange={(e) => setImageWorkflowId(e.target.value)}
                            disabled={contentMode !== "generated_image"}
                            className="h-9 text-sm"
                          >
                            <option value="">使用默认图像工作流</option>
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
                            视频生成工作流
                          </label>
                          <Select
                            id="studio-video-workflow"
                            value={videoWorkflowId}
                            onChange={(e) => setVideoWorkflowId(e.target.value)}
                            disabled={contentMode !== "generated_video"}
                            className="h-9 text-sm"
                          >
                            <option value="">使用默认视频工作流</option>
                            {workflows
                              .filter((w) => w.type === "video")
                              .map((w) => (
                                <option key={w.id} value={w.id}>
                                  {w.name}
                                </option>
                              ))}
                          </Select>
                        </div>
                      </div>
                    </>
                  )
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
            className="h-11 text-sm px-4"
          >
            取消
          </Button>
          <Button
            type="submit"
            disabled={createTaskMutation.isPending || !isFormValid}
            className="h-11 text-sm px-5 gap-2 font-medium"
          >
            <Wand2 className="h-4 w-4" />
            <span>{createTaskMutation.isPending ? `正在创建${modeLabel}…` : `创建${modeLabel}`}</span>
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
