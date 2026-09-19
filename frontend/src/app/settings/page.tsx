"use client";

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import {
  ProviderConfigItem,
  ProviderCreatePayload,
  ProviderTestResult,
  ProviderUpdatePayload,
  SystemConfigSummary,
} from "@/lib/types";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-shell";
import { StatusBadge } from "@/components/ui/status-badge";
import { Select } from "@/components/ui/field";
import { IconButton } from "@/components/ui/icon-button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { STYLE_PRESET_OPTIONS } from "@/lib/ui-constants";
import {
  Key,
  Trash2,
  CheckCircle2,
  Bot,
  Search,
  Volume2,
  Radio,
  ExternalLink,
  AlertCircle,
  Image as ImageIcon,
  Video as VideoIcon,
  Loader2,
  Share2,
  Star,
  Play,
  StopCircle,
  Check,
  ShieldAlert,
  Eye,
  EyeOff,
  Database,
  QrCode,
  Smartphone,
  RefreshCw,
  ShieldCheck,
  RotateCcw,
  Copy,
  HardDrive,
  Cpu,
} from "lucide-react";

interface CustomFieldDef {
  key: string;
  label: string;
  type?: "text" | "number" | "select";
  placeholder?: string;
  defaultValue?: any;
  options?: Array<{ label: string; value: string }>;
  description?: string;
  required?: boolean;
}

interface PresetOption {
  type: string;
  name: string;
  display: string;
  defaultBaseUrl?: string;
  defaultModel?: string;
  defaultWorkflow?: string;
  keyUrl?: string;
  hint?: string;
  hasBaseUrl?: boolean;
  hasModel?: boolean;
  hasApiKey?: boolean;
  hasWorkflow?: boolean;
  modelPlaceholder?: string;
  baseUrlPlaceholder?: string;
  keyPlaceholder?: string;
  customFields?: CustomFieldDef[];
}

const PRESET_OPTIONS: Record<string, PresetOption[]> = {
  llm: [
    {
      type: "llm",
      name: "deepseek",
       display: "DeepSeek V4 Flash",
       defaultBaseUrl: "https://api.deepseek.com",
       defaultModel: "deepseek-v4-flash",
       keyUrl: "https://platform.deepseek.com/api_keys",
       hint: "推荐：DeepSeek 最新通用模型，适合短视频剧本编排与结构化分镜拆解。",
      hasBaseUrl: true,
      hasModel: true,
      hasApiKey: true,
      baseUrlPlaceholder: "https://api.deepseek.com",
       modelPlaceholder: "deepseek-v4-flash",
    },
    {
      type: "llm",
      name: "openai",
       display: "OpenAI GPT-5.6 Luna",
       defaultBaseUrl: "https://api.openai.com/v1",
       defaultModel: "gpt-5.6-luna",
      keyUrl: "https://platform.openai.com/api-keys",
       hint: "OpenAI 当前面向成本敏感、高频调用场景的通用模型。",
      hasBaseUrl: true,
      hasModel: true,
      hasApiKey: true,
      baseUrlPlaceholder: "https://api.openai.com/v1",
       modelPlaceholder: "gpt-5.6-luna",
    },
    {
      type: "llm",
      name: "claude",
       display: "Claude Sonnet 5",
       defaultBaseUrl: "https://api.anthropic.com/v1",
       defaultModel: "claude-sonnet-5",
       keyUrl: "https://console.anthropic.com/settings/keys",
       hint: "通过 Anthropic 原生 Messages API 调用，适合长文本理解与精细化叙事。",
      hasBaseUrl: true,
      hasModel: true,
      hasApiKey: true,
      baseUrlPlaceholder: "https://api.anthropic.com/v1",
       modelPlaceholder: "claude-sonnet-5",
    },
    {
      type: "llm",
      name: "cloudflare",
      display: "Cloudflare Workers AI",
      defaultBaseUrl: "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
       defaultModel: "@cf/openai/gpt-oss-120b",
      keyUrl: "https://dash.cloudflare.com/profile/api-tokens",
       hint: "Cloudflare Workers AI 生产级通用高推理模型；请将 Base URL 中的 account_id 替换为真实值。",
      hasBaseUrl: true,
      hasModel: true,
      hasApiKey: true,
      baseUrlPlaceholder: "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
       modelPlaceholder: "@cf/openai/gpt-oss-120b",
    },
    {
      type: "llm",
      name: "ollama",
      display: "Ollama 本地模型",
      defaultBaseUrl: "http://127.0.0.1:11434/v1",
       defaultModel: "qwen3:8b",
      hint: "使用本机 Ollama 模型，无需云端 LLM API Key。",
      hasBaseUrl: true,
      hasModel: true,
      hasApiKey: false,
      baseUrlPlaceholder: "http://127.0.0.1:11434/v1",
       modelPlaceholder: "qwen3:8b",
    },
    {
      type: "llm",
       name: "custom",
       display: "自定义 OpenAI 兼容接口",
       defaultBaseUrl: "https://your-api-endpoint.com/v1",
       hint: "兼容任何遵循 OpenAI 规范的第三方中转网关或自建聚合 API 端点。",
      hasBaseUrl: true,
      hasModel: true,
      hasApiKey: true,
      baseUrlPlaceholder: "https://your-api-endpoint.com/v1",
       modelPlaceholder: "请输入供应商支持的模型 ID",
    },
  ],
  search: [
    {
      type: "search",
      name: "tavily",
      display: "Tavily AI Search",
      keyUrl: "https://app.tavily.com/home",
      hint: "专为 AI Agent 打造的深度事实搜索引擎，用于热点调研与事实验证。",
      hasBaseUrl: false,
      hasModel: false,
      hasApiKey: true,
    },
  ],
  image: [
    {
      type: "image",
      name: "comfyui",
      display: "ComfyUI 本地工作流",
      defaultBaseUrl: "http://127.0.0.1:8188",
      defaultWorkflow: "image/image_flux.json",
      hint: "连接本地 ComfyUI 实例，支持 Flux、SDXL 等多种生图工作流。",
      hasBaseUrl: true,
      hasModel: false,
      hasApiKey: false,
      hasWorkflow: true,
      baseUrlPlaceholder: "http://127.0.0.1:8188",
    },
    {
      type: "image",
      name: "volcengine",
      display: "火山方舟 Seedream",
      defaultBaseUrl: "https://ark.cn-beijing.volces.com/api/v3",
      defaultModel: "doubao-seedream-5-0-260128",
      keyUrl: "https://console.volcengine.com/ark",
      hint: "通过火山方舟 Seedream 生成分镜图片，模型和尺寸可按账号权限调整。",
      hasBaseUrl: true,
      hasModel: true,
      hasApiKey: true,
      baseUrlPlaceholder: "https://ark.cn-beijing.volces.com/api/v3",
      modelPlaceholder: "doubao-seedream-5-0-260128",
    },
  ],
  video: [
    {
      type: "video",
      name: "comfyui",
      display: "ComfyUI 视频工作流",
      defaultBaseUrl: "http://127.0.0.1:8188",
      defaultWorkflow: "video/video_wan2.1_fusionx.json",
      hint: "调用本地 ComfyUI 执行 Wan 2.1、CogVideoX 等文生视频与图生视频工作流。",
      hasBaseUrl: true,
      hasModel: false,
      hasApiKey: false,
      hasWorkflow: true,
      baseUrlPlaceholder: "http://127.0.0.1:8188",
    },
    {
      type: "video",
      name: "volcengine",
      display: "火山方舟 Seedance",
      defaultBaseUrl: "https://ark.cn-beijing.volces.com/api/v3",
      defaultModel: "doubao-seedance-2-0-260128",
      keyUrl: "https://console.volcengine.com/ark",
      hint: "通过火山方舟 Seedance 创建异步视频任务，生成音频默认关闭并由独立语音合成负责旁白。",
      hasBaseUrl: true,
      hasModel: true,
      hasApiKey: true,
      baseUrlPlaceholder: "https://ark.cn-beijing.volces.com/api/v3",
      modelPlaceholder: "doubao-seedance-2-0-260128",
    },
  ],
  material: [
    {
      type: "material",
      name: "pexels",
      display: "Pexels 素材库视频",
      keyUrl: "https://www.pexels.com/api/",
      hint: "按分镜检索词获取可商用实拍视频，并在导入后保留作者与来源署名。",
      hasBaseUrl: false,
      hasModel: false,
      hasApiKey: true,
      customFields: [
        {
          key: "locale",
          label: "搜索语言",
          type: "select",
          defaultValue: "zh-CN",
          options: [
            { label: "中文 (zh-CN)", value: "zh-CN" },
            { label: "English (en-US)", value: "en-US" },
            { label: "日本語 (ja-JP)", value: "ja-JP" },
          ],
        },
        {
          key: "min_short_edge",
          label: "最低短边清晰度",
          type: "select",
          defaultValue: "720",
          options: [
            { label: "480p", value: "480" },
            { label: "720p", value: "720" },
            { label: "1080p", value: "1080" },
          ],
        },
      ],
    },
  ],
  tts: [
    {
      type: "tts",
      name: "edge_tts",
      display: "Microsoft Edge-TTS",
      hint: "系统内置微软神经网络多语种配音引擎，零成本、免 API Key 即开即用。",
      hasBaseUrl: false,
      hasModel: false,
      hasApiKey: false,
    },
    {
      type: "tts",
      name: "volcengine",
      display: "火山引擎 豆包语音",
      defaultBaseUrl: "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
      keyUrl: "https://console.volcengine.com/speech/service/8",
      hint: "使用豆包语音 V3 HTTP Chunked 合成旁白；需与火山控制台授权的 Resource ID 保持匹配。",
      hasBaseUrl: true,
      hasModel: false,
      hasApiKey: true,
      baseUrlPlaceholder: "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
      customFields: [
        {
          key: "resource_id",
          label: "Resource ID",
          type: "text",
          defaultValue: "seed-tts-2.0",
          placeholder: "seed-tts-2.0",
          description: "Provider 资源标识 (如 X-Api-Resource-Id)；若连接返回 403，请填写控制台授权并与音色匹配的 Resource ID。",
          required: true,
        },
        {
          key: "default_voice",
          label: "默认音色 ID",
          type: "text",
          defaultValue: "zh_female_vv_uranus_bigtts",
          placeholder: "zh_female_vv_uranus_bigtts",
          required: true,
        },
      ],
    },
  ],
  publishing: [
    {
      type: "publishing",
      name: "douyin",
      display: "抖音创作者中心",
      hint: "托管抖音创作者中心安全凭证，成片生成后直接进入发布排期或一键多端发布。",
      hasBaseUrl: false,
      hasModel: false,
      hasApiKey: false,
      hasWorkflow: false,
    },
  ],
};

