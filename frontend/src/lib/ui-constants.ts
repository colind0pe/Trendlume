import type { StatusTone } from "@/components/ui/status-badge";
import {
  CONTENT_MODE_VALUES,
  type ContentMode,
  type CreativeAngle,
  type ProductionMode,
  type TrendFrequency,
  type VisualRole,
} from "@/lib/types";

export { CONTENT_MODE_VALUES, PRODUCTION_MODE_VALUES } from "@/lib/types";

export interface ProductionModeSpec {
  label: string;
  description: string;
  badge?: string;
}

export const PRODUCTION_MODE_SPECS: Record<ProductionMode, ProductionModeSpec> =
  {
    knowledge: {
      label: "知识视频",
      description: "围绕主题或已有文案生成视频。",
    },
    commerce: {
      label: "商品视频",
      description: "使用商品资料和素材生成视频。",
      badge: "Beta",
    },
    drama: {
      label: "短剧",
      description: "使用已审批的人物、地点和道具制作剧集。",
      badge: "Beta",
    },
  };

export const GENRE_OPTIONS = [
  {
    value: "auto",
    label: "自动匹配",
    desc: "根据标题、文案和调研内容自动选择最合适的表达方向",
  },
  {
    value: "science_tech",
    label: "科普解说与前沿科技",
    desc: "用清晰的比喻解释复杂机制，保持严谨易懂",
  },
  {
    value: "business_wealth",
    label: "商业财经与财富认知",
    desc: "拆解商业逻辑，提炼市场变化和行动启发",
  },
  {
    value: "emotion_growth",
    label: "个人成长与情感心理",
    desc: "表达真实情绪，提供温和而具体的成长视角",
  },
  {
    value: "culture_history",
    label: "人文历史与传统文化",
    desc: "讲好历史故事，呈现文化脉络和审美细节",
  },
  {
    value: "humor_meme",
    label: "幽默段子与趣味吐槽",
    desc: "节奏明快，使用自然口语和反差表达",
  },
  {
    value: "product_review",
    label: "产品测评与实用干货",
    desc: "围绕真实场景，清楚说明差异和使用价值",
  },
  {
    value: "general",
    label: "通用随笔与日常短文",
    desc: "亲切自然，像朋友分享一样直接清楚",
  },
] as const;

export const VISUAL_ROLE_OPTIONS: ReadonlyArray<{
  value: VisualRole;
  label: string;
  description: string;
}> = [
  {
    value: "concept",
    label: "概念",
    description: "解释一个抽象概念或核心定义",
  },
  { value: "process", label: "过程", description: "展示步骤、机制或因果链" },
  { value: "comparison", label: "对比", description: "并列差异、误区或选择" },
  { value: "timeline", label: "时间线", description: "按时间顺序呈现演变" },
  { value: "data", label: "数据", description: "突出数字、趋势或图表关系" },
  { value: "example", label: "例子", description: "把主张落到具体场景" },
  { value: "quote", label: "引语", description: "突出原话、定义或证据摘录" },
  {
    value: "b_roll",
    label: "补充画面",
    description: "提供语境，不承载新的关键结论",
  },
  {
    value: "product_shot",
    label: "商品主体",
    description: "使用商品库中的真实商品素材",
  },
  {
    value: "context",
    label: "使用场景",
    description: "说明商品所处的真实语境",
  },
  {
    value: "benefit",
    label: "核心价值",
    description: "呈现已有事实支持的价值",
  },
  { value: "proof", label: "事实依据", description: "承载可追溯的商品主张" },
  {
    value: "cta",
    label: "行动引导",
    description: "引导核对、了解或下一步动作",
  },
];

export const CREATIVE_ANGLE_OPTIONS: ReadonlyArray<{
  value: CreativeAngle;
  label: string;
  description: string;
}> = [
  {
    value: "direct",
    label: "直接介绍",
    description: "先把商品和已确认信息讲清楚",
  },
  {
    value: "pain_point",
    label: "痛点切入",
    description: "从用户正在面对的需求进入",
  },
  { value: "use_case", label: "使用场景", description: "围绕真实使用语境展开" },
  {
    value: "demo",
    label: "功能演示",
    description: "用商品素材演示如何理解和使用",
  },
  {
    value: "review",
    label: "真实测评",
    description: "区分事实、体验与待确认信息",
  },
  {
    value: "comparison",
    label: "对比选择",
    description: "按明确维度帮助用户核对选择",
  },
  { value: "story", label: "故事叙事", description: "用需求变化串起商品事实" },
];

