import {
  Asset,
  AssetBatchResult,
  AccountCheckResponse,
  Project,
  DramaCharacter,
  DramaLocation,
  DramaProp,
  ProjectDetail,
  ProjectTemplate,
  ProjectTemplateUpdate,
  Product,
  ProductionMode,
  ProductionRecipe,
  ProductionReadiness,
  ProviderConfigItem,
  ProviderCreatePayload,
  ImageGenerationTestResult,
  ProviderTestResult,
  ProviderUpdatePayload,
  SystemConfigSummary,
  PublishingJob,
  PlatformMetadata,
  ResearchResponse,
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

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
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
  workflowArtifactUrl: (jobId: string, artifactId: string) =>
    `${BASE_URL}/artifacts/${encodeURIComponent(artifactId)}/download?job_id=${encodeURIComponent(jobId)}`,

  // Projects
  listProjects: (limit = 50, offset = 0) =>
    request<Project[]>(`/projects?limit=${limit}&offset=${offset}`),

  // Trend discovery feed and real public-source collection.
  listTrends: (
    filters: {
      projectId?: string;
      platform?: string;
      freshness?: TrendFreshness;
    } = {},
  ) => {
    const params = new URLSearchParams();
    if (filters.projectId) params.set("project_id", filters.projectId);
    if (filters.platform && filters.platform !== "all")
      params.set("platform", filters.platform);
    if (filters.freshness && filters.freshness !== "all")
      params.set("freshness", filters.freshness);
    const query = params.toString();
    return request<TrendFeedResponse>(`/trends${query ? `?${query}` : ""}`);
  },

  listTrendSources: () => request<TrendSourceCatalog[]>("/trends/sources"),

  listTrendRuns: (limit = 10) =>
    request<TrendRun[]>(
      `/trends/runs?limit=${Math.max(1, Math.min(100, limit))}`,
    ),

  refreshTrends: (
    data: { platforms?: string[]; source_keys?: string[] } = {},
  ) =>
    request<TrendRun>("/trends/refresh", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getTrendPreferences: (projectId: string) =>
    request<TrendPreferences>(
      `/trends/projects/${encodeURIComponent(projectId)}/preferences`,
    ),

  updateTrendPreferences: (
    projectId: string,
    data: TrendPreferencesUpdateRequest,
  ) =>
    request<TrendPreferences>(
      `/trends/projects/${encodeURIComponent(projectId)}/preferences`,
      {
        method: "PATCH",
        body: JSON.stringify(data),
      },
    ),

  listTrendSubscriptions: (projectId?: string) =>
    request<TrendSubscription[]>(
      `/trends/subscriptions${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`,
    ),

  createTrendSubscription: (data: TrendSubscriptionCreateRequest) =>
    request<TrendSubscription>("/trends/subscriptions", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateTrendSubscription: (
    subscriptionId: string,
    data: TrendSubscriptionRequest,
  ) =>
    request<TrendSubscription>(
      `/trends/subscriptions/${encodeURIComponent(subscriptionId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(data),
      },
    ),

  runTrendSubscription: (subscriptionId: string) =>
    request<TrendSubscription>(
      `/trends/subscriptions/${encodeURIComponent(subscriptionId)}/run`,
      { method: "POST" },
    ),

  createTrendProposal: (data: TrendProposalCreateRequest) =>
    request<TrendProposal>("/trends/proposals", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateTrendProposal: (proposalId: string, data: TrendProposalUpdateRequest) =>
    request<TrendProposal>(
      `/trends/proposals/${encodeURIComponent(proposalId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(data),
      },
    ),

  rejectTrendProposal: (proposalId: string, expectedRevision: number) =>
    request<TrendProposal>(
      `/trends/proposals/${encodeURIComponent(proposalId)}/reject`,
      {
        method: "POST",
        body: JSON.stringify({ expected_revision: expectedRevision }),
      },
    ),

  approveTrendProposal: (proposalId: string, expectedRevision: number) =>
    request<TrendProposalActionResponse>(
      `/trends/proposals/${encodeURIComponent(proposalId)}/approve-and-create-task`,
      {
        method: "POST",
        body: JSON.stringify({ expected_revision: expectedRevision }),
      },
    ),

  getProject: (id: string) => request<ProjectDetail>(`/projects/${id}`),

  createProject: (data: Record<string, unknown>) =>
    request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getProjectProduct: (projectId: string) =>
    request<Product>(`/projects/${projectId}/product`),

  putProjectProduct: (projectId: string, data: Record<string, unknown>) =>
    request<Product>(`/projects/${projectId}/product`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  updateProject: (id: string, data: Partial<Project>) =>
    request<Project>(`/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  listDramaCharacters: (projectId: string) =>
    request<DramaCharacter[]>(`/projects/${projectId}/characters`),
  createDramaCharacter: (projectId: string, data: Record<string, unknown>) =>
    request<DramaCharacter>(`/projects/${projectId}/characters`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateDramaCharacter: (
    projectId: string,
    resourceId: string,
    data: Record<string, unknown>,
  ) =>
    request<DramaCharacter>(`/projects/${projectId}/characters/${resourceId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  approveDramaCharacter: (projectId: string, resourceId: string) =>
    request<DramaCharacter>(
      `/projects/${projectId}/characters/${resourceId}/approve`,
      { method: "POST" },
    ),
  deleteDramaCharacter: (projectId: string, resourceId: string) =>
    request<boolean>(`/projects/${projectId}/characters/${resourceId}`, {
      method: "DELETE",
    }),

  listDramaLocations: (projectId: string) =>
    request<DramaLocation[]>(`/projects/${projectId}/locations`),
  createDramaLocation: (projectId: string, data: Record<string, unknown>) =>
    request<DramaLocation>(`/projects/${projectId}/locations`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateDramaLocation: (
    projectId: string,
    resourceId: string,
    data: Record<string, unknown>,
  ) =>
    request<DramaLocation>(`/projects/${projectId}/locations/${resourceId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  approveDramaLocation: (projectId: string, resourceId: string) =>
    request<DramaLocation>(
      `/projects/${projectId}/locations/${resourceId}/approve`,
      { method: "POST" },
    ),
  deleteDramaLocation: (projectId: string, resourceId: string) =>
    request<boolean>(`/projects/${projectId}/locations/${resourceId}`, {
      method: "DELETE",
    }),

  listDramaProps: (projectId: string) =>
    request<DramaProp[]>(`/projects/${projectId}/props`),
  createDramaProp: (projectId: string, data: Record<string, unknown>) =>
    request<DramaProp>(`/projects/${projectId}/props`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateDramaProp: (
    projectId: string,
    resourceId: string,
    data: Record<string, unknown>,
  ) =>
    request<DramaProp>(`/projects/${projectId}/props/${resourceId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  approveDramaProp: (projectId: string, resourceId: string) =>
    request<DramaProp>(`/projects/${projectId}/props/${resourceId}/approve`, {
      method: "POST",
    }),
  deleteDramaProp: (projectId: string, resourceId: string) =>
    request<boolean>(`/projects/${projectId}/props/${resourceId}`, {
      method: "DELETE",
    }),

  getProjectBgm: (projectId: string) =>
    request<Array<{ asset: Asset }>>(
      `/projects/${projectId}/assets?purpose=bgm`,
    ).then((bindings) => bindings.map((binding) => binding.asset)),

  listBgmCandidates: (projectId: string) =>
    request<Asset[]>(`/projects/${projectId}/bgm-candidates`),

  bindProjectAsset: (projectId: string, assetId: string, purpose: string) =>
    request<{ binding_id: string }>(`/projects/${projectId}/assets`, {
      method: "POST",
      body: JSON.stringify({ asset_id: assetId, purpose }),
    }),

  addProjectProductAsset: (
    projectId: string,
    assetId: string,
    role = "gallery",
  ) =>
    request<Record<string, unknown>>(`/projects/${projectId}/product/assets`, {
      method: "POST",
      body: JSON.stringify({ asset_id: assetId, role }),
    }),

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
    return request<TemplateCatalogItem[]>(
      query ? `/templates?${query}` : "/templates",
    );
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
    } = {},
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
      `/projects/${projectId}/tasks${status ? `?status=${status}` : ""}`,
    ),

  createProjectTask: (
    projectId: string,
    data: {
      title: string;
      description?: string;
      detail: Record<string, any> & { type: ProductionMode };
      generation_settings?: Record<string, any>;
      publishing_settings?: Record<string, any>;
    },
  ) =>
    request<Task>(`/projects/${projectId}/tasks`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Tasks Resource & Workflow Actions
  listAllTasks: (limit = 50, offset = 0, productionStatus?: string) =>
    request<Task[]>(
      `/tasks?limit=${limit}&offset=${offset}${productionStatus ? `&production_status=${productionStatus}` : ""}`,
    ),

  getTask: (taskId: string) => request<TaskDetail>(`/tasks/${taskId}`),

  listProductionRecipes: (mode: ProductionMode) =>
    request<ProductionRecipe[]>(`/tasks/recipes?mode=${encodeURIComponent(mode)}`),

  getTaskReadiness: (taskId: string) =>
    request<ProductionReadiness>(`/tasks/${taskId}/readiness`),

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

  approveTask: (taskId: string) =>
    request<TaskDetail>(`/tasks/${taskId}/approve`, { method: "POST" }),

  createWorkflowJob: (taskId: string) =>
    request<WorkflowJob>(`/tasks/${taskId}/jobs`, {
      method: "POST",
    }),

  retrySceneMedia: (taskId: string, sceneId: string) =>
    request<WorkflowJob>(`/tasks/${taskId}/scenes/${sceneId}/retry`, {
      method: "POST",
    }),

  listTaskJobs: (taskId: string) =>
    request<WorkflowJob[]>(`/tasks/${taskId}/jobs`),

  getWorkflowJob: (jobId: string) =>
    request<WorkflowJob>(`/workflow-jobs/${jobId}`),

  retryWorkflowJob: (jobId: string) =>
    request<WorkflowJob>(`/workflow-jobs/${jobId}/retry`, { method: "POST" }),

  cancelWorkflowJob: (jobId: string) =>
    request<WorkflowJob>(`/workflow-jobs/${jobId}/cancel`, { method: "POST" }),

  duplicateTask: (
    taskId: string,
    payload: {
      mode?: "settings_only" | "settings_and_script";
      title?: string;
    } = {},
  ) =>
    request<TaskDetail>(`/tasks/${taskId}/duplicate`, {
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
    options: {
      max_results?: number;
      max_queries?: number;
      search_provider_id?: string | null;
    } = {},
  ) =>
    request<ResearchResponse>("/generation/research", {
      method: "POST",
      body: JSON.stringify({
        topic,
        max_results: options.max_results ?? 5,
        max_queries: options.max_queries ?? 3,
        search_provider_id: options.search_provider_id,
      }),
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

  generateSceneOnlineMaterial: (sceneId: string, promptOverride?: string) =>
    request<Scene>(`/generation/scenes/${sceneId}/online-material`, {
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
        errorMsg =
          errorData?.error?.message ||
          errorData?.detail ||
          errorData?.message ||
          errorMsg;
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
      {
        id: string;
        name: string;
        type: string;
        subfolder?: string;
        file_name: string;
      }[]
    >("/providers/comfyui/workflows"),

  listVoices: (active = false) =>
    request<VoiceInfo[]>(`/providers/voices${active ? "?active=true" : ""}`),

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
      `/publishing/accounts${platform ? `?platform=${platform}` : ""}`,
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

  completeQRAuth: (data: {
    session_id: string;
    account_name: string;
    username?: string;
  }) =>
    request<SocialAccount>("/publishing/auth/qr/complete", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listPublishingJobs: (projectId?: string, status?: string) => {
    const params = new URLSearchParams();
    if (projectId) params.append("project_id", projectId);
    if (status) params.append("status", status);
    const query = params.toString();
    return request<PublishingJob[]>(
      `/publishing/jobs${query ? `?${query}` : ""}`,
    );
  },

  createPublishingJob: (data: {
    project_id: string;
    workflow_job_id: string;
    artifact_id: string;
    account_id: string;
    platform: "douyin";
    title: string;
    description?: string;
    tags?: string[];
    cover_asset_id?: string | null;
    scheduled_at?: string | null;
  }) =>
    request<PublishingJob>("/publishing/jobs", {
      method: "POST",
      body: JSON.stringify(data),
    }),

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
    request<PlatformMetadata>(
      `/generation/tasks/${taskId}/metadata/regenerate`,
      { method: "POST" },
    ),

  resolveUncertainPublishingJob: (
    jobId: string,
    action: "retry" | "acknowledge",
  ) =>
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
