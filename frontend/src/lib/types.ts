export type AspectRatio = "9:16" | "16:9" | "1:1";
export type ProjectStatus = "draft" | "configured" | "generating" | "completed" | "failed";
export type AssetType = "image" | "video" | "audio" | "bgm" | "font";
export type JobStatus =
  | "queued"
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "retrying";
export type TaskStatus =
  | "draft"
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "retrying";
export type PlatformType = "douyin" | "xiaohongshu" | "bilibili" | "wechat_video" | "tiktok" | "mock";
export type PublishJobStatus =
  | "draft"
  | "scheduled"
  | "queued"
  | "publishing"
  | "published"
  | "failed"
  | "cancelled"
  | "missed"
  | "uncertain";
export type VisualMode = "image" | "video";
export type ContentMode = "generated_image" | "generated_video" | "online_asset" | "static" | "uploaded_asset";
export type TemplateType = "image" | "video" | "static" | "asset";

export interface ScheduledPublishConfig {
  account_id: string;
  scheduled_at: string;
  timezone: string;
}

export type ScheduledPublishStatus =
  | "pending"
  | "scheduled"
  | "queued"
  | "publishing"
  | "published"
  | "failed"
  | "cancelled"
  | "missed"
  | string;

export interface ScheduledPublishState extends Partial<ScheduledPublishConfig> {
  enabled?: boolean;
  status?: ScheduledPublishStatus | null;
  publishing_job_id?: string | null;
  error_message?: string | null;
}

export interface TemplateParameter {
  name: string;
  type: string;
  default?: any;
  label?: string | null;
}

export interface TemplateCatalogItem {
  id: string;
  name: string;
  version: string;
  width: number;
  height: number;
  aspect_ratio: AspectRatio | string;
  media_width: number;
  media_height: number;
  template_type: TemplateType | string;
  html_path: string;
  preview_path?: string | null;
  parameter_schema: TemplateParameter[];
  default_params: Record<string, any>;
  supported_content_modes: ContentMode[];
}