export const SCENE_COUNT_MIN = 8;
export const SCENE_COUNT_MAX = 20;
export const SCENE_COUNT_PRESETS = [
  { count: 8, label: "8 镜", desc: "标准叙事 ~32s" },
  { count: 12, label: "12 镜", desc: "完整叙事 ~48s" },
  { count: 14, label: "14 镜", desc: "深度拆解 ~56s" },
  { count: 18, label: "18 镜", desc: "细节展开 ~72s" },
  { count: 20, label: "20 镜", desc: "完整长片 ~80s" },
] as const;

export const HOOK_OPTIONS = [
  { value: "auto", label: "自动匹配" },
  { value: "bold_claim", label: "颠覆认知" },
  { value: "curiosity_gap", label: "悬念反问" },
  { value: "mistake_warning", label: "避坑提醒" },
  { value: "story_twist", label: "故事反转" },
  { value: "pain_point", label: "直击痛点" },
] as const;

export const SPEED_PRESETS = [0.8, 1.0, 1.1, 1.2, 1.5] as const;

export const TREND_FREQUENCY_OPTIONS: ReadonlyArray<{
  value: TrendFrequency;
  label: string;
}> = [
  { value: "15m", label: "每 15 分钟" },
  { value: "1h", label: "每小时" },
  { value: "6h", label: "每 6 小时" },
  { value: "24h", label: "每天" },
];

export const TREND_FREQUENCY_LABELS = Object.fromEntries(
  TREND_FREQUENCY_OPTIONS.map((option) => [option.value, option.label]),
) as Record<TrendFrequency, string>;

export const STYLE_PRESET_OPTIONS = [
  {
    value: "stick_figure",
    label: "简约火柴人",
    desc: "黑白线条与纯白留白，适合概念拆解和流程说明",
  },
  {
    value: "minimalist_line_art",
    label: "简笔画插画",
    desc: "流畅手绘轮廓与少量色彩，适合知识卡点和日常解释",
  },
  {
    value: "chinese_ink",
    label: "中国水墨国潮",
    desc: "水墨笔触与东方留白，适合历史文化和情绪叙事",
  },
  {
    value: "cinematic_real",
    label: "电影写实摄影",
    desc: "真实材质、浅景深与戏剧光影，适合人物、产品和纪实画面",
  },
  {
    value: "animation",
    label: "现代动画",
    desc: "主体轮廓清晰、配色协调、动作易读，适合故事化和科普表达",
  },
  {
    value: "custom",
    label: "自定义风格",
    desc: "手动指定风格、光线、材质和构图",
  },
] as const;

export const VOICE_OPTIONS = [
  {
    value: "zh-CN-YunjianNeural",
    label: "云健 · 沉稳磁性男声（推荐、纪录片、科普）",
  },
  {
    value: "zh-CN-XiaoxiaoNeural",
    label: "晓晓 · 亲切温和女声（日常播报、故事抒情）",
  },
  {
    value: "zh-CN-YunxiNeural",
    label: "云希 · 活力年轻男声（短视频、快节奏）",
  },
  {
    value: "zh-CN-XiaoyiNeural",
    label: "晓伊 · 年轻知性女声（生活感悟、产品介绍）",
  },
  { value: "zh-CN-YunyangNeural", label: "云扬 · 专业新闻男声（权威、严谨）" },
  {
    value: "zh-TW-HsiaoChenNeural",
    label: "晓臻 · 台湾国语女声（温柔、治愈）",
  },
  { value: "en-US-GuyNeural", label: "Guy · 美式英语男声（英文旁白）" },
] as const;

export const ASSET_TYPE_LABELS: Record<string, string> = {
  image: "图片",
  video: "视频",
  audio: "配音",
  bgm: "背景音乐",
  font: "字体",
};

export const TEMPLATE_TYPE_LABELS: Record<string, string> = {
  image: "图片",
  video: "视频",
  static: "文字",
  asset: "素材",
};

