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
export const CONTENT_MODE_VALUES = [
  "generated_image",
  "generated_video",
  "online_asset",
  "static",
  "uploaded_asset",
] as const;
export type ContentMode = (typeof CONTENT_MODE_VALUES)[number];
export type DramaContentMode = Extract<ContentMode, "generated_image" | "generated_video">;
export const PRODUCTION_MODE_VALUES = ["knowledge", "commerce", "drama"] as const;
export type ProductionMode = (typeof PRODUCTION_MODE_VALUES)[number];
export type DramaSourceType = "idea" | "script";
export type DramaStage = "story" | "bible" | "assets" | "episode" | "storyboard" | "approval";
export type DramaWorkflowStatus = "draft" | "in_progress" | "paused" | "completed" | "failed";
export type DramaApprovalStatus = "draft" | "in_review" | "approved" | "changes_requested";
export type CreativeAngle =
  | "direct"
  | "pain_point"
  | "use_case"
  | "demo"
  | "review"
  | "comparison"
  | "story";
export type CreativePlanStatus = "draft" | "selected" | "variant" | "archived";
export type VisualRole =
  | "concept"
  | "process"
  | "comparison"
  | "timeline"
  | "data"
  | "example"
  | "quote"
  | "b_roll"
  | "product_shot"
  | "context"
  | "benefit"
  | "proof"
  | "cta";
export type TemplateType = "image" | "video" | "static" | "asset";

/** Persisted trend feed contract; source ingestion remains an explicit adapter boundary. */
export type TrendFreshness = "15m" | "1h" | "6h" | "24h" | "all";
export type TrendRelation = "high" | "medium" | "low" | "unknown";
export type TrendSourceStatus = "fresh" | "stale" | "failed" | "unavailable";

export interface TrendSourceRun {
  id: string;
  source_key: string;
  adapter_name: string;
  platform: string;
  status: TrendSourceStatus;
  item_count: number;
  fetched_at?: string | null;
  source_updated_at?: string | null;
  error_message?: string | null;
}

export interface TrendRun {
  id: string;
  status: string;
  requested_platforms: string[];
  source_count: number;
  success_count: number;
  stale_count: number;
  error_count: number;
  error_summary?: string | null;
  fetched_at?: string | null;
  started_at: string;
  completed_at?: string | null;
  subscription_id?: string | null;
  trigger_key?: string | null;
  sources: TrendSourceRun[];
}

export interface TrendSourceCatalog {
  source_key: string;
  adapter_name: string;
  platform: string;
  platform_label: string;
  primary_available: boolean;
  fallback_available: boolean;
}

export interface TrendSourceHealth {
  source_key: string;
  platform: string;
  status: TrendSourceRun["status"];
  item_count: number;
  fetched_at?: string | null;
  error_message?: string | null;
}

export interface TrendItem {
  id: string;
  title: string;
  platform: string;
  platform_label?: string | null;
  rank: number;
  raw_metric?: string | number | null;
  metric_unit?: string | null;
  fetched_at?: string | null;
  source_url?: string | null;
  project_relevance?: TrendRelation;
  source_status?: TrendSourceStatus;
  risk_note?: string | null;
  summary?: string | null;
}

export interface TrendFeedResponse {
  items: TrendItem[];
  status: "ready" | "stale" | "unavailable";
  fetched_at?: string | null;
  source_message?: string | null;
}

export interface TrendPreferences {
  project_id: string;
  include_keywords: string[];
  exclude_keywords: string[];
  platforms: string[];
}

export type TrendSubscriptionStatus = "active" | "paused" | "running" | "stale" | "failed" | "unavailable";
export type TrendFrequency = "15m" | "1h" | "6h" | "24h";

export interface TrendPreferencesUpdateRequest {
  include_keywords?: string[];
  exclude_keywords?: string[];
  platforms?: string[];
}

export interface TrendSubscriptionRequest {
  enabled?: boolean;
  platforms?: string[];
  source_keys?: string[];
  frequency?: TrendFrequency;
  timezone?: string;
}

export interface TrendSubscriptionCreateRequest extends TrendSubscriptionRequest {
  project_id: string;
}

export interface TrendProposalCreateRequest {
  project_id: string;
  trend_item_id: string;
  angle?: string;
  knowledge_brief?: KnowledgeBrief;
  generation_options?: Record<string, any>;
}

