import {
  CONTENT_MODE_SPECS,
  SCENE_COUNT_MAX,
  SCENE_COUNT_MIN,
  isContentMode,
} from "@/lib/ui-constants";
import type { ContentMode } from "@/lib/types";

export function generationStatus(
  task: {
    production_status?: string;
    latest_job?: { status?: string; job_type?: string } | null;
  },
  liveStatus: string | null = null,
): string {
  const job = task.latest_job;
  if (job && job.job_type !== "publish" && job.status) {
    if (job.status === "queued" || job.status === "pending") return "pending";
    if (job.status === "retrying") return "running";
    return job.status;
  }
  if (
    ["completed", "failed", "cancelled"].includes(task.production_status || "")
  )
    return task.production_status!;
  return liveStatus || task.production_status || "not_started";
}

export function isGenerationLifecycleEvent(event: string): boolean {
  return /^(task\.(started|completed|failed|cancelled)|job\.(started|retrying|completed|failed|cancelled|uncertain))$/.test(
    event,
  );
}

export type SceneAssetRefreshAction = "workflow_unit" | "none";
export interface GenerationOptionsInput {
  targetSceneCount: number;
  enableResearch: boolean;
  contentMode: ContentMode;
  templateId: string;
  genre: string;
  hookType: string;
  stylePreset: string;
  promptPrefix: string;
  voiceId?: string | null;
  speed: number;
  bgmEnabled: boolean;
  bgmAssetId?: string | null;
  bgmVolume: number;
  sourceAssetId?: string | null;
}

export function buildGenerationOptions(
  input: GenerationOptionsInput,
  base: Record<string, unknown> = {},
): Record<string, unknown> {
  const speed = Math.max(0.5, Math.min(2, input.speed));
  const bgmVolume = Math.max(0, Math.min(0.5, input.bgmVolume));
  return {
    ...base,
    target_scene_count: Math.max(
      SCENE_COUNT_MIN,
      Math.min(SCENE_COUNT_MAX, input.targetSceneCount),
    ),
    enable_research: input.enableResearch,
    content_mode: input.contentMode,
    template_id: input.templateId,
    genre: input.genre,
    hook_type: input.hookType,
    style_preset: input.stylePreset,
    prompt_prefix: input.promptPrefix,
    voice_id: input.voiceId || null,
    speed,
    bgm_enabled: input.bgmEnabled,
    bgm_asset_id: input.bgmEnabled ? input.bgmAssetId || null : null,
    bgm_volume: bgmVolume,
    source_asset_id:
      input.contentMode === "uploaded_asset"
        ? input.sourceAssetId || null
        : null,
  };
}

export function isSourceMaterialMode(contentMode: string | undefined): boolean {
  return (
    isContentMode(contentMode) &&
    CONTENT_MODE_SPECS[contentMode].sourceKind === "online"
  );
}

export function resolveSceneAssetRefreshAction(
  contentMode: string | undefined,
  hasRetryUnit: boolean,
  hasSceneId: boolean,
): SceneAssetRefreshAction {
  if (
    isContentMode(contentMode) &&
    CONTENT_MODE_SPECS[contentMode].supportsSceneRetry &&
    hasRetryUnit &&
    hasSceneId
  )
    return "workflow_unit";
  return "none";
}