export type ContentModeGroup = "ai" | "real" | "text";
export type ContentModeSource = "ai" | "online" | "uploaded" | "text";
export type ContentModeVisualKind = "image" | "video" | "none";

export interface ContentModeSpec {
  group: ContentModeGroup;
  label: string;
  /** One-line hint for the creation form; keep detailed semantics in description. */
  selectionHint: string;
  description: string;
  sourceKind: ContentModeSource;
  visualKind: ContentModeVisualKind;
  requiresSourceAsset: boolean;
  usesVisualPrompt: boolean;
  supportsSceneRetry: boolean;
}

/**
 * User-facing mode semantics. Keep labels and progressive-disclosure copy in one place.
 */
export const CONTENT_MODE_SPECS: Record<ContentMode, ContentModeSpec> = {
  generated_image: {
    group: "ai",
    label: "智能生成图片",
    selectionHint: "根据分镜生成图片",
    description: "根据分镜提示词生成静态画面，稳定、快速，适合大多数普通任务。",
    sourceKind: "ai",
    visualKind: "image",
    requiresSourceAsset: false,
    usesVisualPrompt: true,
    supportsSceneRetry: true,
  },
  generated_video: {
    group: "ai",
    label: "智能生成视频",
    selectionHint: "根据分镜生成视频片段",
    description: "为每个分镜生成动态视频片段，通常耗时更长、成本更高。",
    sourceKind: "ai",
    visualKind: "video",
    requiresSourceAsset: false,
    usesVisualPrompt: true,
    supportsSceneRetry: true,
  },
  online_asset: {
    group: "real",
    label: "素材库视频",
    selectionHint: "从已配置素材库获取实拍视频",
    description:
      "从已配置的素材库获取实拍视频，不自动替换为生成画面。",
    sourceKind: "online",
    visualKind: "video",
    requiresSourceAsset: false,
    usesVisualPrompt: false,
    supportsSceneRetry: true,
  },
  uploaded_asset: {
    group: "real",
    label: "我的素材",
    selectionHint: "使用我的图片或视频",
    description:
      "使用项目中已有或上传的图片、视频，用户绑定的素材不会被自动替换。",
    sourceKind: "uploaded",
    visualKind: "none",
    requiresSourceAsset: true,
    usesVisualPrompt: false,
    supportsSceneRetry: false,
  },
  static: {
    group: "text",
    label: "文字排版",
    selectionHint: "用文字排版完成画面",
    description: "使用文字卡片和动态版式完成画面，不需要图片或视频素材。",
    sourceKind: "text",
    visualKind: "none",
    requiresSourceAsset: false,
    usesVisualPrompt: false,
    supportsSceneRetry: false,
  },
};

const CONTENT_MODE_GROUP_ORDER: ReadonlyArray<{
  value: ContentModeGroup;
  label: string;
}> = [
  { value: "ai", label: "智能生成" },
  { value: "real", label: "真实素材" },
  { value: "text", label: "文字排版" },
];

export const CONTENT_MODE_GROUPS: ReadonlyArray<{
  value: ContentModeGroup;
  label: string;
  modes: ReadonlyArray<ContentMode>;
}> = CONTENT_MODE_GROUP_ORDER.map((group) => ({
  ...group,
  modes: CONTENT_MODE_VALUES.filter(
    (mode) => CONTENT_MODE_SPECS[mode].group === group.value,
  ),
}));

export function isContentMode(value: unknown): value is ContentMode {
  return (
    typeof value === "string" &&
    CONTENT_MODE_VALUES.includes(value as ContentMode)
  );
}

export function getContentModeSpec(
  value: unknown,
): ContentModeSpec | undefined {
  return isContentMode(value) ? CONTENT_MODE_SPECS[value] : undefined;
}

export const CONTENT_MODE_LABELS: Record<ContentMode, string> =
  Object.fromEntries(
    Object.entries(CONTENT_MODE_SPECS).map(([mode, spec]) => [
      mode,
      spec.label,
    ]),
  ) as Record<ContentMode, string>;

