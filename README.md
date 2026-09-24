# 🎬 Trendlume

> 从一个主题或现成文案开始，做出可发布的短视频，并保留对每个镜头的修改与重试权。

**由 AI 生成初稿，创作者始终保留控制权。** Trendlume 是一个面向不同内容赛道的开源自动化短视频生产工作台。在同一个本地工作台中，知识科普、电商带货与故事短剧三条赛道拥有各自专属的策划入口与生产流程，并共用底层的画面生成、语音合成、字幕对齐与本地视频渲染能力。

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=flat-square)](LICENSE) [![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/) [![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/) [![Next.js 14](https://img.shields.io/badge/Next.js-14-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/) [![React 18](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/) [![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://www.sqlite.org/) [![FFmpeg](https://img.shields.io/badge/FFmpeg-6.0+-007808?style=flat-square&logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)

<p align="center">
  <b>简体中文</b> | <a href="README_EN.md">English</a>
</p>

<p align="center">
  <img src="docs/assets/trendlume-readme-hero.png" alt="Trendlume 面向不同内容赛道的视频生产工作台" />
</p>

## 三种生产模式

| 赛道模式 | 适用场景与起点 | 专属生产流程 |
| --- | --- | --- |
| **知识科普** | 主题灵感、全网热点选题或现成文案 | 事实资料调研、知识策划卡、脚本大纲拆解、故事板工作室镜头级精修 |
| **电商带货** | 商品参数事实与已选创意方案 | 商品真实属性清单、卖点约束校验、商业分镜、真实商品素材强锁定与合规质检 |
| **故事短剧** | 故事创意或现有剧本文案 | 剧作世界观设定集、角色与场景库（支持多图角色一致性）、分集规划、逐镜头分镜、审核批准闸门 |

三条赛道共用已配置的大语言模型、画面生成、语音合成服务与本地 FFmpeg 渲染引擎。为避免不必要的试错成本，**电商带货模式**会严格校验真实商品素材，商品主体镜头强制锁定实拍图，杜绝算法虚构商品外观；**故事短剧模式**则设有审核闸门，只有在分镜脚本与镜头通过确认后，才会真正触发媒体生成任务。

## 它能为你做什么

- **按赛道组织生产**：创建项目时直接指定知识科普、电商带货或故事短剧赛道。工作区界面只呈现当前赛道相关的输入项与检查规则，告别通用模板繁杂且不契合的配置。
- **镜头级可视化微调**：生成的视频不是不可控的黑盒。在分镜故事板中，你可以逐个镜头试听配音、微调旁白文字、替换画面或局部重绘。修改单个镜头的素材，绝不会打乱其他镜头的节奏。
- **画面来源自由组合**：支持调用本地 ComfyUI，或火山方舟、阿里云百炼、Google Gemini 与 Veo 等云端图像与视频生成模型，也支持检索 Pexels 高清免版税素材、生成纯文字排版卡片，或直接绑定本地实拍素材。
- **音画字幕自动对齐**：内置免费可用的微软语音合成服务（Edge-TTS），也支持接入火山引擎豆包语音。系统会根据生成的实际音频时长自动计算镜头时长，并排布双语或单语字幕，内置 19 款涵盖 9:16 竖屏、16:9 横屏及 1:1 方形的排版模板。
- **断点续跑与局部重试**：流水线每个阶段自动存盘入库。网络抖动或程序意外退出后可随时继续；重新生成单镜画面无需重新合成整部视频。
- **直连抖音创作者中心**：手机扫码即可授权绑定抖音账号，在发布中心直接填写标题、添加话题标签、选择封面帧，支持即时发布与定时排期。

## 生产工作流

```text
知识科普: 选题 / 热点 / 文案 ──> 资料调研与策划卡 ──> 脚本大纲拆解 ──> 故事板工作室 ──> 镜头精修与本地合成
电商带货: 商品属性事实 ──> 创意方案 ──> 实拍素材强锁定 ──> 商业分镜 ──> 发布前合规质检 ──> 视频合成
故事短剧: 故事想法 / 剧本 ──> 剧作设定集 ──> 角色与场景库 ──> 分集与分镜 ──> 审核批准 ──> 媒体制作
                                                                                   │
                                            共用外部模型服务集成、局部重试与本地渲染引擎 ───────┘
```

- **全网热点跟踪**：内置热点中心实时聚合主流平台公开热榜，结合项目偏好自动分析切入角度与大纲，确认后一键转为知识科普视频任务。
- **自带脚本直通**：已有现成文案或剧本文本时，系统会自动跳过前期的资料检索阶段，直接进入分镜拆解与排版。
- **真实素材锁定**：带货或纪实类内容可优先绑定实拍素材，系统会按照旁白语义自动关联或下载，杜绝画面无中生有。

## 界面预览

| 01. 工作台总览 |
| :---: |
| <a href="docs/assets/screenshots/01-workbench-dashboard.png"><img src="docs/assets/screenshots/01-workbench-dashboard.png" width="100%" alt="工作台总览" /></a> |
| 项目空间、活跃流水线与最新成片动态监控 |

| 02. 新建视频任务 | 03. 故事板工作室 |
| :---: | :---: |
| <a href="docs/assets/screenshots/02-create-task-modal.png"><img src="docs/assets/screenshots/02-create-task-modal.png" width="100%" alt="新建视频任务" /></a> | <a href="docs/assets/screenshots/03-storyboard-editor.png"><img src="docs/assets/screenshots/03-storyboard-editor.png" width="100%" alt="故事板工作室" /></a> |
| 知识策划卡、选题拆解与画幅模板选择 | 流水线全阶段追踪、实时视频预览与模板微调 |

| 04. 镜头级分镜精修 | 05. 任务流水线中心 |
| :---: | :---: |
| <a href="docs/assets/screenshots/04-storyboard-scenes.png"><img src="docs/assets/screenshots/04-storyboard-scenes.png" width="100%" alt="镜头级分镜精修" /></a> | <a href="docs/assets/screenshots/05-task-pipeline.png"><img src="docs/assets/screenshots/05-task-pipeline.png" width="100%" alt="任务流水线中心" /></a> |
| 逐镜头调整旁白、试听配音、重新生成与素材绑定 | 集中管理各项目的生成任务，支持暂停、恢复与失败重试 |

| 06. 抖音发布中心 | 07. 系统模型与服务配置 |
| :---: | :---: |
| <a href="docs/assets/screenshots/06-douyin-publishing.png"><img src="docs/assets/screenshots/06-douyin-publishing.png" width="100%" alt="抖音发布中心" /></a> | <a href="docs/assets/screenshots/07-system-settings.png"><img src="docs/assets/screenshots/07-system-settings.png" width="100%" alt="系统设置" /></a> |
| 扫码授权绑定创作者账号，配置标题标签与定时排期 | 集中管理与测试大语言模型、生图、视频、素材及语音合成渠道 |

## 支持的模型与服务

所有服务均在「系统设置」中配置与测试。密钥在本地加密存储，应用日志中会自动脱敏。

| 服务类别 | 支持服务与模型 | 说明与前置条件 |
| --- | --- | --- |
| **全网热点** | 七大平台公开热榜 | 覆盖微博、抖音、知乎、今日头条、小红书、哔哩哔哩、百度，基于公开接口采集，无需平台账号或登录凭据 |
| **大语言模型** | DeepSeek、OpenAI 兼容接口、Anthropic Claude、Cloudflare Workers AI、本地 Ollama | 日常创作推荐使用 DeepSeek 或本地私有化部署的 Ollama，成本经济可控 |
| **事实检索** | Tavily 全网检索 | 用于联网获取事实依据与背景资料，需配置 Tavily 访问密钥（可选） |
| **图像生成** | 本地 ComfyUI (Flux / SDXL 等)<br>火山方舟 Seedream<br>阿里云百炼 Qwen Image 3.0 Pro<br>Google Gemini Image<br>RunningHub 云端工作流 | 本地具备独立显卡可直连 ComfyUI；云端可选用火山方舟、阿里云百炼（支持角色与场景参考图）或 Google（支持多图角色一致性）；RunningHub 支持执行线上托管的 ComfyUI 工作流 |
| **视频生成** | 本地 ComfyUI (Wan 2.1 / CogVideoX)<br>火山方舟 Seedance<br>阿里云百炼 Wan 2.7<br>Google Veo 3.1<br>RunningHub 视频工作流 | 本地生成需具备相应显存；云端支持火山方舟 Seedance、阿里云百炼 Wan 2.7（图生视频与文生视频）、Google Veo 3.1（支持参考图与首尾帧插值）或 RunningHub 节点映射 |
| **素材库视频** | Pexels 免版税素材 | 免费高清实拍视频库，需配置 Pexels 访问密钥（可选） |
| **语音合成** | 微软语音服务 Edge-TTS（内置免费）<br>火山引擎豆包语音 | 快速上手首选内置的微软语音，无需注册账号或填写密钥；追求更高拟真度可接入火山引擎豆包语音 |
| **发布渠道** | 抖音创作者中心 | 官方网页扫码授权，支持即时发布与定时排期发布 |

## 快速开始

### 方式一：独立运行包（开箱即用，推荐）

无需在宿主机安装 Python、Node.js、FFmpeg 或 Docker，下载解压即可运行：

1. **下载**：前往 **GitHub Releases** 下载对应系统的压缩包（Windows 为 ZIP，macOS / Linux 为 tar.gz；可比对 `.sha256` 校验和）。
2. **启动**：解压并运行 `Trendlume` 可执行文件（macOS / Linux 若遇权限提示，在终端执行 `chmod +x Trendlume-*`）。
3. **创作**：程序会自动启动后端服务与前端界面，并在浏览器打开 [http://127.0.0.1:3000](http://127.0.0.1:3000)。首次进入「系统设置」填入大语言模型访问密钥即可开始创作。

### 方式二：Docker Compose 部署

适合习惯容器化或部署在私有服务器 / NAS 的用户。镜像内预装了运行环境、FFmpeg 与 Playwright Chromium：

1. **启动容器**：

   ```bash
   docker compose up --build -d
   docker compose ps
   ```

2. **访问工作台**：
   - 前端访问地址：[http://127.0.0.1:8080](http://127.0.0.1:8080)
   - 后端健康检查：[http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)
   - 首次使用请进入右上角「系统设置」配置大语言模型访问密钥（如 DeepSeek）。
   - 查看运行日志：

     ```bash
     docker compose logs -f backend
     docker compose logs -f frontend
     ```

3. **数据持久化目录**：

   所有数据均持久化在本地项目的 **`./data`** 目录中（映射至容器内 `/app/data`）：
   - `trendlume.db`：SQLite 数据库文件（存储项目空间、分镜故事板、流水线任务与服务配置）。
   - `.credential-encryption-key`：本地密钥加密密钥，请妥善备份，切勿随意删除。
   - `storage/`：渲染生成的视频成片、配音音频、字幕文件及上传的素材快照。

## 本地源码开发

如果你希望二次开发或调试功能，可在本地分别启动后端和前端：

### 0. 环境依赖

| 工具 | 最低版本要求 | 用途 |
| --- | --- | --- |
| **[Python](https://www.python.org/downloads/)** | 3.11+ | 后端服务运行环境 |
| **[uv](https://docs.astral.sh/uv/getting-started/installation/)** | 最新稳定版 | Python 虚拟环境与依赖管理工具 |
| **[Node.js](https://nodejs.org/en/download)** | 18.17+ (推荐 LTS) | 前端开发运行环境（自带 npm） |
| **[FFmpeg](https://ffmpeg.org/download.html)** | 6.0+ | 音视频剪辑合成与多媒体探测（需加入系统环境变量 PATH） |

验证命令：
```bash
uv --version
node --version
npm --version
ffmpeg -version
ffprobe -version
```

### 1. 启动后端

```bash
cp backend/.env.example backend/.env
cd backend
uv sync --extra dev
uv run playwright install chromium
uv run alembic upgrade head
uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

> 提示：接口文档在后端 `DEBUG=true` 时可通过 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) 访问。

### 2. 启动前端

另开终端窗口：

```bash
cd frontend
npm ci
npm run dev
```

前端界面访问地址为 [http://127.0.0.1:3000](http://127.0.0.1:3000)。

## 安全与部署须知

> **注意：切勿将本项目端口直接暴露在公网上！**

- **无多租户与登录鉴权**：Trendlume 当前定位为**本地或私有可信网络下的单人创作者工作台**，未内置账号系统、登录鉴权及多租户数据隔离。
- **未做公网安全渗透审计**：项目尚未经过专业的安全渗透审计。
- **建议部署方案**：仅在个人电脑（`127.0.0.1` / `localhost`）或受保护的局域网内运行。若需远程访问，请使用 Tailscale、WireGuard 等私有网络，或在前置反向代理层配置 HTTP Basic Auth / OAuth2 Proxy 等身份验证机制。

## 产物清单

视频渲染完成后，任务详情页面可直接预览或下载以下产物：

- **最终成片**：本地 FFmpeg 渲染输出的 MP4 格式高清视频。
- **外挂字幕轨**：`.srt` 与 `.ass` 字幕文件，可直接导入剪映、Premiere 或 DaVinci Resolve 进行后期精修。
- **时间轴与清单文件**：`timeline.json` 与 `render_manifest.json`，记录每个分镜的音频片段、时间戳与排版参数。

## 后续开发计划

- [x] **全网热点中心**：聚合公开热榜，智能匹配项目选题偏好。
- [x] **三大生产模式架构**：知识科普、电商带货与故事短剧专属策划入口。
- [x] **云端图像与视频生成扩展**：接入阿里云百炼（Qwen Image / Wan 2.7）、Google（Gemini Image / Veo 3.1）与 RunningHub 云端 ComfyUI 工作流。
- [ ] **接入更多模型与服务**：
  - 接入 MiniMax、智谱清言等大语言模型接口
  - 接入可灵 AI 等视频生成服务
  - 接入支持丰富情感表达的语音合成服务
- [ ] **拓展社交发布渠道**：
  - 增加哔哩哔哩、小红书、YouTube、TikTok 等平台的视频发布支持。

## 项目结构

```text
Trendlume/
├── backend/                          # 后端服务（Python 3.11+ / FastAPI）
│   ├── alembic/                      # SQLite 数据库迁移版本
│   ├── templates/                    # HTML/CSS 动态视频排版模板（9:16 / 16:9 / 1:1）
│   ├── workflows/                    # ComfyUI 图像与视频工作流模板 (JSON)
│   └── src/
│       ├── api/                      # 接口路由（项目、任务、分镜、热点、发布、设置）
│       ├── core/                     # 基础设施（配置、密钥加密、异常定义、统一日志）
│       ├── domain/                   # 领域模型（赛道模式、画面来源契约）
│       ├── models/                   # SQLAlchemy ORM 实体（项目、任务、分镜、热点、产物等）
│       ├── providers/                # 外部服务适配器（大语言模型、生图、视频、素材、语音合成、发布）
│       │   ├── image/                # 图像生成（ComfyUI、火山方舟、阿里云百炼、Google、RunningHub）
│       │   ├── video/                # 视频生成（ComfyUI、火山方舟、阿里云百炼、Google、RunningHub）
│       │   ├── llm/                  # 大语言模型（DeepSeek、OpenAI、Claude、Cloudflare、Ollama）
│       │   ├── tts/                  # 语音合成（微软语音服务、火山引擎豆包语音）
│       │   ├── materials/            # 在线素材（Pexels 免版税视频素材）
│       │   └── publishing/           # 社交发布（抖音创作者中心）
│       ├── repositories/             # 数据访问层（数据持久化封装）
│       ├── schemas/                  # 数据传输对象与请求响应契约 (DTO)
│       ├── services/                 # 业务逻辑与工作流运行时（流水线、渲染、热点调度）
│       └── storage/                  # 本地持久化文件存储与资产管理
├── frontend/                         # 前端工作台（Next.js 14 / React 18 / TailwindCSS）
│   └── src/
│       ├── app/                      # 页面路由（工作台、热点中心、项目库、任务中心、发布中心、系统设置）
│       ├── components/               # 界面组件库（故事板工作室、分镜编辑卡、生产任务弹窗等）
│       └── lib/                      # 前端接口客户端、状态契约与类型定义
├── data/                             # 本地运行时持久化目录（已加入 .gitignore）
│   ├── trendlume.db                  # SQLite 数据库文件
│   ├── .credential-encryption-key    # 凭据加密密钥
│   └── storage/                      # 视频、音频、字幕与素材快照
└── tests/                            # 自动化测试套件（单元测试、流水线与集成回归）
```

## 常见说明

- **访问凭据要求**：除内置的微软语音合成服务（Edge-TTS）免费可用（只需能访问网络）外，大语言模型、云端图像与视频生成及搜索服务需自行提供对应平台的访问密钥。热点中心默认通过公开接口采集，无需配置第三方平台账号或登录凭据。
- **抖音扫码发布**：采用官方创作者中心网页扫码授权。若平台触发异地或短信二次核验，需在手机端配合确认。
- **外部素材版权**：使用 Pexels 在线素材库时，请遵循其对应的免版税开源使用协议。
- **本地渲染依赖**：本地运行源码时，依赖系统的 FFmpeg 以及 Playwright Chromium。如果生成时提示缺少浏览器，请执行 `uv run playwright install chromium`。

## 参与开发

欢迎提交 Issue 与 Pull Request。开发约定请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
后端模型与服务适配层位于 [`backend/src/providers`](backend/src/providers)，前端交互逻辑位于 [`frontend/src`](frontend/src)。

## 赞助与支持

如果 Trendlume 对你的短视频创作或开发工作有所帮助，欢迎赞助支持项目的持续迭代！商务合作或交流可通过邮箱联系：[colin0921@outlook.com](mailto:colin0921@outlook.com)。

| 微信支付 (WeChat Pay) | 支付宝 (Alipay) | PayPal |
| :---: | :---: | :---: |
| <img src="docs/assets/WeChatPay.png" width="220" alt="微信支付" /> | <img src="docs/assets/AliPay.png" width="220" alt="支付宝" /> | <img src="docs/assets/PayPal.png" width="220" alt="PayPal" /> |

## 致谢

本项目参考了以下开源项目，在此表示感谢：

- [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)
- [Pixelle-Video](https://github.com/ATH-MaaS/Pixelle-Video)
- [Easel](https://github.com/ZJU-REAL/Easel)
- [social-auto-upload](https://github.com/dreammis/social-auto-upload)

## 许可证

本项目遵循 [Apache License 2.0](LICENSE) 开源许可证。