const VOLCENGINE_TTS_DEFAULT_VOICE = "zh_female_vv_uranus_bigtts";
const VOLCENGINE_TTS_DEFAULT_RESOURCE_ID = "seed-tts-2.0";
const VOLCENGINE_TTS_DEFAULT_SPEED_RATIO = 1.0;
const VOLCENGINE_TTS_MIN_SPEED_RATIO = 0.5;
const VOLCENGINE_TTS_MAX_SPEED_RATIO = 2.0;
const DEFAULT_IMAGE_TEST_PROMPT = "一只橘猫坐在窗边，温暖阳光";
const DEFAULT_IMAGE_TEST_STYLE = "cinematic_real";
const IMAGE_TEST_STYLE_OPTIONS = STYLE_PRESET_OPTIONS.filter((style) => style.value !== "custom");

function normalizeVolcengineTtsSpeed(value: unknown): number {
  if (value === undefined || value === null || value === "") {
    return VOLCENGINE_TTS_DEFAULT_SPEED_RATIO;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return VOLCENGINE_TTS_DEFAULT_SPEED_RATIO;
  }
  return Math.min(
    VOLCENGINE_TTS_MAX_SPEED_RATIO,
    Math.max(VOLCENGINE_TTS_MIN_SPEED_RATIO, parsed),
  );
}

interface CategoryMeta {
  key: string;
  title: string;
  shortTitle: string;
  subtitle: string;
  group: "engine" | "channel" | "system";
  icon: React.ComponentType<{ className?: string }>;
  impactText: string;
}

const SETTING_CATEGORIES: CategoryMeta[] = [
  {
    key: "llm",
    title: "语言模型 (LLM)",
    shortTitle: "语言模型",
    subtitle: "用于主题构思、脚本文案创作与分镜设计的主控大模型",
    group: "engine",
    icon: Bot,
    impactText: "未配置生效语言模型时，文案生成与智能分镜规划将无法执行。",
  },
  {
    key: "search",
    title: "事实检索",
    shortTitle: "事实检索",
    subtitle: "热点趋势调研、背景资料检索与事实验证",
    group: "engine",
    icon: Search,
    impactText: "未配置事实检索 Provider 时，系统将跳过外部搜索，直接基于语言模型通用知识创作分镜。",
  },
  {
    key: "image",
    title: "图像生成",
    shortTitle: "图像生成",
    subtitle: "配置图像生成模型或工作流，渲染视频分镜画面",
    group: "engine",
    icon: ImageIcon,
    impactText: "未配置图像生成 Provider 时无法自动渲染画面，可在分镜中手动上传本地素材继续流程。",
  },
  {
    key: "video",
    title: "视频生成",
    shortTitle: "视频生成",
    subtitle: "配置视频生成模型或工作流，渲染动态分镜镜头",
    group: "engine",
    icon: VideoIcon,
    impactText: "未配置视频生成 Provider 时，流水线将自动降级为“静态画面 + 运镜动画”合成完整 MP4 成片，不阻塞流程。",
  },
  {
    key: "material",
    title: "素材库视频",
    shortTitle: "素材库视频",
    subtitle: "按分镜检索词检索与获取可商用实拍视频",
    group: "engine",
    icon: VideoIcon,
    impactText: "未配置素材库 Provider 时，仍可使用 AI 生图、视频生成或我的素材。",
  },
  {
    key: "tts",
    title: "语音合成 (TTS)",
    shortTitle: "语音合成",
    subtitle: "配置语音合成 Provider 与默认音色，用于旁白解说与配音生成",
    group: "engine",
    icon: Volume2,
    impactText: "支持系统内置免密钥语音引擎与第三方高保真语音 Provider。",
  },
  {
    key: "publishing",
    title: "平台分发",
    shortTitle: "平台分发",
    subtitle: "托管社交平台创作者授权凭据，支持成片定时自动发布",
    group: "channel",
    icon: Share2,
    impactText: "未绑定社交账号时仅影响一键自动发布，成片后仍可在本地直接下载完整 MP4 视频文件自行分发。",
  },
  {
    key: "system",
    title: "系统与存储",
    shortTitle: "系统与存储",
    subtitle: "持久化存储、并发工作线程池与运行目录诊断",
    group: "system",
    icon: HardDrive,
    impactText: "任务、生成过程文件和运行状态会持久化到配置的存储目录与 SQLite 数据库。",
  },
];

const TTS_LANGUAGE_PRESETS = [
  {
    key: "zh-CN",
    name: "普通话",
    localePrefix: ["zh-CN"],
    defaultSample: "你好，这是 Trendlume 汉语普通话神经网络语音合成试听测试。",
    defaultVoice: "zh-CN-YunxiNeural",
  },
  {
    key: "zh-HK",
    name: "粤语",
    localePrefix: ["zh-HK"],
    defaultSample: "你好，呢個係 Trendlume 廣東話神經網絡語音合成試聽。",
    defaultVoice: "zh-HK-HiuMaanNeural",
  },
  {
    key: "dialects",
    name: "地方方言 / 台语",
    localePrefix: ["zh-TW", "zh-CN-liaoning", "zh-CN-shaanxi"],
    defaultSample: "你好啊，这是地方特色方言与台湾国语语音合成试听。",
    defaultVoice: "zh-TW-HsiaoChenNeural",
  },
  {
    key: "en",
    name: "英语",
    localePrefix: ["en-US", "en-GB"],
    defaultSample: "Hello! This is a high quality neural voice synthesis test from Trendlume.",
    defaultVoice: "en-US-JennyNeural",
  },
  {
    key: "ja",
    name: "日语",
    localePrefix: ["ja-JP"],
    defaultSample: "こんにちは！这是TrendlumeのAI音声合成のプレビューテストです。",
    defaultVoice: "ja-JP-NanamiNeural",
  },
  {
    key: "ko",
    name: "韩语",
    localePrefix: ["ko-KR"],
    defaultSample: "안녕하세요! Trendlume 인공지능 음성 합성 샘플 테스트입니다.",
    defaultVoice: "ko-KR-SunHiNeural",
  },
];

function getCategoryStatus(
  categoryKey: string,
  summary?: SystemConfigSummary,
  providers: ProviderConfigItem[] = [],
  preferredProviderId?: string,
): { tone: "success" | "warning" | "destructive" | "neutral"; label: string; isReady: boolean } {
  if (categoryKey === "system") {
    return { tone: "success", label: "正常就绪", isReady: true };
  }
  const catSummary = summary?.categories.find((c) => c.type === categoryKey);
  const categoryProviderSummaries = summary?.providers.filter((provider) => provider.provider_type === categoryKey) || [];
  const preferredProvider = preferredProviderId
    ? categoryProviderSummaries.find((provider) => provider.id === preferredProviderId)
    : undefined;
  const configuredProviders = categoryProviderSummaries.filter((provider) => provider.configured);
  const configuredFallbackStatus =
    configuredProviders.find((provider) => provider.connection_status === "ready")?.connection_status ||
    configuredProviders.find((provider) => provider.connection_status === "not_tested")?.connection_status ||
    configuredProviders.find((provider) => provider.connection_status === "failed")?.connection_status;
  const status =
    preferredProvider?.connection_status ||
    (categoryKey !== "publishing" && catSummary?.status === "not_configured"
      ? configuredFallbackStatus
      : undefined) ||
    catSummary?.status ||
    (providers.some((p) => p.provider_type === categoryKey) ? "not_tested" : "not_configured");

  switch (status) {
    case "ready":
      return { tone: "success", label: "连接就绪", isReady: true };
    case "not_tested":
      return { tone: "warning", label: "待测试", isReady: false };
    case "failed":
      return { tone: "destructive", label: "连接失败", isReady: false };
    case "disabled":
      return { tone: "neutral", label: "已停用", isReady: false };
    default:
      return { tone: "neutral", label: "未配置", isReady: false };
  }
}

function normalizeLlmPresetName(providerName: string | undefined): string | undefined {
  return providerName === "custom_llm" ? "custom" : providerName;
}