export const TEMPLATE_NAMES: Record<string, string> = {
  // 9:16 (竖屏)
  image_gallery_matted: "画廊留白展卡",
  image_editorial_warm: "暖调人文社论",
  image_frosted_ambient: "磨砂微光视窗",
  static_editorial_quote: "质感金句引言",
  static_bulletin_flash: "动态快讯简报",
  video_cinema_scope: "电影宽幅遮幅",
  video_full_overlay: "沉浸全屏字幕",

  // 16:9 (横屏)
  image_wide_minimal: "横屏极简视窗",
  image_wide_cinema: "横屏电影胶片",
  image_wide_editorial: "横屏深度专栏",
  static_wide_bulletin: "横屏焦点快报",
  video_wide_full: "横屏全景沉浸",
  video_wide_cinema_scope: "横屏影院宽幅",

  // 1:1 (正方)
  image_square_matted: "正方雅致留白",
  image_square_editorial: "正方精选社论",
  image_square_frosted: "正方磨砂卡片",
  static_square_quote: "正方金句卡片",
  video_square_full: "正方全景画幅",
  video_square_card: "正方杂志动效",
};

export const TEMPLATE_PARAM_LABELS: Record<string, string> = {
  author: "创作者署名",
  describe: "副标题说明",
  brand: "品牌标识",
  tag: "标签文案",
  source: "来源引文",
  theme_color: "主题配色",
  title: "主标题",
  subtitle: "副标题",
  accent_color: "强调色彩",
  background_color: "背景色彩",
  font_size: "字号大小",
  date: "日期标注",
};

export function formatTemplateName(
  idOrName?: string | null,
  fallback?: string | null,
): string {
  if (!idOrName) return fallback || "默认排版模板";
  if (TEMPLATE_NAMES[idOrName]) return TEMPLATE_NAMES[idOrName];
  // Check if string contains underscore (raw template ID)
  const normalizedKey = idOrName.toLowerCase().trim();
  if (TEMPLATE_NAMES[normalizedKey]) return TEMPLATE_NAMES[normalizedKey];
  return fallback || idOrName;
}

export function formatParamLabel(
  paramName?: string | null,
  fallback?: string | null,
): string {
  if (!paramName) return fallback || "";
  const key = paramName.toLowerCase().trim();
  if (TEMPLATE_PARAM_LABELS[key]) return TEMPLATE_PARAM_LABELS[key];
  return (
    fallback ||
    paramName.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

export const PLATFORM_LABELS: Record<string, string> = {
  douyin: "抖音",
};

export const TASK_STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  pending: "待处理",
  queued: "排队中",
  running: "生成中",
  retrying: "重试中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export const PUBLISH_STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  pending: "等待生成",
  scheduled: "已排期",
  queued: "排队中",
  publishing: "发布中",
  published: "已发布",
  failed: "失败",
  cancelled: "已取消",
  missed: "已错过",
  uncertain: "待确认",
};

export const PROVIDER_STATUS_LABELS: Record<string, string> = {
  ready: "已就绪",
  not_tested: "未测试",
  not_configured: "未配置",
  unconfigured: "未配置",
  failed: "连接失败",
  disabled: "已停用",
};

export function getTaskStatusTone(status?: string): StatusTone {
  switch (status) {
    case "completed":
      return "success";
    case "failed":
      return "destructive";
    case "running":
    case "retrying":
    case "queued":
    case "pending":
      return "primary";
    default:
      return "neutral";
  }
}

export function getPublishStatusTone(status?: string): StatusTone {
  switch (status) {
    case "published":
      return "success";
    case "failed":
      return "destructive";
    case "missed":
    case "uncertain":
      return "warning";
    case "publishing":
    case "queued":
    case "scheduled":
      return "primary";
    default:
      return "neutral";
  }
}

export function getProviderStatusTone(status?: string): StatusTone {
  switch (status) {
    case "ready":
      return "success";
    case "failed":
      return "destructive";
    case "not_tested":
    case "not_configured":
    case "unconfigured":
      return "warning";
    default:
      return "neutral";
  }
}

export const ACTIVE_TASK_STATUSES = new Set([
  "pending",
  "queued",
  "running",
  "retrying",
]);

export function isTaskActive(task: {
  production_status?: string;
  latest_job?: { status?: string } | null;
}) {
  return ACTIVE_TASK_STATUSES.has(
    task.latest_job?.status || task.production_status || "",
  );
}