export interface ProjectTemplate {
  id: string;
  project_id: string;
  name: string;
  aspect_ratio: AspectRatio;
  style_preset: string;
  font_family: string;
  primary_color: string;
  background_color: string;
  layout_type: string;
  frame_template: string;
  template_id: string;
  template_version: string;
  custom_css: string;
  params: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface ProjectTemplateUpdate {
  name?: string;
  aspect_ratio?: AspectRatio;
  style_preset?: string;
  font_family?: string;
  primary_color?: string;
  background_color?: string;
  layout_type?: string;
  frame_template?: string;
  template_id?: string;
  template_version?: string;
  custom_css?: string;
  params?: Record<string, any>;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  aspect_ratio: AspectRatio;
  status: ProjectStatus;
  cover_asset_id?: string | null;
  default_voice_id?: string | null;
  bgm_asset_id?: string | null;
  settings: Record<string, any>;
  template?: ProjectTemplate | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends Project {
  tasks: Task[];
}

export interface Scene {
  id: string;
  task_id: string;
  sequence_index: number;
  narration_text: string;
  visual_prompt: string;
  duration_seconds: number;
  layout_params: Record<string, any>;
  audio_asset_id?: string | null;
  media_asset_id?: string | null;
  rendered_segment_asset_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SceneCreate {
  sequence_index: number;
  narration_text: string;
  visual_prompt: string;
  duration_seconds: number;
  layout_params?: Record<string, any>;
  audio_asset_id?: string | null;
  media_asset_id?: string | null;
}

export interface WorkflowJob {
  id: string;
  task_id: string;
  job_type: string;
  status: JobStatus;
  progress: number;
  current_stage?: string | null;
  params?: Record<string, any>;
  checkpoint?: Record<string, any>;
  result?: Record<string, any> | null;
  error_message?: string | null;
  retry_count: number;
  max_retries: number;
  available_at?: string | null;
  scheduled_at?: string | null;
  created_at: string;
  started_at?: string | null;
  heartbeat_at?: string | null;
  completed_at?: string | null;
  updated_at?: string;
}

export interface Task {
  id: string;
  project_id: string;
  title: string;
  description: string;
  job_type: string;
  status: TaskStatus;
  progress_percentage: number;
  input_payload: Record<string, any>;
  result_payload?: Record<string, any> | null;
  error_message?: string | null;
  scenes_count?: number;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  active_job?: WorkflowJob | null;
  current_stage?: string | null;
  resume_count?: number;
  last_heartbeat_at?: string | null;
  can_resume?: boolean;
  scheduled_publish?: ScheduledPublishState | null;
}

export interface TaskDetail extends Task {
  scenes: Scene[];
}

export interface Asset {
  id: string;
  project_id?: string | null;
  asset_type: AssetType;
  file_name: string;
  file_path: string;
  mime_type: string;
  file_size_bytes: number;
  duration_seconds?: number | null;
  width?: number | null;
  height?: number | null;
  metadata_json: Record<string, any>;
  created_at: string;
}

export interface AssetBatchSkippedItem {
  id: string;
  reason: string;
}

export interface AssetBatchResult {
  deleted_ids?: string[];
  updated_ids?: string[];
  skipped?: AssetBatchSkippedItem[];
  assets?: Asset[];
}

export interface ResearchSource {
  title: string;
  url: string;
  snippet: string;
  domain?: string | null;
  published_at?: string | null;
  score?: number | null;
}

export interface ResearchQueryRecord {
  query: string;
  status: "completed" | "failed" | "skipped" | string;
  result_count: number;
  error_message?: string | null;
}

export interface ResearchResponse {
  topic: string;
  status: "pending" | "completed" | "failed" | "skipped" | string;
  provider?: string | null;
  queries: string[];
  query_records?: ResearchQueryRecord[];
  query_source?: "llm" | "heuristic" | string;
  warnings?: string[];
  summary: string;
  sources: ResearchSource[];
  from_cache: boolean;
  error_message?: string | null;
  duration_seconds?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface PlatformMetadata {
  platform?: string;
  title?: string;
  description: string;
  tags: string[];
  declaration?: string;
  location?: string | null;
  collection_name?: string | null;
  visibility?: "public" | "friend" | "private" | string;
  allow_download?: boolean;
  platform_custom_params?: Record<string, any>;
}

export interface StructuredSceneScript {
  sequence_index: number;
  narration_text: string;
  visual_prompt: string;
  badge_text?: string;
}

export interface StructuredScript {
  title: string;
  hook: string;
  narration: string;
  scenes: StructuredSceneScript[];
  metadata?: PlatformMetadata | null;
}

export interface ScriptGenerateRequest {
  topic: string;
  mode?: "generate" | "fixed" | string;
  raw_script?: string;
  split_mode?: "paragraph" | "line" | "sentence" | string;
  genre?: string;
  hook_type?: string;
  style_preset?: string;
  prompt_prefix?: string;
  voice_id?: string;
  speed?: number;
  enable_research?: boolean;
  search_provider_id?: string | null;
  research_max_queries?: number;
  research_max_results?: number;
  research_context?: string;
  target_scene_count?: number;
}

export interface ProviderConfigItem {
  id: string;
  provider_type: "llm" | "search" | "image" | "video" | "tts" | "publishing" | string;
  provider_name: string;
  display_name: string;
  enabled: boolean;
  is_default: boolean;
  config: Record<string, any>;
  masked_credentials: Record<string, string>;
  has_credentials: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProviderCreatePayload {
  id?: string;
  provider_type: string;
  provider_name: string;
  display_name: string;
  enabled?: boolean;
  is_default?: boolean;
  config?: Record<string, any>;
  credentials?: Record<string, any>;
}

export interface ProviderUpdatePayload {
  display_name?: string;
  enabled?: boolean;
  is_default?: boolean;
  config?: Record<string, any>;
  credentials?: Record<string, any>;
}

export interface ProviderTestResult {
  connected: boolean;
  message: string;
  latency_ms?: number;
  details?: Record<string, any>;
  tested_at?: string | null;
}

export interface ImageGenerationTestResult extends ProviderTestResult {
  image_url?: string;
  width?: number;
  height?: number;
  format?: string;
}

export type SystemConfigStatus =
  | "ready"
  | "not_tested"
  | "not_configured"
  | "failed"
  | "disabled"
  | string;

export interface SystemConfigProviderSummary {
  id: string;
  provider_type: string;
  provider_name: string;
  display_name: string;
  enabled: boolean;
  is_default: boolean;
  config: Record<string, any>;
  masked_credentials: Record<string, string>;
  has_credentials: boolean;
  configured: boolean;
  connection_status: SystemConfigStatus;
  missing_fields: string[];
  last_test?: ProviderTestResult | null;
}

export interface SystemConfigCategorySummary {
  type: string;
  label: string;
  required: boolean;
  status: SystemConfigStatus;
  configured: boolean;
  enabled: boolean;
  default_provider_id?: string | null;
  default_provider_name?: string | null;
  missing_fields: string[];
  provider_ids: string[];
  account_count?: number | null;
}

export interface SystemConfigAccountSummary {
  id: string;
  account_name: string;
  username: string;
  platform: string;
  status: string;
  credential_present: boolean;
  credential_status: SystemConfigStatus;
}

export interface SystemConfigSummary {
  generated_at: number;
  overall: {
    status: SystemConfigStatus;
    label: string;
    configured_categories: number;
    ready_categories: number;
    pending_test_categories: number;
    failed_categories: number;
    missing_items: Array<{
      category: string;
      label: string;
      required: boolean;
      fields: string[];
    }>;
  };
  system: {
    app_name: string;
    app_version: string;
    debug: boolean;
  };
  storage: {
    database: string;
    data_dir: string;
    storage_dir: string;
    worker_count: number;
    task_timeout_seconds: number;
  };
  categories: SystemConfigCategorySummary[];
  providers: SystemConfigProviderSummary[];
  publishing: {
    status: SystemConfigStatus;
    total_accounts: number;
    pending_accounts: number;
    invalid_accounts: number;
    accounts: SystemConfigAccountSummary[];
  };
}

export interface VoiceInfo {
  id: string;
  name: string;
  gender: string;
  language: string;
  locale: string;
}

export interface SocialAccount {
  id: string;
  platform: PlatformType;
  account_name: string;
  username: string;
  avatar_url?: string | null;
  status: string;
  credential_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface QRStartResponse {
  session_id: string;
  platform: string;
  status: string;
  qrcode_data_url?: string | null;
}

export interface QRStatusResponse {
  session_id: string;
  platform: string;
  status: "initializing" | "pending" | "success" | "expired" | "timeout" | "error" | string;
  qrcode_data_url?: string | null;
  is_logged_in: boolean;
  error_message?: string | null;
}

export interface AccountCheckResponse {
  account_id: string;
  is_valid: boolean;
  username?: string | null;
  display_name?: string | null;
  error_message?: string | null;
  checked_at: string;
}

export interface PublishingJob {
    id: string;
    task_id?: string | null;
  project_id: string;
  video_asset_id: string;
  account_id: string;
  platform: PlatformType;
  title: string;
  description: string;
  tags: string[];
  cover_asset_id?: string | null;
  status: PublishJobStatus;
  scheduled_at?: string | null;
  published_at?: string | null;
  attempt_count: number;
  max_attempts: number;
  error_message?: string | null;
  platform_post_id?: string | null;
  custom_params: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface VerificationRequestItem {
  request_id: string;
  job_id: string;
  account_id: string;
  account_name: string;
  title: string;
  platform: string;
  prompt: string;
  status: string;
  remaining_seconds: number;
  timeout_seconds: number;
  created_at: number;
  error_message?: string | null;
}
export interface WorkflowArtifact {
  id: string; task_id: string; step_run_id: string; kind: string;
  relative_path: string; size_bytes: number; sha256: string; source: string;
}
export interface WorkflowStepRun {
  id: string; job_id: string; step_key: string; unit_key: string; attempt: number;
  status: string; validity: string; invalid_reason?: string | null;
  duration_ms?: number | null; error_message?: string | null; warning?: string | null;
  started_at: string; completed_at?: string | null; artifacts: WorkflowArtifact[];
}
export interface WorkflowStageSummary {
  step_key: string; status: string; validity: string; duration_ms: number; retry_count: number;
  units: WorkflowStepRun[]; history: WorkflowStepRun[];
}
export interface WorkflowSnapshot { task_id: string; stages: WorkflowStageSummary[]; }
