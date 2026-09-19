import {
  Asset,
  AssetBatchResult,
  AccountCheckResponse,
  ContentMode,
  Project,
  ProjectDetail,
  ProjectTemplate,
  ProjectTemplateUpdate,
  Product,
  CreativePlan,
  DramaApprovalResponse,
  DramaBible,
  DramaDetail,
  DramaPreflight,
  DramaProductionStartRequest,
  DramaProductionStatus,
  DramaProductionStage,
  CommercePreflightResponse,
  ProductionMode,
  CreativeAngle,
  ProviderConfigItem,
  ProviderCreatePayload,
  ImageGenerationTestResult,
  KnowledgeBrief,
  ProviderTestResult,
  ProviderUpdatePayload,
  SystemConfigSummary,
  PublishingJob,
  PlatformMetadata,
  ResearchResponse,
  ScheduledPublishConfig,
  Scene,
  SceneCreate,
  ScriptGenerateRequest,
  SocialAccount,
  StructuredScript,
  Task,
  TaskDetail,
  TemplateCatalogItem,
  VerificationRequestItem,
  VoiceInfo,
  WorkflowJob,
  WorkflowSnapshot,
  QRStartResponse,
  QRStatusResponse,
  TrendFeedResponse,
  TrendFreshness,
  TrendPreferences,
  TrendProposal,
  TrendProposalCreateRequest,
  TrendProposalActionResponse,
  TrendProposalUpdateRequest,
  TrendPreferencesUpdateRequest,
  TrendRun,
  TrendSourceCatalog,
  TrendSubscription,
  TrendSubscriptionCreateRequest,
  TrendSubscriptionRequest,
} from "./types";

const BASE_URL = "/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!res.ok) {
    let errorMsg = `HTTP Error ${res.status}`;
    try {
      const errorData = await res.json();
      errorMsg =
        errorData?.error?.message ||
        errorData?.detail ||
        errorData?.message ||
        errorMsg;
    } catch {
      // ignore JSON parse error
    }
    throw new ApiError(errorMsg, res.status);
  }

  const json = await res.json();
  return json.data !== undefined ? json.data : json;
}

