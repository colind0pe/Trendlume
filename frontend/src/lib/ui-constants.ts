import type { StatusTone } from "@/components/ui/status-badge";

export const GENRE_OPTIONS = [
  { value: "auto", label: "自动匹配", desc: "根据标题、文案和调研内容自动选择最合适的表达方向" },
  { value: "science_tech", label: "科普解说与前沿科技", desc: "用清晰的比喻解释复杂机制，保持严谨易懂" },
  { value: "business_wealth", label: "商业财经与财富认知", desc: "拆解商业逻辑，提炼市场变化和行动启发" },
  { value: "emotion_growth", label: "个人成长与情感心理", desc: "表达真实情绪，提供温和而具体的成长视角" },
  { value: "culture_history", label: "人文历史与传统文化", desc: "讲好历史故事，呈现文化脉络和审美细节" },
  { value: "humor_meme", label: "幽默段子与趣味吐槽", desc: "节奏明快，使用自然口语和反差表达" },
  { value: "product_review", label: "产品测评与实用干货", desc: "围绕真实场景，清楚说明差异和使用价值" },
  { value: "general", label: "通用随笔与日常短文", desc: "亲切自然，像朋友分享一样直接清楚" },
] as const;

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

export const STYLE_PRESET_OPTIONS = [
  { value: "stick_figure", label: "简约火柴人", desc: "黑白线条与纯白留白，适合概念拆解和流程说明" },
  { value: "minimalist_line_art", label: "简笔画插画", desc: "流畅手绘轮廓与少量色彩，适合知识卡点和日常解释" },
  { value: "chinese_ink", label: "中国水墨国潮", desc: "水墨笔触与东方留白，适合历史文化和情绪叙事" },
  { value: "cinematic_real", label: "电影写实摄影", desc: "真实材质、浅景深与戏剧光影，适合人物、产品和纪实画面" },
  { value: "animation", label: "现代动画", desc: "主体轮廓清晰、配色协调、动作易读，适合故事化和科普表达" },
  { value: "custom", label: "自定义风格", desc: "手动指定风格、光线、材质和构图" },
] as const;

export const VOICE_OPTIONS = [
  { value: "zh-CN-YunjianNeural", label: "云健 · 沉稳磁性男声（推荐、纪录片、科普）" },
  { value: "zh-CN-XiaoxiaoNeural", label: "晓晓 · 亲切温和女声（日常播报、故事抒情）" },
  { value: "zh-CN-YunxiNeural", label: "云希 · 活力年轻男声（短视频、快节奏）" },
  { value: "zh-CN-XiaoyiNeural", label: "晓伊 · 年轻知性女声（生活感悟、产品介绍）" },
  { value: "zh-CN-YunyangNeural", label: "云扬 · 专业新闻男声（权威、严谨）" },
  { value: "zh-TW-HsiaoChenNeural", label: "晓臻 · 台湾国语女声（温柔、治愈）" },
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

export const CONTENT_MODE_LABELS: Record<string, string> = {
  generated_image: "生成图片",
  generated_video: "生成视频",
  online_asset: "在线素材",
  static: "纯文字静态",
  uploaded_asset: "上传素材",
};

export const STAGE_LABELS: Record<string, string> = {
  topic: "选题规划",
  planning: "选题策划",
  research: "全网调研",
  script: "剧本编排",
  storyboard: "分镜拆解",
  scenes: "分镜拆解",
  visuals: "画面素材",
  assets: "画面素材",
  voice: "旁白配音",
  tts: "旁白配音",
  render: "视觉渲染",
  subtitles: "动态字幕",
  composition: "视频合成",
  assembly: "视频合成",
  export: "成片导出",
  completed: "已完成",
  ready: "已就绪",
  queued: "排队中",
};

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

  // 常用兼容别名与历史模板
  default_portrait: "画廊留白展卡",
  default_landscape: "横屏极简视窗",
  default_square: "正方雅致留白",
  video_default_portrait: "沉浸全屏字幕",
  video_default_landscape: "横屏全景沉浸",
  video_default_square: "正方全景画幅",
  image_default: "画廊留白展卡",
  video_default: "数字演播视窗",
  static_default: "质感金句引言",
  video_studio_stream: "数字演播视窗",
  video_split_stack: "双层分屏视窗",
  video_healing: "治愈舒缓视窗",
  asset_default: "通用素材展卡",
  image_modern: "现代先锋版式",
  image_purple: "霓虹夜幕紫调",
  image_neon: "赛博霓虹幻彩",
  image_elegant: "雅致典藏版式",
  image_cartoon: "活力卡通动漫",
  image_book: "书卷人文质感",
  image_blur_card: "毛玻璃质感卡",
  image_full: "纯粹全屏原画",
  image_healing: "治愈插画卡片",
  image_simple_black: "极简玄黑版式",
  image_simple_line_drawing: "极简线条画风",
  image_studio_aurora: "极光工坊视效",
  static_ambient_manifesto: "氛围宣言大字",
  static_frosted_insight: "磨砂深度洞察",
  static_landscape_card: "横屏画卡语录",
  static_square_card: "正方语录画卡",
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

export function formatTemplateName(idOrName?: string | null, fallback?: string | null): string {
  if (!idOrName) return fallback || "默认排版模板";
  if (TEMPLATE_NAMES[idOrName]) return TEMPLATE_NAMES[idOrName];
  // Check if string contains underscore (raw template ID)
  const normalizedKey = idOrName.toLowerCase().trim();
  if (TEMPLATE_NAMES[normalizedKey]) return TEMPLATE_NAMES[normalizedKey];
  return fallback || idOrName;
}

export function formatParamLabel(paramName?: string | null, fallback?: string | null): string {
  if (!paramName) return fallback || "";
  const key = paramName.toLowerCase().trim();
  if (TEMPLATE_PARAM_LABELS[key]) return TEMPLATE_PARAM_LABELS[key];
  return fallback || paramName.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatStageName(stageKey?: string | null): string {
  if (!stageKey) return "执行中";
  const key = stageKey.toLowerCase().trim();
  return STAGE_LABELS[key] || stageKey;
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

export const ACTIVE_TASK_STATUSES = new Set(["pending", "queued", "running", "retrying"]);

export function isTaskActive(task: { status?: string; active_job?: { status?: string } | null }) {
  return ACTIVE_TASK_STATUSES.has(task.active_job?.status || task.status || "");
}