function matchesPresetProvider(provider: ProviderConfigItem, presetName: string): boolean {
  return provider.provider_name === presetName ||
    (presetName === "custom" && provider.provider_name === "custom_llm");
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [activeCategoryKey, setActiveCategoryKey] = React.useState<string>("llm");

  const { data: providers = [], isLoading: providersLoading } = useQuery({
    queryKey: ["providers"],
    queryFn: () => api.listProviders(),
  });

  const { data: configSummary } = useQuery<SystemConfigSummary>({
    queryKey: ["system-config-summary"],
    queryFn: () => api.getSystemConfigSummary(),
  });

  const { data: workflows = [] } = useQuery({
    queryKey: ["comfyui-workflows"],
    queryFn: () => api.listComfyUIWorkflows(),
  });

  const { data: voices = [] } = useQuery({
    queryKey: ["voices"],
    queryFn: () => api.listVoices(),
  });

  const createMutation = useMutation({
    mutationFn: (data: ProviderCreatePayload) => api.createProvider(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      queryClient.invalidateQueries({ queryKey: ["system-config-summary"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ProviderUpdatePayload }) =>
      api.updateProvider(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      queryClient.invalidateQueries({ queryKey: ["system-config-summary"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteProvider(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      queryClient.invalidateQueries({ queryKey: ["system-config-summary"] });
    },
  });

  const activeCategory = SETTING_CATEGORIES.find((c) => c.key === activeCategoryKey) || SETTING_CATEGORIES[0];
  const overall = configSummary?.overall;

  const engineCategories = SETTING_CATEGORIES.filter((c) => c.group === "engine");
  const channelCategories = SETTING_CATEGORIES.filter((c) => c.group === "channel");
  const systemCategories = SETTING_CATEGORIES.filter((c) => c.group === "system");

  return (
    <PageContainer width="wide" className="space-y-4">
      {/* SaaS Page Header with Overall Health Status */}
      <header className="flex flex-col gap-2.5 border-b border-border/70 pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h1 className="text-lg sm:text-xl font-bold leading-tight tracking-tight text-foreground">
            系统设置
          </h1>
          <p className="max-w-3xl text-sm leading-normal text-muted-foreground">
            管理语言模型、图像与视频生成、语音合成、素材库视频等 Provider 及平台发布凭据。
          </p>
        </div>

        {overall && (
          <div className="flex items-center gap-2 rounded-xl glass-pill px-3.5 py-1.5 text-xs font-mono shrink-0 shadow-xs border border-border/70">
            <span className="flex items-center gap-1.5 text-foreground font-medium">
              <span className="h-2 w-2 rounded-full bg-success" />
              <span>{overall.ready_categories}/{configSummary?.categories.length ?? 0} 项 Provider 就绪</span>
            </span>
            {overall.pending_test_categories > 0 && (
              <>
                <span className="text-muted-foreground/40">|</span>
                <span className="text-warning font-medium">{overall.pending_test_categories} 项待测试</span>
              </>
            )}
            {overall.missing_items.length > 0 && (
              <>
                <span className="text-muted-foreground/40">|</span>
                <span className="text-muted-foreground">{overall.missing_items.length} 项未配置</span>
              </>
            )}
          </div>
        )}
      </header>

      {/* Two-Column Master-Detail Layout */}
      <div className="flex flex-col md:flex-row items-start gap-4 lg:gap-5">
        {/* Left Sidebar Navigation Rail */}
        <nav
          aria-label="Provider 设置导航"
          className="w-full md:w-60 lg:w-64 shrink-0 space-y-3 rounded-xl glass-panel p-2.5 shadow-glass"
        >
          {/* Group 1: Core Generation Providers */}
          <div className="space-y-1.5">
            <div className="px-2.5 py-1 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              核心生成 Provider
            </div>
            <div className="space-y-0.5">
              {engineCategories.map((cat) => {
                const isSelected = activeCategoryKey === cat.key;
                const status = getCategoryStatus(cat.key, configSummary, providers);
                const count = configSummary?.providers.filter(
                  (provider) => provider.provider_type === cat.key && provider.configured,
                ).length ?? 0;

                return (
                  <button
                    key={cat.key}
                    type="button"
                    onClick={() => setActiveCategoryKey(cat.key)}
                    className={cn(
                      "group flex w-full items-center justify-between gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-150 text-left cursor-pointer select-none",
                      isSelected
                        ? "bg-primary/10 text-primary border border-primary/20 shadow-xs font-semibold"
                        : "text-muted-foreground hover:bg-secondary hover:text-foreground border border-transparent"
                    )}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <cat.icon
                        className={cn(
                          "h-4 w-4 shrink-0 transition-colors",
                          isSelected ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                        )}
                      />
                      <span className="truncate">{cat.shortTitle}</span>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {count > 0 && (
                        <span className="font-mono text-xs text-muted-foreground/70">
                          {count}
                        </span>
                      )}
                      <span
                        aria-label={status.label}
                        className={cn(
                          "h-2 w-2 rounded-full shrink-0",
                          status.tone === "success" && "bg-success",
                          status.tone === "warning" && "bg-warning",
                          status.tone === "destructive" && "bg-destructive",
                          status.tone === "neutral" && "bg-muted-foreground/40"
                        )}
                      />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Group 2: Publishing & Channels */}
          <div className="space-y-1.5 pt-2 border-t border-border/60">
            <div className="px-2.5 py-1 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              分发与渠道
            </div>
            <div className="space-y-0.5">
              {channelCategories.map((cat) => {
                const isSelected = activeCategoryKey === cat.key;
                const status = getCategoryStatus(cat.key, configSummary, providers);

                return (
                  <button
                    key={cat.key}
                    type="button"
                    onClick={() => setActiveCategoryKey(cat.key)}
                    className={cn(
                      "group flex w-full items-center justify-between gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-150 text-left cursor-pointer select-none",
                      isSelected
                        ? "bg-primary/10 text-primary border border-primary/20 shadow-xs font-semibold"
                        : "text-muted-foreground hover:bg-secondary hover:text-foreground border border-transparent"
                    )}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <cat.icon
                        className={cn(
                          "h-4 w-4 shrink-0 transition-colors",
                          isSelected ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                        )}
                      />
                      <span className="truncate">{cat.shortTitle}</span>
                    </div>

                    <span
                      aria-label={status.label}
                      className={cn(
                        "h-2 w-2 rounded-full shrink-0",
                        status.tone === "success" && "bg-success",
                        status.tone === "warning" && "bg-warning",
                        status.tone === "destructive" && "bg-destructive",
                        status.tone === "neutral" && "bg-muted-foreground/40"
                      )}
                    />
                  </button>
                );
              })}
            </div>
          </div>

          {/* Group 3: System & Diagnostics */}
          <div className="space-y-1.5 pt-2 border-t border-border/60">
            <div className="px-2.5 py-1 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              系统与底层
            </div>
            <div className="space-y-0.5">
              {systemCategories.map((cat) => {
                const isSelected = activeCategoryKey === cat.key;

                return (
                  <button
                    key={cat.key}
                    type="button"
                    onClick={() => setActiveCategoryKey(cat.key)}
                    className={cn(
                      "group flex w-full items-center justify-between gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-150 text-left cursor-pointer select-none",
                      isSelected
                        ? "bg-primary/10 text-primary border border-primary/20 shadow-xs font-semibold"
                        : "text-muted-foreground hover:bg-secondary hover:text-foreground border border-transparent"
                    )}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <cat.icon
                        className={cn(
                          "h-4 w-4 shrink-0 transition-colors",
                          isSelected ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                        )}
                      />
                      <span className="truncate">{cat.shortTitle}</span>
                    </div>

                    <span className="h-2 w-2 rounded-full bg-success shrink-0" />
                  </button>
                );
              })}
            </div>
          </div>
        </nav>

        {/* Right Main Configuration Focus Canvas */}
        <main className="flex-1 min-w-0 w-full space-y-4">
          {activeCategoryKey === "system" ? (
            <SystemDiagnosticsWorkspace summary={configSummary} />
          ) : activeCategoryKey === "publishing" ? (
            <PublishingWorkspace />
          ) : (
            <ProviderWorkspace
              key={activeCategoryKey}
              category={activeCategory}
              providers={providers}
              providersLoading={providersLoading}
              summary={configSummary}
              workflows={workflows}
              voices={voices}
              createMutation={createMutation}
              updateMutation={updateMutation}
              deleteMutation={deleteMutation}
            />
          )}
        </main>
      </div>
    </PageContainer>
  );
}

// -----------------------------------------------------------------------------
// Component: Provider Configuration Workspace (Focus Panel for Engines)
// -----------------------------------------------------------------------------
function ProviderWorkspace({
  category,
  providers,
  providersLoading,
  summary,
  workflows,
  voices,
  createMutation,
  updateMutation,
  deleteMutation,
}: {
  category: CategoryMeta;
  providers: ProviderConfigItem[];
  providersLoading: boolean;
  summary?: SystemConfigSummary;
  workflows: any[];
  voices: any[];
  createMutation: any;
  updateMutation: any;
  deleteMutation: any;
}) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const categoryKey = category.key;
  const presets = PRESET_OPTIONS[categoryKey] || [];
  const categoryProviders = providers.filter((p) => p.provider_type === categoryKey);
  const configuredProviderCount = summary?.providers.filter(
    (provider) => provider.provider_type === categoryKey && provider.configured,
  ).length ?? 0;
  const defaultProvider = categoryProviders.find((p) => p.is_default) || categoryProviders[0];

  const [selectedVendorName, setSelectedVendorName] = React.useState<string>(
    normalizeLlmPresetName(defaultProvider?.provider_name) || presets[0]?.name || "default"
  );

  const [displayName, setDisplayName] = React.useState<string>("");
  const [baseUrl, setBaseUrl] = React.useState<string>("");
  const [model, setModel] = React.useState<string>("");
  const [workflow, setWorkflow] = React.useState<string>("");
  const [customFieldValues, setCustomFieldValues] = React.useState<Record<string, any>>({});
  const [apiKey, setApiKey] = React.useState<string>("");
  const [isEditingApiKey, setIsEditingApiKey] = React.useState<boolean>(false);
  const [showApiKey, setShowApiKey] = React.useState<boolean>(false);
  const [enabled, setEnabled] = React.useState<boolean>(true);
  const [isDefault, setIsDefault] = React.useState<boolean>(false);
  const [isSavedNotice, setIsSavedNotice] = React.useState<boolean>(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = React.useState(false);
  const [isDirty, setIsDirty] = React.useState(false);
  const hydratedCategoryRef = React.useRef<string | null>(null);

  const [isTesting, setIsTesting] = React.useState(false);
  const [testResult, setTestResult] = React.useState<ProviderTestResult | null>(null);
  const [testMode, setTestMode] = React.useState<"connection" | "image_generation" | null>(null);
  const [imageTestPrompt, setImageTestPrompt] = React.useState(DEFAULT_IMAGE_TEST_PROMPT);
  const [imageTestStyle, setImageTestStyle] = React.useState(DEFAULT_IMAGE_TEST_STYLE);
  const [imageTestUrl, setImageTestUrl] = React.useState<string | null>(null);

  const [selectedLangKey, setSelectedLangKey] = React.useState<string>("zh-CN");
  const [previewVoiceId, setPreviewVoiceId] = React.useState<string>("zh-CN-YunxiNeural");
  const [previewText, setPreviewText] = React.useState<string>(TTS_LANGUAGE_PRESETS[0].defaultSample);
  const [previewSpeedRatio, setPreviewSpeedRatio] = React.useState(VOLCENGINE_TTS_DEFAULT_SPEED_RATIO);
  const [isPlayingAudio, setIsPlayingAudio] = React.useState(false);
  const [activeAudio, setActiveAudio] = React.useState<HTMLAudioElement | null>(null);

  const categoryWorkflows = workflows.filter(
    (w: any) =>
      w.type === categoryKey ||
      w.subfolder === categoryKey ||
      w.id?.startsWith(`${categoryKey}/`) ||
      w.path?.startsWith(`${categoryKey}/`)
  );

  const existingProvider = categoryProviders.find((p) => matchesPresetProvider(p, selectedVendorName));
  const selectedProviderSummary = existingProvider
    ? summary?.providers.find((provider) => provider.id === existingProvider.id)
    : undefined;
  const displayedTestResult = testResult || (!isDirty ? selectedProviderSummary?.last_test : null);
  const currentPreset = presets.find((p) => p.name === selectedVendorName) || presets[0];

  const SOLID_MASK_DOTS = "••••••••••••••••";
  const hasSavedApiKey = Boolean(
    existingProvider?.has_credentials || existingProvider?.masked_credentials?.api_key
  );
  const isDisplayingSavedDots = hasSavedApiKey && !isEditingApiKey && !apiKey;
  const inputDisplayValue = isDisplayingSavedDots
    ? showApiKey
      ? (existingProvider?.masked_credentials?.api_key || SOLID_MASK_DOTS)
      : SOLID_MASK_DOTS
    : apiKey;
  const inputType = showApiKey ? "text" : "password";

  const markDirty = () => {
    setIsDirty(true);
    setTestResult(null);
    setTestMode(null);
    setImageTestUrl(null);
  };

  const handleApiKeyChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    if (isDisplayingSavedDots) {
      const clean = raw.replace(/[••]/g, "");
      setApiKey(clean);
      setIsEditingApiKey(true);
    } else {
      setApiKey(raw);
      setIsEditingApiKey(true);
    }
    markDirty();
  };

  const handleApiKeyFocus = (e: React.FocusEvent<HTMLInputElement>) => {
    if (isDisplayingSavedDots) {
      e.target.select();
    }
  };

  const loadVendorFields = (vendorName: string, existing?: ProviderConfigItem, preset?: PresetOption) => {
    const customDefs = preset?.customFields || [];
    const newCustomValues: Record<string, any> = {};

    if (existing) {
      setDisplayName(existing.display_name);
      setBaseUrl(existing.config?.base_url || preset?.defaultBaseUrl || "");
      setModel(existing.config?.model || preset?.defaultModel || "");
      setWorkflow(existing.config?.default_workflow || preset?.defaultWorkflow || "");
      setEnabled(existing.enabled);
      setIsDefault(existing.is_default);

      customDefs.forEach((cf) => {
        const val = existing.config?.[cf.key];
        newCustomValues[cf.key] = val !== undefined ? String(val) : String(cf.defaultValue ?? "");
      });

      if (categoryKey === "tts") {
        const voiceFromConfig =
          existing.config?.default_voice ||
          newCustomValues.default_voice ||
          (vendorName === "volcengine" ? VOLCENGINE_TTS_DEFAULT_VOICE : "zh-CN-YunxiNeural");
        setPreviewVoiceId(voiceFromConfig);
      }
    } else if (preset) {
      setDisplayName(preset.display);
      setBaseUrl(preset.defaultBaseUrl || "");
      setModel(preset.defaultModel || "");
      setWorkflow(preset.defaultWorkflow || "");
      setEnabled(true);
      setIsDefault(categoryProviders.length === 0);

      customDefs.forEach((cf) => {
        newCustomValues[cf.key] = String(cf.defaultValue ?? "");
      });

      if (categoryKey === "tts") {
        setPreviewVoiceId(
          vendorName === "volcengine"
            ? VOLCENGINE_TTS_DEFAULT_VOICE
            : "zh-CN-YunxiNeural"
        );
      }
    } else {
      setDisplayName(vendorName);
      setBaseUrl("");
      setModel("");
      setWorkflow("");
      setEnabled(true);
      setIsDefault(categoryProviders.length === 0);
      setPreviewVoiceId("zh-CN-YunxiNeural");
    }

    setPreviewSpeedRatio(
      categoryKey === "tts" && vendorName === "volcengine"
        ? normalizeVolcengineTtsSpeed(existing?.config?.speed_ratio)
        : VOLCENGINE_TTS_DEFAULT_SPEED_RATIO,
    );
    setCustomFieldValues(newCustomValues);
    setApiKey("");
    setIsEditingApiKey(false);
    setShowApiKey(false);
    setTestResult(null);
    setTestMode(null);
    setImageTestStyle(DEFAULT_IMAGE_TEST_STYLE);
    setImageTestUrl(null);
    setIsDirty(false);
  };

  React.useEffect(() => {
    if (providersLoading || hydratedCategoryRef.current === categoryKey) return;
    hydratedCategoryRef.current = categoryKey;
    const initialVendor = normalizeLlmPresetName(defaultProvider?.provider_name) || presets[0]?.name || "default";
    setSelectedVendorName(initialVendor);
    const matched = categoryProviders.find((p) => matchesPresetProvider(p, initialVendor));
    const p = presets.find((x) => x.name === initialVendor);
    loadVendorFields(initialVendor, matched, p);
  }, [categoryKey, providersLoading]);

  const handleVendorSelect = (vendorName: string) => {
    setSelectedVendorName(vendorName);
    const matchedPreset = presets.find((p) => p.name === vendorName);
    const matchedExisting = categoryProviders.find((p) => matchesPresetProvider(p, vendorName));
    loadVendorFields(vendorName, matchedExisting, matchedPreset);
  };

  const handleLanguageChange = (langKey: string) => {
    setSelectedLangKey(langKey);
    const preset = TTS_LANGUAGE_PRESETS.find((l) => l.key === langKey);
    if (preset) {
      setPreviewVoiceId(preset.defaultVoice);
      setPreviewText(preset.defaultSample);
    }
  };

  const currentLangPreset = TTS_LANGUAGE_PRESETS.find((l) => l.key === selectedLangKey) || TTS_LANGUAGE_PRESETS[0];
  const filteredVoices = voices.filter((v: any) =>
    currentLangPreset.localePrefix.some((prefix) => v.locale?.startsWith(prefix) || v.id?.startsWith(prefix))
  );

  const buildProviderPayload = () => {
    const config: Record<string, any> = {};
    if (currentPreset?.hasBaseUrl !== false && baseUrl) {
      config.base_url = baseUrl.trim();
    }
    if (currentPreset?.hasModel && model) {
      config.model = model.trim();
    }
    if (currentPreset?.hasWorkflow && workflow) {
      config.default_workflow = workflow.trim();
    }

    if (currentPreset?.customFields) {
      currentPreset.customFields.forEach((cf) => {
        const rawVal = customFieldValues[cf.key] ?? cf.defaultValue;
        if (rawVal !== undefined && rawVal !== "") {
          config[cf.key] = cf.type === "number" ? Number(rawVal) : rawVal;
        }
      });
    }

    if (categoryKey === "material") {
      config.locale = customFieldValues.locale || "zh-CN";
      config.size = "medium";
      config.min_short_edge = Math.max(1, Number(customFieldValues.min_short_edge) || 720);
      config.timeout = 15;
      config.download_timeout = 120;
      config.max_download_bytes = 200 * 1024 * 1024;
    }
    if (categoryKey === "tts" && selectedVendorName === "edge_tts") {
      config.default_voice = previewVoiceId;
    }
    if (categoryKey === "tts" && selectedVendorName === "volcengine") {
      config.resource_id = (customFieldValues.resource_id || VOLCENGINE_TTS_DEFAULT_RESOURCE_ID).trim();
      config.default_voice = (previewVoiceId || customFieldValues.default_voice || VOLCENGINE_TTS_DEFAULT_VOICE).trim();
      config.speed_ratio = previewSpeedRatio;
      config.timeout = 60;
    }
    if (categoryKey === "image" && selectedVendorName === "volcengine") {
      config.response_format = "url";
      config.watermark = false;
    }
    if (categoryKey === "video" && selectedVendorName === "volcengine") {
      config.generation_timeout = 1800;
      config.poll_interval = 5;
      config.resolution = "720p";
      config.generate_audio = false;
      config.watermark = false;
    }

    const credentials: Record<string, any> = {};
    if (currentPreset?.hasApiKey !== false && apiKey.trim()) {
      credentials.api_key = apiKey.trim();
    }

    return { config, credentials };
  };

  const saveCurrentProvider = async () => {
    const { config, credentials } = buildProviderPayload();

    if (existingProvider) {
      const payload: ProviderUpdatePayload = {
        display_name: displayName || currentPreset?.display || selectedVendorName,
        enabled,
        is_default: isDefault,
        config,
        ...(Object.keys(credentials).length > 0 ? { credentials } : {}),
      };
      const saved = await updateMutation.mutateAsync({ id: existingProvider.id, data: payload });
      return saved.id;
    } else {
      const payload: ProviderCreatePayload = {
        provider_type: categoryKey,
        provider_name: selectedVendorName,
        display_name: displayName || currentPreset?.display || selectedVendorName,
        enabled,
        is_default: isDefault,
        config,
        ...(Object.keys(credentials).length > 0 ? { credentials } : {}),
      };
      const created = await createMutation.mutateAsync(payload);
      return created.id;
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await saveCurrentProvider();
      setIsSavedNotice(true);
      setApiKey("");
      setIsEditingApiKey(false);
      setTestResult(null);
      setTestMode(null);
      setImageTestUrl(null);
      setIsDirty(false);
      toast("Provider 配置已成功保存。", "success");
      setTimeout(() => setIsSavedNotice(false), 2500);
    } catch (err: any) {
      toast(err?.message || "保存配置失败，请检查参数。", "error");
    }
  };

  const handleTestConnection = async () => {
    if (currentPreset?.hasApiKey !== false && !hasSavedApiKey && !apiKey.trim()) {
      toast("请先填写 API Key 再测试连通性。", "warning");
      return;
    }
    if (currentPreset?.hasBaseUrl && !baseUrl.trim()) {
      toast("请填写 Base URL 端点地址。", "warning");
      return;
    }

    setIsTesting(true);
    setTestResult(null);
    setTestMode("connection");
    setImageTestUrl(null);

    try {
      const { config, credentials } = buildProviderPayload();
      const hasUnsavedChanges = isDirty || Boolean(apiKey.trim());

      const res = await api.testProviderConnection({
        // Keep the saved provider id so the backend can reuse its encrypted
        // credentials while testing an unsaved config change. The manager
        // only persists evidence when the submitted config is unchanged.
        provider_id: existingProvider?.id,
        provider_type: categoryKey,
        provider_name: selectedVendorName,
        config,
        credentials: Object.keys(credentials).length > 0 ? credentials : undefined,
      });

      setTestResult(res);
      if (!hasUnsavedChanges && existingProvider?.id) {
        queryClient.invalidateQueries({ queryKey: ["providers"] });
        queryClient.invalidateQueries({ queryKey: ["system-config-summary"] });
      }
      if (res.connected) {
        toast(`连接测试成功${res.latency_ms ? ` (延迟 ${res.latency_ms}ms)` : ""}。`, "success");
      } else {
        toast("连接测试失败，请核对网络与配置。", "warning");
      }
    } catch (err: any) {
      setTestResult({
        connected: false,
        message: err.message || "探测请求异常，无法连通 Provider 接口端点。",
      });
      toast("探测请求异常，无法连通 Provider 接口端点。", "error");
    } finally {
      setIsTesting(false);
    }
  };

  const handleTestImage = async () => {
    if (currentPreset?.hasApiKey !== false && !hasSavedApiKey && !apiKey.trim()) {
      toast("请先填写 API Key 再测试图片生成。", "warning");
      return;
    }
    if (currentPreset?.hasBaseUrl && !baseUrl.trim()) {
      toast("请填写 Base URL 端点地址。", "warning");
      return;
    }

    const prompt = imageTestPrompt.trim() || DEFAULT_IMAGE_TEST_PROMPT;
    setImageTestPrompt(prompt);
    setIsTesting(true);
    setTestResult(null);
    setTestMode("image_generation");
    setImageTestUrl(null);

    try {
      const { config, credentials } = buildProviderPayload();
      const hasUnsavedChanges = isDirty || Boolean(apiKey.trim());
      const res = await api.testImageGeneration({
        // Reuse saved credentials for unsaved prompt/config changes; the
        // image stays response-only, while the backend applies its existing
        // config-match rule to persisted test evidence.
        provider_id: existingProvider?.id,
        provider_name: selectedVendorName,
        config,
        credentials: Object.keys(credentials).length > 0 ? credentials : undefined,
        prompt,
        aspect_ratio: "16:9",
        style_preset: imageTestStyle,
      });

      setTestResult(res);
      setImageTestUrl(res.image_url || null);
      if (!hasUnsavedChanges && existingProvider?.id) {
        queryClient.invalidateQueries({ queryKey: ["providers"] });
        queryClient.invalidateQueries({ queryKey: ["system-config-summary"] });
      }
      if (res.connected) {
        toast(`图片生成测试成功${res.latency_ms ? ` (耗时 ${res.latency_ms}ms)` : ""}。`, "success");
      } else {
        toast("图片生成测试失败，请核对网络与配置。", "warning");
      }
    } catch (err: any) {
      setTestResult({
        connected: false,
        message: err.message || "图片生成测试请求异常。",
      });
      toast("图片生成测试请求异常，请检查网络连接与配置。", "error");
    } finally {
      setIsTesting(false);
    }
  };

  const handlePreviewVoice = async () => {
    if (isPlayingAudio && activeAudio) {
      activeAudio.pause();
      setIsPlayingAudio(false);
      return;
    }

    try {
      setIsPlayingAudio(true);
      const voiceToTest =
        selectedVendorName === "volcengine"
          ? (customFieldValues.default_voice || previewVoiceId || VOLCENGINE_TTS_DEFAULT_VOICE)
          : previewVoiceId;
      const blob = await api.testVoice(
        voiceToTest,
        previewText,
        existingProvider?.id,
        selectedVendorName === "volcengine" ? previewSpeedRatio : undefined,
      );
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      setActiveAudio(audio);
      audio.onended = () => setIsPlayingAudio(false);
      audio.onerror = () => setIsPlayingAudio(false);
      audio.play();
    } catch {
      setIsPlayingAudio(false);
      toast("试听音频生成失败，请检查网络连接与配置。", "error");
    }
  };

  const status = getCategoryStatus(categoryKey, summary, providers, existingProvider?.id);

  return (
    <div className="space-y-4">
      {/* Active Category Header Card */}
      <Card className="glass-card rounded-xl">
        <CardHeader className="pb-3 border-b border-border/70">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <category.icon className="h-4 w-4 text-primary" />
                <CardTitle className="text-sm sm:text-base font-semibold text-foreground">
                  {category.title}
                </CardTitle>
                <StatusBadge
                  tone={status.tone}
                  label={status.label}
                  className="text-xs"
                />
                {existingProvider?.is_default && (
                  <Badge variant="default" className="gap-1 text-xs">
                    <Star className="h-2.5 w-2.5 fill-current" />
                    默认 Provider
                  </Badge>
                )}
              </div>
              <CardDescription className="text-xs text-muted-foreground">
                {category.subtitle}
              </CardDescription>
            </div>

            {configuredProviderCount > 0 && (
              <Badge variant="outline" className="font-mono text-xs self-start sm:self-center">
                已配置 {configuredProviderCount} 项 Provider
              </Badge>
            )}
          </div>
        </CardHeader>

        <CardContent className="p-4 sm:p-5 space-y-5 text-xs">
          {/* 1. Provider 预设选择卡片 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground tracking-tight">
                Provider 预设
              </span>
              {currentPreset?.keyUrl && (
                <a
                  href={currentPreset.keyUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline group"
                >
                  <Key className="h-3 w-3" />
                  <span>获取 API Key</span>
                  <ExternalLink className="h-2.5 w-2.5 opacity-70 transition-transform group-hover:translate-x-0.5" />
                </a>
              )}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
              {presets.map((preset) => {
                const isSelected = selectedVendorName === preset.name;
                const matchedProvider = categoryProviders.find((p) => matchesPresetProvider(p, preset.name));
                const providerSummary = matchedProvider
                  ? summary?.providers.find((provider) => provider.id === matchedProvider.id)
                  : undefined;
                const isConfiguredInDb = Boolean(providerSummary?.configured);
                const isPresetDefault = matchedProvider?.is_default;

                return (
                  <button
                    key={preset.name}
                    type="button"
                    aria-pressed={isSelected}
                    disabled={isTesting || createMutation.isPending || updateMutation.isPending}
                    onClick={() => handleVendorSelect(preset.name)}
                    className={cn(
                      "flex flex-col justify-between rounded-lg border p-3 text-left transition-all duration-150 cursor-pointer select-none",
                      isSelected
                        ? "border-primary bg-primary/5 ring-1 ring-primary shadow-xs"
                        : "border-border bg-background hover:border-foreground/20 hover:bg-secondary/30"
                    )}
                  >
                    <div className="flex items-center justify-between gap-1 w-full mb-1.5">
                      <span className="truncate text-sm font-semibold text-foreground">
                        {preset.display}
                      </span>
                      {isPresetDefault && (
                        <Star className="h-3 w-3 fill-primary text-primary shrink-0" />
                      )}
                    </div>

                    <div className="flex items-center justify-between text-xs">
                      <span className="truncate text-muted-foreground font-mono">
                        {preset.name}
                      </span>
                      {isConfiguredInDb ? (
                        <span className="font-mono text-success font-medium">已配置</span>
                      ) : (
                        <span className="font-mono text-muted-foreground/60">未配置</span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>

            {currentPreset?.hint && (
              <p className="text-xs leading-relaxed text-muted-foreground bg-secondary/30 rounded-lg p-2.5 border border-border/50">
                {currentPreset.hint}
              </p>
            )}
          </div>

          {/* 2. 结构化配置表单 */}
          <form
            onSubmit={handleSave}
            aria-busy={isTesting || createMutation.isPending || updateMutation.isPending}
            className="space-y-4 pt-2 border-t border-border/70"
          >
            {/* 基础连接设置 */}
            <div className="space-y-3">
              <div className="text-xs font-semibold text-foreground">基础连接</div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                <div className="space-y-1">
                  <label htmlFor={`display-name-${categoryKey}`} className="text-xs font-medium text-foreground">
                    Provider 名称
                  </label>
                  <Input
                    id={`display-name-${categoryKey}`}
                    value={displayName}
                    onChange={(e) => {
                      setDisplayName(e.target.value);
                      markDirty();
                    }}
                    placeholder="例如：DeepSeek 官方 API"
                    required
                  />
                </div>

                {currentPreset?.hasBaseUrl !== false && (
                  <div className="space-y-1">
                    <label htmlFor={`base-url-${categoryKey}`} className="text-xs font-medium text-foreground">
                      Base URL
                    </label>
                    <Input
                      id={`base-url-${categoryKey}`}
                      value={baseUrl}
                      onChange={(e) => {
                        setBaseUrl(e.target.value);
                        markDirty();
                      }}
                      placeholder={currentPreset?.defaultBaseUrl || "https://api.example.com/v1"}
                      className="font-mono"
                    />
                  </div>
                )}
              </div>

              {/* Model */}
              {currentPreset?.hasModel && (
                <div className="space-y-1">
                  <label htmlFor={`model-${categoryKey}`} className="text-xs font-medium text-foreground">
                    Model
                  </label>
                  <Input
                    id={`model-${categoryKey}`}
                    value={model}
                    onChange={(e) => {
                      setModel(e.target.value);
                      markDirty();
                    }}
                    placeholder={currentPreset?.defaultModel || "请输入模型标识"}
                    required={categoryKey !== "tts"}
                    className="font-mono"
                  />
                </div>
              )}

              {/* Workflow 工作流 */}
              {currentPreset?.hasWorkflow && (
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <label htmlFor={`workflow-${categoryKey}`} className="text-xs font-medium text-foreground">
                      Workflow 工作流
                    </label>
                    <span className="text-xs text-muted-foreground">
                      本地已扫描到 {categoryWorkflows.length} 个工作流
                    </span>
                  </div>
                  {categoryWorkflows.length > 0 ? (
                    <Select
                      id={`workflow-${categoryKey}`}
                      value={workflow || currentPreset?.defaultWorkflow || ""}
                      onChange={(e) => {
                        setWorkflow(e.target.value);
                        markDirty();
                      }}
                    >
                      {categoryWorkflows.map((wf: any) => {
                        const rawText = wf.name || wf.title || wf.path || "";
                        const cleanLabel = rawText.replace(/\s*[\(\（][^\)\）]*[\)\）]\s*$/g, "").trim();
                        return (
                          <option key={wf.id || wf.path} value={wf.path || wf.id}>
                            {cleanLabel || wf.path}
                          </option>
                        );
                      })}
                    </Select>
                  ) : (
                    <Input
                      id={`workflow-${categoryKey}`}
                      value={workflow}
                      onChange={(e) => setWorkflow(e.target.value)}
                      placeholder={currentPreset?.defaultWorkflow || "请输入工作流路径"}
                      className="font-mono"
                    />
                  )}
                </div>
              )}
            </div>

            {/* 定制参数 (Dynamic Custom Fields) */}
            {currentPreset?.customFields && currentPreset.customFields.length > 0 && (
              <div className="space-y-3 pt-2 border-t border-border/50">
                <div className="text-xs font-semibold text-foreground">参数设置</div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                  {currentPreset.customFields.map((cf) => (
                    <div key={cf.key} className="space-y-1">
                      <label htmlFor={`custom-field-${cf.key}`} className="text-xs font-medium text-foreground">
                        {cf.label}
                      </label>
                      {cf.type === "select" ? (
                        <Select
                          id={`custom-field-${cf.key}`}
                          value={customFieldValues[cf.key] ?? cf.defaultValue ?? ""}
                          onChange={(e) => {
                            const newVal = e.target.value;
                            setCustomFieldValues((prev) => ({
                              ...prev,
                              [cf.key]: newVal,
                            }));
                            markDirty();
                            if (categoryKey === "tts" && cf.key === "default_voice") {
                              setPreviewVoiceId(newVal);
                            }
                          }}
                        >
                          {cf.options?.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <Input
                          id={`custom-field-${cf.key}`}
                          type={cf.type === "number" ? "number" : "text"}
                          value={customFieldValues[cf.key] ?? cf.defaultValue ?? ""}
                          onChange={(e) => {
                            const newVal = e.target.value;
                            setCustomFieldValues((prev) => ({
                              ...prev,
                              [cf.key]: newVal,
                            }));
                            markDirty();
                            if (categoryKey === "tts" && cf.key === "default_voice") {
                              setPreviewVoiceId(newVal);
                            }
                          }}
                          placeholder={cf.placeholder}
                          className="font-mono"
                        />
                      )}
                      {cf.description && (
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          {cf.description}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 身份认证 (Unified API Key) */}
            {currentPreset?.hasApiKey !== false && (
              <div className="space-y-2 pt-2 border-t border-border/50">
                <div className="flex items-center justify-between">
                  <label htmlFor={`api-key-${categoryKey}`} className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                    <Key className="h-3 w-3 text-primary" />
                    <span>API Key</span>
                  </label>
                  <div className="flex items-center gap-2">
                    {isEditingApiKey && hasSavedApiKey && (
                      <button
                        type="button"
                        onClick={() => {
                          setApiKey("");
                          setIsEditingApiKey(false);
                          markDirty();
                        }}
                        className="text-xs text-muted-foreground hover:text-primary transition-colors flex items-center gap-1 cursor-pointer"
                        title="放弃未保存修改，恢复已保存密钥"
                      >
                        <RotateCcw className="h-3 w-3" />
                        <span>恢复已保存密钥</span>
                      </button>
                    )}
                    {isDisplayingSavedDots && (
                      <span className="flex items-center gap-1 text-xs text-success font-medium">
                        <Check className="h-3 w-3" />
                        已安全加密存储
                      </span>
                    )}
                  </div>
                </div>

                <div className="relative">
                  <Input
                    type={inputType}
                    value={inputDisplayValue}
                    onChange={handleApiKeyChange}
                    onFocus={handleApiKeyFocus}
                    placeholder={currentPreset?.keyPlaceholder || "请输入 API Key"}
                    id={`api-key-${categoryKey}`}
                    className="pr-8 font-mono tracking-wider"
                  />
                  <button
                    type="button"
                    aria-label={showApiKey ? "隐藏 API Key" : "显示 API Key"}
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
                  >
                    {showApiKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </button>
                </div>
              </div>
            )}

            {/* 音色工坊与试听 (TTS Voice Studio) */}
            {categoryKey === "tts" && (
              <div className="rounded-xl border border-border/70 bg-card/30 backdrop-blur-sm p-3.5 space-y-3 pt-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 font-medium text-foreground text-xs">
                    <Volume2 className="h-3.5 w-3.5 text-primary" />
                    <span>音色试听</span>
                  </div>
                  {selectedVendorName === "edge_tts" && (
                    <span className="text-xs text-muted-foreground">支持多语种神经网络音色</span>
                  )}
                </div>

                {selectedVendorName === "edge_tts" ? (
                  <Tabs value={selectedLangKey} onValueChange={handleLanguageChange} className="space-y-3">
                    <TabsList aria-label="音色语言分类" className="h-auto flex-wrap max-w-full">
                      {TTS_LANGUAGE_PRESETS.map((lang) => (
                        <TabsTrigger key={lang.key} value={lang.key}>
                          {lang.name}
                        </TabsTrigger>
                      ))}
                    </TabsList>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-1">
                      <div className="space-y-1 sm:col-span-1">
                        <label htmlFor={`voice-${categoryKey}`} className="text-xs font-medium text-muted-foreground">
                          选择音色
                        </label>
                        <Select
                          id={`voice-${categoryKey}`}
                          value={previewVoiceId}
                          onChange={(e) => setPreviewVoiceId(e.target.value)}
                        >
                          {filteredVoices.length > 0 ? (
                            filteredVoices.map((v: any) => (
                              <option key={v.id} value={v.id}>
                                {v.name}（{v.locale}）· {v.gender}
                              </option>
                            ))
                          ) : (
                            <>
                              <option value="zh-CN-YunxiNeural">云希（普通话）· 活力男声</option>
                              <option value="zh-CN-XiaoxiaoNeural">晓晓（普通话）· 亲切女声</option>
                              <option value="zh-HK-HiuMaanNeural">晓曼（粤语）· 女声</option>
                              <option value="en-US-JennyNeural">Jenny（英语）· 女声</option>
                              <option value="ja-JP-NanamiNeural">七海（日语）· 女声</option>
                              <option value="ko-KR-SunHiNeural">善熙（韩语）· 女声</option>
                            </>
                          )}
                        </Select>
                      </div>

                      <div className="space-y-1 sm:col-span-2">
                        <label htmlFor={`voice-preview-${categoryKey}`} className="text-xs font-medium text-muted-foreground">
                          试听文案
                        </label>
                        <div className="flex gap-2">
                          <Input
                            id={`voice-preview-${categoryKey}`}
                            value={previewText}
                            onChange={(e) => setPreviewText(e.target.value)}
                            placeholder="输入试听测试语句…"
                            className="flex-1"
                          />
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={handlePreviewVoice}
                            className="shrink-0 gap-1"
                          >
                            {isPlayingAudio ? (
                              <StopCircle aria-hidden="true" className="h-3.5 w-3.5 text-destructive animate-pulse" />
                            ) : (
                              <Play aria-hidden="true" className="h-3.5 w-3.5 text-primary" />
                            )}
                            <span>{isPlayingAudio ? "停止试听" : "播放试听"}</span>
                          </Button>
                        </div>
                      </div>
                    </div>
                  </Tabs>
                ) : (
                  <div className="space-y-2.5">
                    {selectedVendorName === "volcengine" && (
                      <div className="flex min-h-11 items-center gap-2 border-b border-border/50 pb-1.5">
                        <label
                          htmlFor="volcengine-tts-speed"
                          className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-muted-foreground"
                        >
                          <span>语速</span>
                          <output
                            htmlFor="volcengine-tts-speed"
                            aria-live="polite"
                            className="font-mono text-xs font-semibold text-primary"
                          >
                            {previewSpeedRatio.toFixed(1)}x
                          </output>
                        </label>
                        <input
                          id="volcengine-tts-speed"
                          type="range"
                          min={VOLCENGINE_TTS_MIN_SPEED_RATIO}
                          max={VOLCENGINE_TTS_MAX_SPEED_RATIO}
                          step="0.1"
                          value={previewSpeedRatio}
                          onChange={(e) => {
                            setPreviewSpeedRatio(normalizeVolcengineTtsSpeed(e.target.value));
                            markDirty();
                          }}
                          aria-valuetext={`${previewSpeedRatio.toFixed(1)} 倍速`}
                          className="h-9 min-w-0 flex-1 cursor-pointer accent-primary"
                        />
                        <span className="shrink-0 text-[10px] text-muted-foreground" aria-hidden="true">
                          0.5–2.0x
                        </span>
                      </div>
                    )}
                    <div className="space-y-1">
                      <label htmlFor={`voice-preview-${categoryKey}`} className="text-xs font-medium text-muted-foreground">
                          试听文案
                      </label>
                      <div className="flex gap-2">
                        <Input
                          id={`voice-preview-${categoryKey}`}
                          value={previewText}
                          onChange={(e) => setPreviewText(e.target.value)}
                          placeholder="输入试听测试语句…"
                          className="flex-1"
                        />
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={handlePreviewVoice}
                          className="shrink-0 gap-1.5"
                        >
                          {isPlayingAudio ? (
                            <StopCircle aria-hidden="true" className="h-3.5 w-3.5 text-destructive animate-pulse" />
                          ) : (
                            <Play aria-hidden="true" className="h-3.5 w-3.5 text-primary" />
                          )}
                          <span>{isPlayingAudio ? "停止试听" : "播放试听"}</span>
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 图片生成测试 */}
            {categoryKey === "image" && (
              <div className="rounded-xl border border-border/70 bg-card/30 p-3.5 space-y-3 backdrop-blur-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                    <ImageIcon className="h-3.5 w-3.5 text-primary" />
                    <span>图片生成测试</span>
                  </div>
                  <Badge variant="outline" className="text-[10px] font-normal text-muted-foreground">
                    仅预览，不保存
                  </Badge>
                </div>
                <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_12rem_auto] sm:items-end">
                  <div className="min-w-0 space-y-1.5">
                    <label htmlFor="image-test-prompt" className="text-xs font-medium text-muted-foreground">
                      测试提示词
                    </label>
                    <Input
                      id="image-test-prompt"
                      value={imageTestPrompt}
                      maxLength={500}
                      disabled={isTesting}
                      onChange={(e) => {
                        setImageTestPrompt(e.target.value);
                        setImageTestUrl(null);
                        setTestResult(null);
                        setTestMode(null);
                      }}
                      placeholder={DEFAULT_IMAGE_TEST_PROMPT}
                    />
                  </div>
                  <div className="min-w-0 space-y-1.5">
                    <label htmlFor="image-test-style" className="text-xs font-medium text-muted-foreground">
                      视觉风格
                    </label>
                    <Select
                      id="image-test-style"
                      value={imageTestStyle}
                      disabled={isTesting}
                      onChange={(e) => {
                        setImageTestStyle(e.target.value);
                        setImageTestUrl(null);
                        setTestResult(null);
                        setTestMode(null);
                      }}
                    >
                      {IMAGE_TEST_STYLE_OPTIONS.map((style) => (
                        <option key={style.value} value={style.value}>
                          {style.label}
                        </option>
                      ))}
                    </Select>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={isTesting || createMutation.isPending || updateMutation.isPending}
                    onClick={handleTestImage}
                    className="min-h-11 shrink-0 gap-1.5 sm:h-9 sm:min-h-0"
                  >
                    {isTesting && testMode === "image_generation" ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <ImageIcon className="h-3.5 w-3.5 text-primary" />
                    )}
                    <span>{isTesting && testMode === "image_generation" ? "正在生成…" : "图片生成测试"}</span>
                  </Button>
                </div>
                {imageTestUrl && (
                  <div
                    className="aspect-video overflow-hidden rounded-lg border border-border/60 bg-background/40"
                    aria-live="polite"
                  >
                    <img
                      src={imageTestUrl}
                      alt="图片生成测试结果"
                      loading="eager"
                      decoding="async"
                      className="h-full w-full object-contain"
                    />
                  </div>
                )}
              </div>
            )}

            {/* 运行策略选项 */}
            <div className="flex flex-wrap items-center gap-6 pt-1">
              <label htmlFor={`enabled-${categoryKey}`} className="flex cursor-pointer items-center gap-2 text-sm text-foreground select-none">
                <input
                  id={`enabled-${categoryKey}`}
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => {
                    setEnabled(e.target.checked);
                    markDirty();
                  }}
                  className="rounded border-input text-primary focus:ring-primary h-4 w-4 cursor-pointer"
                />
                <span>启用此 Provider</span>
              </label>

              <label htmlFor={`default-${categoryKey}`} className="flex cursor-pointer items-center gap-2 text-sm text-foreground select-none">
                <input
                  id={`default-${categoryKey}`}
                  type="checkbox"
                  checked={isDefault}
                  onChange={(e) => {
                    setIsDefault(e.target.checked);
                    markDirty();
                  }}
                  className="rounded border-input text-primary focus:ring-primary h-4 w-4 cursor-pointer"
                />
                <span>设为该服务默认 Provider</span>
              </label>
            </div>

            {/* 连通性测试结果横幅 */}
            {displayedTestResult && (
              <div
                role={displayedTestResult.connected ? "status" : "alert"}
                className={cn(
                  "rounded-xl border p-3.5 text-xs flex items-start gap-2.5 backdrop-blur-xs",
                  displayedTestResult.connected
                    ? "bg-success/10 border-success/30 text-success"
                    : "bg-destructive/10 border-destructive/30 text-destructive"
                )}
              >
                {displayedTestResult.connected ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
                ) : (
                  <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                )}
                <div className="space-y-0.5 min-w-0 flex-1">
                  <div className="font-semibold flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-2">
                      <span>
                        {testMode === "image_generation"
                          ? displayedTestResult.connected
                            ? "图片生成测试成功"
                            : "图片生成测试失败"
                          : displayedTestResult.connected
                            ? "连接测试成功"
                            : "连接测试失败"}
                      </span>
                      {displayedTestResult.latency_ms !== undefined && (
                        <Badge variant="outline" className="font-mono text-xs">
                          {displayedTestResult.latency_ms}ms 延迟
                        </Badge>
                      )}
                    </div>
                    {testResult && (
                      <span className="text-xs font-normal text-muted-foreground">
                        {testMode === "image_generation" ? "仅生成测试预览，未保存图片" : "仅测试连通性，未自动保存"}
                      </span>
                    )}
                  </div>
                  <p className="break-words leading-relaxed opacity-90 font-mono text-xs">
                    {displayedTestResult.message}
                  </p>
                </div>
              </div>
            )}

            {/* 操作工具栏 */}
            <div className="flex flex-wrap items-center justify-between gap-2.5 pt-3 border-t border-border/70">
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={isTesting || createMutation.isPending || updateMutation.isPending}
                  onClick={handleTestConnection}
                  className="gap-1.5 h-9 px-3.5 text-sm"
                >
                  <Radio className={cn("h-3.5 w-3.5", isTesting && "animate-pulse text-primary")} />
                  <span>{isTesting && testMode === "connection" ? "正在测试连接…" : "测试连通性"}</span>
                </Button>

                {existingProvider && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={deleteMutation.isPending || isTesting}
                    onClick={() => setShowDeleteConfirm(true)}
                    className="text-destructive hover:bg-destructive/10 gap-1.5 h-9 px-3 text-sm"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    <span>删除配置</span>
                  </Button>
                )}
              </div>

              <Button
                type="submit"
                size="sm"
                disabled={isTesting || createMutation.isPending || updateMutation.isPending}
                className="gap-1.5 h-9 px-4 text-sm font-medium"
              >
                {createMutation.isPending || updateMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : isSavedNotice ? (
                  <Check className="h-4 w-4 text-success" />
                ) : (
                  <Check className="h-4 w-4" />
                )}
                <span>{isSavedNotice ? "已保存生效" : "保存配置"}</span>
              </Button>
            </div>

            {/* 未配置提醒 */}
            {summary && configuredProviderCount === 0 && (
              <div className="rounded-md border border-warning/30 bg-warning/5 p-3 text-xs text-warning space-y-1">
                <div className="flex items-center gap-1.5 font-medium">
                  <ShieldAlert className="h-3.5 w-3.5 shrink-0" />
                  <span>当前服务暂未配置可用 Provider</span>
                </div>
                <p className="text-muted-foreground leading-relaxed">
                  {category.impactText}
                </p>
              </div>
            )}
          </form>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="确认删除此 Provider 配置？"
        description={existingProvider ? `“${existingProvider.display_name}”的配置将被移除。` : undefined}
        confirmLabel="确认删除"
        variant="destructive"
        onConfirm={async () => {
          if (existingProvider) {
            const deletedProviderId = existingProvider.id;
            await deleteMutation.mutateAsync(deletedProviderId);
            const fallbackProvider =
              categoryProviders.find((provider) => provider.id !== deletedProviderId && provider.is_default) ||
              categoryProviders.find((provider) => provider.id !== deletedProviderId);
            const fallbackName = fallbackProvider?.provider_name || presets[0]?.name || "default";
            const fallbackPreset = presets.find((preset) => preset.name === fallbackName);
            setSelectedVendorName(fallbackName);
            loadVendorFields(fallbackName, fallbackProvider, fallbackPreset);
            if (!fallbackProvider) setIsDefault(true);
            toast("Provider 配置已删除。", "success");
          }
        }}
      />
    </div>
  );
}

// -----------------------------------------------------------------------------
// Component: Publishing Workspace (Douyin Creators Account Management)
// -----------------------------------------------------------------------------
function PublishingWorkspace() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [showQr, setShowQr] = React.useState(false);
  const [qrSessionId, setQrSessionId] = React.useState<string | null>(null);
  const [qrStatus, setQrStatus] = React.useState<string>("idle");
  const [qrCodeUrl, setQrCodeUrl] = React.useState<string | null>(null);
  const [qrError, setQrError] = React.useState<string | null>(null);
  const [qrAccountName, setQrAccountName] = React.useState("我的抖音号");

  const [checkingAccountId, setCheckingAccountId] = React.useState<string | null>(null);
  const [accountToDelete, setAccountToDelete] = React.useState<{ id: string; name: string } | null>(null);
  const [accountChecks, setAccountChecks] = React.useState<
    Record<string, { isValid: boolean; message: string }>
  >({});

  const { data: accounts = [], isLoading: isLoadingAccounts } = useQuery({
    queryKey: ["publishing-accounts"],
    queryFn: () => api.listAccounts("douyin"),
  });

  const deleteAccountMutation = useMutation({
    mutationFn: (id: string) => api.deleteAccount(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["publishing-accounts"] });
      queryClient.invalidateQueries({ queryKey: ["system-config-summary"] });
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      toast("抖音账号已解除绑定。", "success");
    },
    onError: (error: any) => toast(error?.message || "解绑账号失败。", "error"),
  });

  const completeQRMutation = useMutation({
    mutationFn: (data: { session_id: string; account_name: string; username?: string }) =>
      api.completeQRAuth(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["publishing-accounts"] });
      queryClient.invalidateQueries({ queryKey: ["system-config-summary"] });
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      setShowQr(false);
      setQrSessionId(null);
      setQrStatus("idle");
      setQrCodeUrl(null);
      toast("抖音创作者账号绑定成功！", "success");
    },
    onError: (error: any) => toast(error?.message || "保存账号授权失败。", "error"),
  });

  const handleStartQR = async () => {
    try {
      setShowQr(true);
      setQrStatus("initializing");
      setQrError(null);
      const res = await api.startQRAuth("douyin", true);
      setQrSessionId(res.session_id);
      setQrCodeUrl(res.qrcode_data_url || null);
      setQrStatus(res.status);
    } catch (e: any) {
      setQrStatus("error");
      setQrError(e.message || "获取登录二维码失败");
      toast(e.message || "获取登录二维码失败。", "error");
    }
  };

  React.useEffect(() => {
    if (!qrSessionId || !showQr) return;
    if (qrStatus === "success" || qrStatus === "error" || qrStatus === "timeout") return;

    const interval = setInterval(async () => {
      try {
        const res = await api.getQRAuthStatus(qrSessionId);
        setQrStatus(res.status);
        if (res.qrcode_data_url) setQrCodeUrl(res.qrcode_data_url);
        if (res.is_logged_in || res.status === "success") clearInterval(interval);
      } catch (e: any) {
        setQrStatus("error");
        setQrError(e.message || "登录状态轮询异常");
        clearInterval(interval);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [qrSessionId, showQr, qrStatus]);

  const handleCheckAccount = async (accountId: string) => {
    setCheckingAccountId(accountId);
    try {
      const res = await api.checkAccountStatus(accountId);
      setAccountChecks((prev) => ({
        ...prev,
        [accountId]: {
          isValid: res.is_valid,
          message: res.is_valid ? "Cookie 凭证有效，可正常自动发布" : res.error_message || "凭证已过期，请重新扫码",
        },
      }));
      queryClient.invalidateQueries({ queryKey: ["publishing-accounts"] });
      queryClient.invalidateQueries({ queryKey: ["system-config-summary"] });
      toast(res.is_valid ? "账号凭证正常有效。" : "凭证已过期，请重新扫码。", res.is_valid ? "success" : "warning");
    } catch (e: any) {
      setAccountChecks((prev) => ({
        ...prev,
        [accountId]: { isValid: false, message: e.message || "检测失败" },
      }));
      toast(e.message || "检测凭证通信失败。", "error");
    } finally {
      setCheckingAccountId(null);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="glass-card rounded-xl">
        <CardHeader className="pb-3 border-b border-border/70">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Share2 className="h-4 w-4 text-primary" />
                <CardTitle className="text-sm sm:text-base font-semibold text-foreground">
                  平台分发账号管理
                </CardTitle>
                <Badge variant="outline" className="font-mono text-xs">
                  已绑定 {accounts.length} 个
                </Badge>
              </div>
              <CardDescription className="text-xs text-muted-foreground">
                托管各平台创作者中心登录凭据，支持成片定时自动发布与排期调度。
              </CardDescription>
            </div>

            <Button
              type="button"
              size="sm"
              onClick={() => {
                if (showQr) {
                  setShowQr(false);
                  setQrSessionId(null);
                  setQrStatus("idle");
                } else {
                  handleStartQR();
                }
              }}
              className="gap-1.5 shrink-0"
            >
              <QrCode className="h-3.5 w-3.5" />
              <span>{showQr ? "收起扫码绑定" : "扫码绑定账号"}</span>
            </Button>
          </div>
        </CardHeader>

        <CardContent className="p-4 sm:p-5 space-y-4 text-xs">
          {/* QR Code Authorization Panel */}
          {showQr && (
            <div className="flex flex-col items-center gap-3 rounded-xl border border-border/70 bg-card/40 backdrop-blur-sm p-4 text-center">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Smartphone className="h-4 w-4 text-primary" />
                <span>请使用创作者手机客户端扫描下方二维码并在手机端确认授权</span>
              </div>

              {qrStatus === "initializing" && (
                <div className="flex flex-col items-center gap-2 py-4 text-xs text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin text-primary" />
                  <span>正在获取安全授权会话…</span>
                </div>
              )}

              {qrStatus === "pending" && qrCodeUrl && (
                <div className="flex flex-col items-center gap-2.5">
                  <img
                    src={qrCodeUrl}
                    alt="分发平台扫码登录二维码"
                    className="h-36 w-36 rounded-md border bg-white p-1 shadow-sm"
                  />
                  <div className="w-full max-w-[200px] space-y-1 text-left">
                    <label htmlFor="douyin-account-name" className="text-xs font-medium text-foreground">
                      账号备注名称
                    </label>
                    <Input
                      id="douyin-account-name"
                      value={qrAccountName}
                      onChange={(e) => setQrAccountName(e.target.value)}
                      placeholder="例如：主账号 / 科普矩阵1号"
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">登录成功后，系统将自动安全加密托管 Cookie。</p>
                </div>
              )}

              {qrStatus === "success" && (
                <div className="flex flex-col items-center gap-2 py-2 text-success">
                  <CheckCircle2 className="h-6 w-6" />
                  <span className="font-medium">扫码成功，会话凭证已就绪</span>
                  <Button
                    size="sm"
                    disabled={completeQRMutation.isPending}
                    onClick={() => {
                      if (qrSessionId) {
                        completeQRMutation.mutate({ session_id: qrSessionId, account_name: qrAccountName });
                      }
                    }}
                    className="gap-1.5"
                  >
                    {completeQRMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
                    <span>确认保存授权</span>
                  </Button>
                </div>
              )}

              {(qrStatus === "error" || qrStatus === "timeout") && (
                <div className="flex flex-col items-center gap-2 py-2 text-destructive">
                  <AlertCircle className="h-5 w-5" />
                  <span className="text-xs">{qrError || "二维码已过期或登录超时"}</span>
                  <Button size="sm" variant="outline" onClick={handleStartQR} className="gap-1.5">
                    <RefreshCw className="h-3 w-3" />
                    <span>重新获取二维码</span>
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* Accounts List */}
          {isLoadingAccounts ? (
            <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
              <span>正在加载授权账号列表…</span>
            </div>
          ) : accounts.length === 0 ? (
            <EmptyState
              icon={QrCode}
              title="尚未绑定任何平台分发账号"
              description="点击右上角“扫码绑定账号”，即可安全托管创作者凭据并开启定时自动发布。"
            />
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {accounts.map((acc: any) => {
                const check = accountChecks[acc.id];
                const isChecking = checkingAccountId === acc.id;

                return (
                  <div
                    key={acc.id}
                    className="flex flex-col justify-between gap-2.5 rounded-xl border border-border/70 glass-card p-3 hover:border-primary/40 hover:shadow-glass-hover transition-all duration-200"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-primary/10 font-bold font-mono text-xs text-primary">
                          {acc.account_name.slice(0, 1)}
                        </div>
                        <div className="min-w-0">
                          <div className="truncate text-xs font-semibold text-foreground">{acc.account_name}</div>
                          <div className="truncate text-xs font-mono text-muted-foreground">
                            {acc.username ? `@${acc.username}` : `ID: ${acc.id.slice(0, 8)}`}
                          </div>
                        </div>
                      </div>

                      <StatusBadge
                        tone={
                          check
                            ? check.isValid ? "success" : "destructive"
                            : acc.status === "active" ? "success" : "destructive"
                        }
                        label={
                          check
                            ? check.isValid ? "凭证正常" : "凭证失效"
                            : acc.status === "active" ? "凭证有效" : "待检测"
                        }
                        className="text-xs"
                      />
                    </div>

                    {check && !check.isValid && (
                      <p className="text-xs text-destructive leading-normal bg-destructive/10 p-1.5 rounded-lg">
                        {check.message}
                      </p>
                    )}

                    <div className="flex items-center justify-between gap-2 pt-2 border-t border-border/60">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={isChecking}
                        onClick={() => handleCheckAccount(acc.id)}
                        className="gap-1 h-7 text-xs px-2 text-muted-foreground hover:text-foreground"
                      >
                        <RefreshCw className={cn("h-3 w-3", isChecking && "animate-spin")} />
                        <span>{isChecking ? "检测中…" : "检查凭证"}</span>
                      </Button>

                      <IconButton
                        variant="ghost"
                        label={`解绑账号 ${acc.account_name}`}
                        className="h-7 w-7 text-muted-foreground/60 hover:text-destructive hover:bg-destructive/10"
                        onClick={() => setAccountToDelete({ id: acc.id, name: acc.account_name })}
                        disabled={deleteAccountMutation.isPending}
                      >
                        <Trash2 className="h-3 w-3" />
                      </IconButton>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={Boolean(accountToDelete)}
        onOpenChange={(open) => {
          if (!open) setAccountToDelete(null);
        }}
        title="确认解绑分发账号？"
        description={accountToDelete ? `账号“${accountToDelete.name}”的授权 Cookie 将被移除，定时发布任务将暂停。` : undefined}
        confirmLabel="确认解绑"
        variant="destructive"
        onConfirm={async () => {
          if (accountToDelete) await deleteAccountMutation.mutateAsync(accountToDelete.id);
        }}
      />
    </div>
  );
}

// -----------------------------------------------------------------------------
// Component: System & Storage Diagnostics Workspace (Focus Panel for Diagnostics)
// -----------------------------------------------------------------------------
function SystemDiagnosticsWorkspace({ summary }: { summary?: SystemConfigSummary }) {
  const { toast } = useToast();

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast(`${label} 已复制到剪贴板。`, "success");
  };

  if (!summary) {
    return (
      <Card className="border-border/80 bg-card p-4 text-xs text-muted-foreground">
        <span>正在读取系统与存储环境参数…</span>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card className="glass-card rounded-xl">
        <CardHeader className="pb-3 border-b border-border/70">
          <div className="flex items-center gap-2">
            <HardDrive className="h-4 w-4 text-primary" />
            <CardTitle className="text-sm sm:text-base font-semibold text-foreground">
              底层运行环境与存储诊断
            </CardTitle>
          </div>
          <CardDescription className="text-xs text-muted-foreground">
            运行状态：持久化 SQLite 数据库、并发工作线程池与素材目录绝对路径。
          </CardDescription>
        </CardHeader>

        <CardContent className="p-4 sm:p-5 space-y-4 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            {/* Storage & Database Card */}
            <div className="rounded-xl border border-border/70 bg-card/40 backdrop-blur-sm p-3.5 space-y-2.5">
              <div className="flex items-center gap-2 font-semibold text-foreground text-xs">
                <Database className="h-3.5 w-3.5 text-primary" />
                <span>持久化存储与数据库</span>
              </div>

              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between gap-2 border-b border-border/50 pb-2">
                  <span className="text-muted-foreground">SQLite 数据库</span>
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-xs text-foreground select-all truncate max-w-[180px]">
                      {summary.storage.database}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleCopy(summary.storage.database, "数据库路径")}
                      className="text-muted-foreground hover:text-foreground cursor-pointer p-0.5"
                      title="复制路径"
                    >
                      <Copy className="h-3 w-3" />
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between gap-2 border-b border-border/50 pb-2">
                  <span className="text-muted-foreground">并发工作线程</span>
                  <span className="font-mono text-foreground font-semibold">
                    {summary.storage.worker_count} 线程
                  </span>
                </div>

                <div className="flex items-center justify-between gap-2">
                  <span className="text-muted-foreground">任务超时阈值</span>
                  <span className="font-mono text-foreground">
                    {summary.storage.task_timeout_seconds} 秒
                  </span>
                </div>
              </div>
            </div>

            {/* Storage Directory Card */}
            <div className="rounded-xl border border-border/70 bg-card/40 backdrop-blur-sm p-3.5 space-y-2.5">
              <div className="flex items-center gap-2 font-semibold text-foreground text-xs">
                <Cpu className="h-3.5 w-3.5 text-primary" />
                <span>生成引擎与工作目录</span>
              </div>

              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between gap-2 border-b border-border/50 pb-2">
                  <span className="text-muted-foreground">素材绝对路径</span>
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-xs text-muted-foreground truncate max-w-[180px]" title={summary.storage.storage_dir}>
                      {summary.storage.storage_dir}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleCopy(summary.storage.storage_dir, "素材目录")}
                      className="text-muted-foreground hover:text-foreground cursor-pointer p-0.5"
                      title="复制路径"
                    >
                      <Copy className="h-3 w-3" />
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between gap-2 border-b border-border/50 pb-2">
                  <span className="text-muted-foreground">诊断运行状态</span>
                  <span className="flex items-center gap-1 text-success font-medium">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    <span>系统正常</span>
                  </span>
                </div>

                <div className="flex items-center justify-between gap-2">
                  <span className="text-muted-foreground">架构模式</span>
                  <span className="font-mono text-primary font-medium">Local</span>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