export const api = {
  getWorkflow: (taskId: string) => request<WorkflowSnapshot>(`/tasks/${taskId}/workflow`),
  retryWorkflowStep: (taskId: string, step: string, unitKey?: string) => request<WorkflowJob>(`/tasks/${taskId}/steps/${step}/retry`, { method: "POST", body: JSON.stringify({ unit_key: unitKey }) }),
  workflowArtifactUrl: (taskId: string, artifactId: string) => `${BASE_URL}/artifacts/${encodeURIComponent(artifactId)}/download?task_id=${encodeURIComponent(taskId)}`,

  // Projects
  listProjects: (limit = 50, offset = 0) =>
    request<Project[]>(`/projects?limit=${limit}&offset=${offset}`),

  // Trend discovery feed and real public-source collection.
  listTrends: (filters: {
    projectId?: string;
    platform?: string;
    freshness?: TrendFreshness;
  } = {}) => {
    const params = new URLSearchParams();
    if (filters.projectId) params.set("project_id", filters.projectId);
    if (filters.platform && filters.platform !== "all") params.set("platform", filters.platform);
    if (filters.freshness && filters.freshness !== "all") params.set("freshness", filters.freshness);
    const query = params.toString();
    return request<TrendFeedResponse>(`/trends${query ? `?${query}` : ""}`);
  },

  listTrendSources: () => request<TrendSourceCatalog[]>("/trends/sources"),

  listTrendRuns: (limit = 10) =>
    request<TrendRun[]>(`/trends/runs?limit=${Math.max(1, Math.min(100, limit))}`),

  refreshTrends: (data: { platforms?: string[]; source_keys?: string[] } = {}) =>
    request<TrendRun>("/trends/refresh", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getTrendPreferences: (projectId: string) =>
    request<TrendPreferences>(`/trends/projects/${encodeURIComponent(projectId)}/preferences`),

  updateTrendPreferences: (
    projectId: string,
    data: TrendPreferencesUpdateRequest,
  ) =>
    request<TrendPreferences>(`/trends/projects/${encodeURIComponent(projectId)}/preferences`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  listTrendSubscriptions: (projectId?: string) =>
    request<TrendSubscription[]>(`/trends/subscriptions${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`),

  createTrendSubscription: (data: TrendSubscriptionCreateRequest) =>
    request<TrendSubscription>("/trends/subscriptions", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateTrendSubscription: (subscriptionId: string, data: TrendSubscriptionRequest) =>
    request<TrendSubscription>(`/trends/subscriptions/${encodeURIComponent(subscriptionId)}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  runTrendSubscription: (subscriptionId: string) =>
    request<TrendSubscription>(`/trends/subscriptions/${encodeURIComponent(subscriptionId)}/run`, { method: "POST" }),

  createTrendProposal: (data: TrendProposalCreateRequest) =>
    request<TrendProposal>("/trends/proposals", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateTrendProposal: (
    proposalId: string,
    data: TrendProposalUpdateRequest,
  ) =>
    request<TrendProposal>(`/trends/proposals/${encodeURIComponent(proposalId)}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  rejectTrendProposal: (proposalId: string, expectedRevision: number) =>
    request<TrendProposal>(`/trends/proposals/${encodeURIComponent(proposalId)}/reject`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: expectedRevision }),
    }),

  approveTrendProposal: (
    proposalId: string,
    expectedRevision: number,
  ) =>
    request<TrendProposalActionResponse>(`/trends/proposals/${encodeURIComponent(proposalId)}/approve-and-create-task`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: expectedRevision }),
    }),

  approveAndRunTrendProposal: (
    proposalId: string,
    expectedRevision: number,
  ) =>
    request<TrendProposalActionResponse>(`/trends/proposals/${encodeURIComponent(proposalId)}/approve-and-run`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: expectedRevision }),
    }),

  getProject: (id: string) => request<ProjectDetail>(`/projects/${id}`),

  // Drama production: approved storyboard -> per-shot media/audio -> episode video.
  listDramas: (projectId: string) =>
    request<DramaBible[]>(`/projects/${encodeURIComponent(projectId)}/dramas`),

  createDrama: (
    projectId: string,
    payload: {
      source_type: "idea" | "script";
      title: string;
      source_text: string;
      logline?: string;
      genre?: string;
      tone?: string;
      visual_style?: string;
      continuity_rules?: Array<Record<string, any>>;
      prop_locks?: Array<Record<string, any>>;
    },
  ) =>
    request<DramaDetail>(`/projects/${encodeURIComponent(projectId)}/dramas`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getDrama: (dramaId: string) => request<DramaDetail>(`/dramas/${encodeURIComponent(dramaId)}`),

  planDrama: (dramaId: string, regenerate = false) =>
    request<DramaDetail>(`/dramas/${encodeURIComponent(dramaId)}/plan`, {
      method: "POST",
      body: JSON.stringify({ regenerate }),
    }),

  getDramaPreflight: (dramaId: string) =>
    request<DramaPreflight>(`/dramas/${encodeURIComponent(dramaId)}/preflight`),

  updateDrama: (dramaId: string, payload: Partial<DramaDetail>) =>
    request<DramaDetail>(`/dramas/${encodeURIComponent(dramaId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  updateDramaCharacter: (dramaId: string, characterId: string, payload: Record<string, any>) =>
    request<DramaDetail>(`/dramas/${encodeURIComponent(dramaId)}/characters/${encodeURIComponent(characterId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  approveDramaCharacter: (dramaId: string, characterId: string) =>
    request<DramaDetail>(`/dramas/${encodeURIComponent(dramaId)}/characters/${encodeURIComponent(characterId)}/approve`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  updateDramaLocation: (dramaId: string, locationId: string, payload: Record<string, any>) =>
    request<DramaDetail>(`/dramas/${encodeURIComponent(dramaId)}/locations/${encodeURIComponent(locationId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  approveDramaLocation: (dramaId: string, locationId: string) =>
    request<DramaDetail>(`/dramas/${encodeURIComponent(dramaId)}/locations/${encodeURIComponent(locationId)}/approve`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  updateDramaEpisode: (dramaId: string, episodeId: string, payload: Record<string, any>) =>
    request<DramaDetail>(`/dramas/${encodeURIComponent(dramaId)}/episodes/${encodeURIComponent(episodeId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  approveDramaEpisode: (dramaId: string, episodeId: string) =>
    request<DramaDetail>(`/dramas/${encodeURIComponent(dramaId)}/episodes/${encodeURIComponent(episodeId)}/approve`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  updateDramaScene: (dramaId: string, sceneId: string, payload: Record<string, any>) =>
    request<DramaDetail>(`/dramas/${encodeURIComponent(dramaId)}/scenes/${encodeURIComponent(sceneId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  approveDramaScene: (dramaId: string, sceneId: string) =>
    request<DramaDetail>(`/dramas/${encodeURIComponent(dramaId)}/scenes/${encodeURIComponent(sceneId)}/approve`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  updateDramaShot: (dramaId: string, shotId: string, payload: Record<string, any>) =>
    request<DramaDetail>(`/dramas/${encodeURIComponent(dramaId)}/shots/${encodeURIComponent(shotId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  approveDramaShot: (dramaId: string, shotId: string) =>
    request<DramaDetail>(`/dramas/${encodeURIComponent(dramaId)}/shots/${encodeURIComponent(shotId)}/approve`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  approveDramaStoryboard: (dramaId: string) =>
    request<DramaApprovalResponse>(`/dramas/${encodeURIComponent(dramaId)}/approve-storyboard`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  getDramaProduction: (dramaId: string, episodeId?: string) =>
    request<DramaProductionStatus>(
      `/dramas/${encodeURIComponent(dramaId)}/production${episodeId ? `?episode_id=${encodeURIComponent(episodeId)}` : ""}`,
    ),

  startDramaProduction: (dramaId: string, payload: DramaProductionStartRequest = {}) =>
    request<DramaProductionStatus>(`/dramas/${encodeURIComponent(dramaId)}/production/start`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  resumeDramaProduction: (dramaId: string) =>
    request<DramaProductionStatus>(`/dramas/${encodeURIComponent(dramaId)}/production/resume`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  retryDramaShot: (dramaId: string, shotId: string, stage: DramaProductionStage = "media") =>
    request<DramaProductionStatus>(
      `/dramas/${encodeURIComponent(dramaId)}/production/shots/${encodeURIComponent(shotId)}/retry`,
      {
        method: "POST",
        body: JSON.stringify({ stage }),
      },
    ),

  createProject: (data: {
    name: string;
    description?: string;
    aspect_ratio?: string;
    primary_production_mode?: ProductionMode;
    default_voice_id?: string;
    bgm_asset_id?: string | null;
    settings?: Record<string, any>;
  }) =>
    request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Product Library
  listProducts: (limit = 50, offset = 0) =>
    request<Product[]>(`/products?limit=${limit}&offset=${offset}`),

  getProduct: (productId: string) =>
    request<Product>(`/products/${encodeURIComponent(productId)}`),

  listCreativePlans: (productId: string) =>
    request<CreativePlan[]>(`/products/${encodeURIComponent(productId)}/creative-plans`),

  generateCreativePlans: (productId: string, data: { count?: number; audience?: string; objective?: string } = {}) =>
    request<CreativePlan[]>(`/products/${encodeURIComponent(productId)}/creative-plans`, {
      method: "POST",
      body: JSON.stringify({ count: 3, ...data }),
    }),

  selectCreativePlan: (productId: string, planId: string) =>
    request<CreativePlan>(`/products/${encodeURIComponent(productId)}/creative-plans/${encodeURIComponent(planId)}/select`, {
      method: "POST",
    }),

  duplicateCreativePlan: (productId: string, planId: string, variant_label?: string) =>
    request<CreativePlan>(`/products/${encodeURIComponent(productId)}/creative-plans/${encodeURIComponent(planId)}/duplicate`, {
      method: "POST",
      body: JSON.stringify({ variant_label }),
    }),

  confirmCreativePlanFacts: (productId: string, planId: string) =>
    request<CreativePlan>(`/products/${encodeURIComponent(productId)}/creative-plans/${encodeURIComponent(planId)}/confirm-facts`, {
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    }),

  createProduct: (data: {
    title: string;
    brand?: string;
    description?: string;
    price?: string;
    currency?: string;
    specifications?: Record<string, any>;
    source_url?: string | null;
    selling_points?: Array<{ text: string; claim_type?: "selling_point" | "numerical"; evidence_refs?: string[] }>;
  }) =>
    request<Product>("/products", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  importProduct: (url: string) =>
    request<Product>("/products/import", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  updateProduct: (productId: string, data: Partial<Pick<Product, "title" | "brand" | "description" | "price" | "currency" | "specifications" | "source_url">> & { selling_points?: Array<{ text: string; claim_type?: "selling_point" | "numerical"; evidence_refs?: string[] }> }) =>
    request<Product>(`/products/${encodeURIComponent(productId)}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  uploadProductAsset: async (productId: string, file: File, assetType: "image" | "video", role = "gallery") => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("asset_type", assetType);
    formData.append("role", role);
    const res = await fetch(`${BASE_URL}/products/${encodeURIComponent(productId)}/assets`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      let message = `HTTP Error ${res.status}`;
      try {
        const data = await res.json();
        message = data?.error?.message || data?.detail || message;
      } catch {
        // Keep the HTTP fallback.
      }
      throw new ApiError(message, res.status);
    }
    const json = await res.json();
    return (json.data !== undefined ? json.data : json) as Product;
  },

  deleteProduct: (productId: string) =>
    request<boolean>(`/products/${encodeURIComponent(productId)}`, { method: "DELETE" }),

  deleteProductAsset: (productId: string, productAssetId: string) =>
    request<boolean>(`/products/${encodeURIComponent(productId)}/assets/${encodeURIComponent(productAssetId)}`, { method: "DELETE" }),

  updateProject: (id: string, data: Partial<Project>) =>
    request<Project>(`/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getProjectBgm: (projectId: string) =>
    request<Asset[]>(`/projects/${projectId}/bgm`),

  deleteProject: (id: string) =>
    request<boolean>(`/projects/${id}`, {
      method: "DELETE",
    }),

  // Project Template (1:1)
  getProjectTemplate: (projectId: string) =>
    request<ProjectTemplate>(`/projects/${projectId}/template`),

  updateProjectTemplate: (projectId: string, data: ProjectTemplateUpdate) =>
    request<ProjectTemplate>(`/projects/${projectId}/template`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Bundled template catalog across multiple aspect ratios and content modes
  listTemplates: (aspect_ratio?: string, content_mode?: string) => {
    const params = new URLSearchParams();
    if (aspect_ratio) params.set("aspect_ratio", aspect_ratio);
    if (content_mode) params.set("content_mode", content_mode);
    const query = params.toString();
    return request<TemplateCatalogItem[]>(query ? `/templates?${query}` : "/templates");
  },

  previewTemplate: (
    templateId: string,
    data: {
      title?: string;
      text?: string;
      image_asset_id?: string | null;
      video_asset_id?: string | null;
      params?: Record<string, any>;
      custom_css?: string | null;
    } = {}
  ) =>
    request<{
      template_id: string;
      width: number;
      height: number;
      preview_url: string;
    }>(`/templates/${encodeURIComponent(templateId)}/preview`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Project Tasks (1:N)
  listProjectTasks: (projectId: string, status?: string) =>
    request<Task[]>(
      `/projects/${projectId}/tasks${status ? `?status=${status}` : ""}`
    ),

  createProjectTask: (
    projectId: string,
    data: {
      title: string;
      description?: string;
      job_type?: string;
      production_mode?: ProductionMode;
      product_id?: string | null;
      creative_plan_id?: string | null;
      creative_angle?: CreativeAngle | string | null;
      knowledge_brief?: KnowledgeBrief;
      input_payload?: Record<string, any>;
      template_id?: string;
      bgm_asset_id?: string | null;
      bgm_enabled?: boolean;
      bgm_volume?: number;
      voice_id?: string | null;
      speed?: number;
      content_mode?: ContentMode;
      material_provider_id?: string | null;
      template_params?: Record<string, any>;
      source_asset_id?: string | null;
      enable_research?: boolean;
      search_provider_id?: string | null;
      research_max_queries?: number;
      research_max_results?: number;
      image_workflow_id?: string | null;
      video_workflow_id?: string | null;
      target_scene_count?: number;
      scheduled_publish?: ScheduledPublishConfig | null;
    }
  ) =>
    request<Task>(`/projects/${projectId}/tasks`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Tasks Resource & Workflow Actions
  listAllTasks: (limit = 50, offset = 0, status?: string) =>
    request<Task[]>(
      `/tasks?limit=${limit}&offset=${offset}${status ? `&status=${status}` : ""}`
    ),

  getTask: (taskId: string) => request<TaskDetail>(`/tasks/${taskId}`),

  getCommercePreflight: (taskId: string, requireMedia = false) =>
    request<CommercePreflightResponse>(
      `/tasks/${taskId}/commerce-preflight?require_media=${requireMedia ? "true" : "false"}`,
      { method: "POST" },
    ),

  getTaskResearch: (taskId: string) =>
    request<ResearchResponse>(`/tasks/${taskId}/research`),

  updateTask: (taskId: string, data: Partial<Task>) =>
    request<TaskDetail>(`/tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  deleteTask: (taskId: string) =>
    request<boolean>(`/tasks/${taskId}`, {
      method: "DELETE",
    }),

  generateTaskVideo: (taskId: string) =>
    request<WorkflowJob>(`/tasks/${taskId}/generate`, {
      method: "POST",
    }),

  cancelTaskGeneration: (taskId: string) =>
    request<boolean>(`/tasks/${taskId}/cancel`, {
      method: "POST",
    }),

  cancelScheduledPublish: (taskId: string) =>
    request<boolean>(`/tasks/${taskId}/scheduled-publish/cancel`, {
      method: "POST",
    }),

  retryTaskGeneration: (taskId: string) =>
    request<WorkflowJob>(`/tasks/${taskId}/retry`, {
      method: "POST",
    }),

  duplicateTask: (
    taskId: string,
    payload: { mode?: "settings_only" | "settings_and_script"; title?: string } = {}
  ) =>
    request<TaskDetail>(`/tasks/${taskId}/duplicate`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  rerenderTask: (
    taskId: string,
    payload: {
      template_id?: string;
      template_params?: Record<string, any>;
      bgm_enabled?: boolean | null;
      bgm_asset_id?: string | null;
      bgm_volume?: number | null;
    } = {}
  ) =>
    request<{ task_id: string; job: WorkflowJob }>(`/tasks/${taskId}/rerender`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  resumeTaskGeneration: (taskId: string, jobId?: string) =>
    request<WorkflowJob>(`/tasks/${taskId}/resume`, {
      method: "POST",
      body: JSON.stringify(jobId ? { job_id: jobId } : {}),
    }),

  composeTaskVideo: (taskId: string) =>
    request<Asset>(`/tasks/${taskId}/compose`, {
      method: "POST",
    }),

  publishTaskVideo: (
    taskId: string,
    payload: {
    account_id?: string;
    title?: string;
    description?: string;
    tags?: string[];
    cover_asset_id?: string | null;
    } = {}
  ) =>
    request<PublishingJob>(`/tasks/${taskId}/publish`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  scheduleTaskVideo: (
    taskId: string,
    payload: {
      scheduled_at: string;
      account_id?: string;
      title?: string;
      description?: string;
      tags?: string[];
      cover_asset_id?: string | null;
    }
  ) =>
    request<PublishingJob>(`/tasks/${taskId}/schedule`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  batchUpdateTaskScenes: (taskId: string, scenes: SceneCreate[]) =>
    request<Scene[]>(`/tasks/${taskId}/scenes`, {
      method: "PUT",
      body: JSON.stringify({ scenes }),
    }),

  // AI Content Generation
  researchTopic: (
    topic: string,
    options: { max_results?: number; max_queries?: number; search_provider_id?: string | null } = {}
  ) =>
    request<ResearchResponse>("/generation/research", {
      method: "POST",
      body: JSON.stringify({ topic, max_results: options.max_results ?? 5, max_queries: options.max_queries ?? 3, search_provider_id: options.search_provider_id }),
    }),

  researchTask: (taskId: string) =>
    request<ResearchResponse>(`/generation/tasks/${taskId}/research`, {
      method: "POST",
    }),

  generateScript: (payload: ScriptGenerateRequest) =>
    request<StructuredScript>("/generation/script", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  applyScriptToTask: (taskId: string, script: StructuredScript) =>
    request<TaskDetail>(`/generation/tasks/${taskId}/apply-script`, {
      method: "POST",
      body: JSON.stringify(script),
    }),

  generateSceneTTS: (sceneId: string, voiceId?: string, speed?: number) =>
    request<Scene>(`/generation/scenes/${sceneId}/tts`, {
      method: "POST",
      body: JSON.stringify({ voice_id: voiceId, speed }),
    }),

  generateSceneImage: (sceneId: string, promptOverride?: string) =>
    request<Scene>(`/generation/scenes/${sceneId}/image`, {
      method: "POST",
      body: JSON.stringify({ prompt_override: promptOverride }),
    }),

  generateSceneVideo: (sceneId: string, promptOverride?: string) =>
    request<Scene>(`/generation/scenes/${sceneId}/video`, {
      method: "POST",
      body: JSON.stringify({ prompt_override: promptOverride }),
    }),

  // Assets
  listAssets: (projectId?: string, assetType?: string) => {
    const params = new URLSearchParams();
    if (projectId) params.append("project_id", projectId);
    if (assetType) params.append("asset_type", assetType);
    const query = params.toString();
    return request<Asset[]>(`/assets${query ? `?${query}` : ""}`);
  },

  uploadAsset: async (file: File, assetType: string, projectId?: string) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("asset_type", assetType);
    if (projectId) formData.append("project_id", projectId);

    const res = await fetch(`${BASE_URL}/assets/upload`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) throw new Error("Failed to upload asset");
    const json = await res.json();
    return json.data as Asset;
  },

  deleteAsset: (id: string) =>
    request<boolean>(`/assets/${id}`, {
      method: "DELETE",
    }),

  batchDeleteAssets: (assetIds: string[]) =>
    request<AssetBatchResult>("/assets/batch/delete", {
      method: "POST",
      body: JSON.stringify({ asset_ids: assetIds }),
    }),

  batchTagAssets: (assetIds: string[], tags: string[]) =>
    request<AssetBatchResult>("/assets/batch/tags", {
      method: "POST",
      body: JSON.stringify({ asset_ids: assetIds, tags }),
    }),

  downloadAssets: async (assetIds: string[]): Promise<Blob> => {
    const res = await fetch(`${BASE_URL}/assets/batch/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asset_ids: assetIds }),
    });
    if (!res.ok) {
      let errorMsg = `HTTP Error ${res.status}`;
      try {
        const errorData = await res.json();
        errorMsg = errorData?.error?.message || errorData?.detail || errorData?.message || errorMsg;
      } catch {
        // Ignore non-JSON error responses.
      }
      throw new ApiError(errorMsg, res.status);
    }
    return res.blob();
  },

  // Providers & Settings (Unified SQLite Management)
  listProviders: (type?: string) =>
    request<ProviderConfigItem[]>(`/providers${type ? `?type=${type}` : ""}`),

  createProvider: (data: ProviderCreatePayload) =>
    request<ProviderConfigItem>("/providers", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateProvider: (id: string, data: ProviderUpdatePayload) =>
    request<ProviderConfigItem>(`/providers/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteProvider: (id: string) =>
    request<boolean>(`/providers/${id}`, {
      method: "DELETE",
    }),

  testProviderConnection: (data: {
    provider_id?: string;
    provider_type?: string;
    provider_name?: string;
    config?: Record<string, any>;
    credentials?: Record<string, any>;
    test_payload?: Record<string, any>;
  }) =>
    request<ProviderTestResult>("/providers/test", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  testImageGeneration: (data: {
    provider_id?: string;
    provider_name?: string;
    config?: Record<string, any>;
    credentials?: Record<string, any>;
    prompt: string;
    aspect_ratio?: "1:1" | "16:9" | "9:16";
    style_preset?: string;
  }) =>
    request<ImageGenerationTestResult>("/providers/image/test-generate", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getSystemConfigSummary: () =>
    request<SystemConfigSummary>("/providers/summary"),

  listComfyUIWorkflows: () =>
    request<
      { id: string; name: string; type: string; subfolder?: string; file_name: string }[]
    >("/providers/comfyui/workflows"),

  listVoices: (active = false) => request<VoiceInfo[]>(`/providers/voices${active ? "?active=true" : ""}`),

  testVoice: async (
    voiceId: string,
    text?: string,
    providerId?: string,
    speedRatio?: number,
  ): Promise<Blob> => {
    const res = await fetch(`${BASE_URL}/providers/voices/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        voice_id: voiceId,
        text: text || undefined,
        provider_id: providerId || undefined,
        speed_ratio: speedRatio,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err?.detail || err?.error?.message || "语音试听合成失败");
    }
    return await res.blob();
  },

  // Publishing
  listAccounts: (platform?: string) =>
    request<SocialAccount[]>(
      `/publishing/accounts${platform ? `?platform=${platform}` : ""}`
    ),

  deleteAccount: (accountId: string) =>
    request<boolean>(`/publishing/accounts/${accountId}`, {
      method: "DELETE",
    }),

  checkAccountStatus: (accountId: string) =>
    request<AccountCheckResponse>(`/publishing/accounts/${accountId}/check`, {
      method: "POST",
    }),

  // Interactive QR Code Login
  startQRAuth: (platform = "douyin", headless = true) =>
    request<QRStartResponse>("/publishing/auth/qr/start", {
      method: "POST",
      body: JSON.stringify({ platform, headless }),
    }),

  getQRAuthStatus: (sessionId: string) =>
    request<QRStatusResponse>(`/publishing/auth/qr/status/${sessionId}`),

  completeQRAuth: (data: { session_id: string; account_name: string; username?: string }) =>
    request<SocialAccount>("/publishing/auth/qr/complete", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listPublishingJobs: (projectId?: string, status?: string) => {
    const params = new URLSearchParams();
    if (projectId) params.append("project_id", projectId);
    if (status) params.append("status", status);
    const query = params.toString();
    return request<PublishingJob[]>(`/publishing/jobs${query ? `?${query}` : ""}`);
  },

  executePublishingJob: (jobId: string) =>
    request<PublishingJob>(`/publishing/jobs/${jobId}/publish`, {
      method: "POST",
    }),

  retryPublishingJob: (jobId: string) =>
    request<PublishingJob>(`/publishing/jobs/${jobId}/retry`, {
      method: "POST",
    }),

  confirmMissedPublishingJob: (jobId: string) =>
    request<PublishingJob>(`/publishing/jobs/${jobId}/confirm-missed`, {
      method: "POST",
    }),

  cancelPublishingJob: (jobId: string) =>
    request<PublishingJob>(`/publishing/jobs/${jobId}/cancel`, {
      method: "POST",
    }),

  deletePublishingJob: (jobId: string) =>
    request<boolean>(`/publishing/jobs/${jobId}`, { method: "DELETE" }),

  regenerateTaskMetadata: (taskId: string) =>
    request<PlatformMetadata>(`/generation/tasks/${taskId}/metadata/regenerate`, { method: "POST" }),

  resolveUncertainPublishingJob: (jobId: string, action: "retry" | "acknowledge") =>
    request<PublishingJob>(`/publishing/jobs/${jobId}/resolve-uncertain`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),

  // Interactive Verification Requests (SMS / 2FA)
  getPendingVerifications: () =>
    request<VerificationRequestItem[]>("/publishing/verification/pending"),

  submitVerificationCode: (requestId: string, code: string) =>
    request<boolean>("/publishing/verification/submit", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId, code }),
    }),

  cancelVerification: (requestId: string) =>
    request<boolean>("/publishing/verification/cancel", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId }),
    }),
};