export interface TrendProposalUpdateRequest {
  expected_revision: number;
  title?: string;
  angle?: string;
  knowledge_brief?: KnowledgeBrief;
  generation_options?: Record<string, any>;
}

export interface TrendSubscription {
  id: string;
  project_id: string;
  enabled: boolean;
  platforms: string[];
  source_keys: string[];
  frequency: TrendFrequency;
  timezone: string;
  status: TrendSubscriptionStatus;
  retry_count: number;
  last_run_id?: string | null;
  last_started_at?: string | null;
  last_success_at?: string | null;
  next_run_at?: string | null;
  last_error?: string | null;
  recent_runs: TrendRun[];
  source_health: TrendSourceHealth[];
  created_at: string;
  updated_at: string;
}

export interface KnowledgeClaim {
  id: string;
  statement: string;
  source_refs: string[];
}

export interface KnowledgeBrief {
  audience?: string | null;
  thesis?: string | null;
  viewer_takeaway?: string | null;
  key_claims: KnowledgeClaim[];
  source_refs: string[];
  genre?: string | null;
}

export type TrendProposalStatus = "draft" | "approving" | "task_created" | "queue_failed" | "rejected";

export interface TrendProposal {
  id: string;
  project_id: string;
  trend_item_id: string;
  trend_run_id?: string | null;
  trend_observation_id?: string | null;
  task_id?: string | null;
  revision: number;
  status: TrendProposalStatus;
  title: string;
  angle: string;
  match_reason: string;
  matched_keywords: string[];
  trend_snapshot: Record<string, any>;
  knowledge_brief: KnowledgeBrief;
  generation_options: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface TrendProposalActionResponse {
  proposal: TrendProposal;
  task?: Task | null;
  job?: WorkflowJob | Record<string, any> | null;
  queue_status: "not_requested" | "queued" | "failed";
  queue_error?: string | null;
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
  mode: ProductionMode;
  status: ProjectStatus;
  default_production_settings: Record<string, any>;
  profile: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends Project {
  tasks: Task[];
}

export interface DramaStageState {
  status: string;
  updated_at?: string | null;
  message?: string | null;
}

export interface DramaCharacter {
  id: string;
  bible_id: string;
  name: string;
  description: string;
  appearance_lock: string;
  wardrobe: string;
  voice_id?: string | null;
  reference_asset_id?: string | null;
  prompt_anchor: string;
  continuity_metadata: Record<string, any>;
  approval_status: DramaApprovalStatus;
  approval_note?: string | null;
  approved_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DramaLocation {
  id: string;
  bible_id: string;
  name: string;
  visual_description: string;
  reference_asset_ids: string[];
  prompt_anchor: string;
  continuity_metadata: Record<string, any>;
  approval_status: DramaApprovalStatus;
  approval_note?: string | null;
  approved_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DramaDialogueLine {
  id: string;
  shot_id: string;
  sequence_index: number;
  character_id?: string | null;
  speaker_name: string;
  text: string;
  delivery: string;
  timing_hint: string;
  created_at: string;
  updated_at: string;
}

export interface DramaShot {
  id: string;
  scene_id: string;
  sequence_index: number;
  action: string;
  character_ids: string[];
  characters: string[];
  location_id?: string | null;
  camera: string;
  framing: string;
  movement: string;
  duration_hint: number;
  visual_prompt: string;
  prompt_anchor: string;
  continuity_metadata: Record<string, any>;
  approval_status: DramaApprovalStatus;
  approval_note?: string | null;
  approved_at?: string | null;
  dialogue_lines: DramaDialogueLine[];
  created_at: string;
  updated_at: string;
}

export interface DramaScene {
  id: string;
  episode_id: string;
  sequence_index: number;
  title: string;
  summary: string;
  beat: string;
  location_id?: string | null;
  script_text: string;
  continuity_metadata: Record<string, any>;
  approval_status: DramaApprovalStatus;
  approval_note?: string | null;
  approved_at?: string | null;
  shots: DramaShot[];
  created_at: string;
  updated_at: string;
}

export interface DramaEpisode {
  id: string;
  bible_id: string;
  episode_number: number;
  title: string;
  synopsis: string;
  script_text: string;
  continuity_metadata: Record<string, any>;
  workflow_status: DramaWorkflowStatus;
  approval_status: DramaApprovalStatus;
  approval_note?: string | null;
  checkpoint: Record<string, any>;
  approved_at?: string | null;
  scenes: DramaScene[];
  created_at: string;
  updated_at: string;
}

export interface DramaBible {
  id: string;
  project_id: string;
  source_type: DramaSourceType;
  source_text: string;
  title: string;
  logline: string;
  genre: string;
  tone: string;
  visual_style: string;
  current_stage: DramaStage;
  workflow_status: DramaWorkflowStatus;
  approval_status: DramaApprovalStatus;
  stage_state: Record<DramaStage, DramaStageState>;
  checkpoint: Record<string, any>;
  continuity_rules: Array<Record<string, any>>;
  prop_locks: Array<Record<string, any>>;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface DramaDetail extends DramaBible {
  characters: DramaCharacter[];
  locations: DramaLocation[];
  episodes: DramaEpisode[];
}

export interface DramaPreflightCheck {
  key: string;
  label: string;
  passed: boolean;
  message: string;
}

export interface DramaPreflight {
  drama_id: string;
  ready: boolean;
  blocking: boolean;
  current_stage: DramaStage;
  checks: DramaPreflightCheck[];
}

export interface DramaApprovalResponse {
  drama: DramaDetail;
  preflight: DramaPreflight;
}

export type DramaProductionStage = "media" | "audio" | "composition";

export interface DramaProductionStartRequest {
  episode_id?: string | null;
  content_mode?: DramaContentMode;
  template_id?: string;
  template_params?: Record<string, any>;
  voice_id?: string | null;
  speed?: number;
  bgm_enabled?: boolean;
  bgm_asset_id?: string | null;
  bgm_volume?: number;
  image_workflow_id?: string | null;
  video_workflow_id?: string | null;
}

export interface DramaProductionFinding {
  key: string;
  label: string;
  severity: "info" | "warning" | "blocking";
  passed: boolean;
  message: string;
  shot_id?: string | null;
}

export interface DramaShotProduction {
  shot_id: string;
  source_shot_id: string;
  sequence_index: number;
  status: string;
  media_status: string;
  audio_status: string;
  composition_status: string;
  media_asset_id?: string | null;
  audio_asset_id?: string | null;
  rendered_segment_asset_id?: string | null;
  duration_seconds?: number | null;
  dialogue_line_count: number;
  dialogue_timeline: Array<Record<string, any>>;
  qa: DramaProductionFinding[];
  error_message?: string | null;
}

export interface DramaProductionStatus {
  drama_id: string;
  episode_id: string;
  task_id?: string | null;
  job_id?: string | null;
  status: string;
  progress: number;
  current_stage?: string | null;
  shots: DramaShotProduction[];
  qa_before: DramaProductionFinding[];
  qa_after: DramaProductionFinding[];
  final_video_asset_id?: string | null;
  final_video_url?: string | null;
  cover_asset_id?: string | null;
  cover_url?: string | null;
  subtitle_artifact_ids: string[];
  episode_metadata_artifact_id?: string | null;
  render_manifest_artifact_id?: string | null;
  total_duration_seconds?: number | null;
  error_message?: string | null;
}

export interface Scene {
  id: string;
  task_id: string;
  sequence_index: number;
  narration_text: string;
  visual_prompt: string;
  duration_seconds: number;
  layout_params: Record<string, any>;
  visual_role: VisualRole;
  claim_refs: string[];
  source_refs: string[];
  production_metadata: Record<string, any>;
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
  visual_role?: VisualRole;
  claim_refs?: string[];
  source_refs?: string[];
  production_metadata?: Record<string, any>;
  audio_asset_id?: string | null;
  media_asset_id?: string | null;
}

export interface WorkflowJob {
  id: string;
  task_id: string;
  production_context_snapshot_id: string;
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
  stages?: WorkflowStepRun[];
  artifacts?: WorkflowArtifact[];
}

export interface Task {
  id: string;
  project_id: string;
  title: string;
  description: string;
  editorial_status: string;
  production_status: string;
  generation_settings: Record<string, any>;
  publishing_settings: Record<string, any>;
  detail: Record<string, any> & { type: ProductionMode };
  scenes_count?: number;
  created_at: string;
  updated_at: string;
  latest_job?: WorkflowJob | null;
  current_stage?: string | null;
  current_stage_label?: string | null;
  resume_count?: number;
  last_heartbeat_at?: string | null;
  can_resume?: boolean;
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
  ref_id?: string | null;
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
  visual_role?: VisualRole;
  claim_refs?: string[];
  source_refs?: string[];
  production_metadata?: Record<string, any>;
}

export interface ProductionReadiness {
  task_id: string;
  mode: ProductionMode;
  ready: boolean;
  checks: Array<{ key: string; label: string; status: "pass" | "error"; message: string }>;
}

export type ProductFactSource = "user_input" | "manual_correction" | "json_ld" | "opengraph" | "page_structure";
export type ProductFactCertainty = "user_asserted" | "source_reported" | "uncertain";

export interface ProductFact {
  id: string;
  field: string;
  value: any;
  source_type: ProductFactSource;
  source_ref: string;
  source_url?: string | null;
  certainty: ProductFactCertainty;
  user_confirmed: boolean;
}

export interface ProductClaim {
  id: string;
  text: string;
  claim_type: "selling_point" | "numerical";
  evidence_refs: string[];
  certainty: ProductFactCertainty;
}

export interface ProductTruthSheet {
  product_id: string;
  version: number;
  facts: ProductFact[];
  selling_points: ProductClaim[];
  numerical_claims: ProductClaim[];
  unresolved_fields: string[];
  generated_at?: string | null;
}

export interface ProductAsset {
  id: string;
  product_id: string;
  asset_id?: string | null;
  asset_type: "image" | "video";
  role: string;
  source_kind: string;
  source_url?: string | null;
  alt_text: string;
  sort_order: number;
  metadata_json: Record<string, any>;
  created_at: string;
  asset?: Asset | null;
}

export interface Product {
  id: string;
  title: string;
  brand: string;
  description: string;
  price: string;
  currency: string;
  specifications: Record<string, any>;
  source_url?: string | null;
  source_snapshot: Record<string, any>;
  truth_sheet: ProductTruthSheet;
  status: string;
  assets: ProductAsset[];
  created_at: string;
  updated_at: string;
}

export interface CreativePlanClaim {
  id: string;
  text: string;
  claim_type: "selling_point" | "numerical";
  evidence_refs: string[];
}

export interface CreativeSceneOutline {
  sequence_index: number;
  beat: string;
  visual: string;
  narration: string;
  visual_role: VisualRole;
  claim_refs: string[];
  asset_strategy: "product_asset" | "deterministic_layout" | "generated_context";
}

export interface CreativePlan {
  id: string;
  product_id: string;
  source_plan_id?: string | null;
  status: CreativePlanStatus;
  variant_label: string;
  variant_index: number;
  angle: CreativeAngle;
  hook: string;
  audience: string;
  core_message: string;
  claims: CreativePlanClaim[];
  scene_outline: CreativeSceneOutline[];
  cta: string;
  truth_sheet_version: number;
  fact_snapshot: Record<string, any>;
  selected_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface StructuredScript {
  title: string;
  hook: string;
  narration: string;
  scenes: StructuredSceneScript[];
  knowledge_brief?: KnowledgeBrief;
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
  knowledge_brief?: KnowledgeBrief;
  research_sources?: ResearchSource[];
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
  id: string; job_id: string; task_id: string; step_run_id: string; kind: string;
  relative_path: string; size_bytes: number; sha256: string; source: string;
}
export interface WorkflowStepRun {
  id: string; job_id: string; step_key: string; unit_key: string; attempt: number;
  status: string; validity: string; invalid_reason?: string | null;
  duration_ms?: number | null; error_message?: string | null; warning?: string | null;
  started_at: string; completed_at?: string | null; artifacts: WorkflowArtifact[];
}
export interface WorkflowStageSummary {
  step_key: string; label?: string; status: string; validity: string; duration_ms: number; retry_count: number;
  units: WorkflowStepRun[]; history: WorkflowStepRun[];
}
export interface WorkflowSnapshot { task_id: string; stages: WorkflowStageSummary[]; }
