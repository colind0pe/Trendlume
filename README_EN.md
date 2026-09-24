# 🎬 Trendlume

> Turn a topic or script into a short video you can still edit scene by scene.

**AI generates the draft. The creator stays in control.** Trendlume is an open-source AI video production workbench built for distinct content tracks. Within a single local workspace, Knowledge, Commerce, and Drama operate with dedicated planning entries and specialized production flows, while sharing media generation, voice synthesis, subtitle alignment, and local rendering.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=flat-square)](LICENSE) [![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/) [![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/) [![Next.js 14](https://img.shields.io/badge/Next.js-14-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/) [![React 18](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/) [![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://www.sqlite.org/) [![FFmpeg](https://img.shields.io/badge/FFmpeg-6.0+-007808?style=flat-square&logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)

<p align="center">
  <a href="README.md">简体中文</a> | <b>English</b>
</p>

<p align="center">
  <img src="docs/assets/trendlume-readme-hero.png" alt="Trendlume AI Video Production Workbench for Distinct Content Tracks" />
</p>

## Three Production Modes

| Mode | Best For & Starting Point | Dedicated Production Workflow |
| --- | --- | --- |
| **Knowledge** | Explainer topics, trending proposals, or existing scripts | Fact research, Knowledge Brief card, script breakdown, Storyboard Studio scene-level editing |
| **Commerce** | Product fact sheet & chosen Creative Plan | Product Truth Sheet, claim constraint verification, commercial storyboard, locked real product footage & preflight QA |
| **Drama** | Narrative concepts or episodic screenplays | Drama Bible world-building, character & location consistency (multi-reference support), episode planning, shot storyboard & approval gates |

All three tracks share configured LLMs, image/video providers, TTS engines, and local FFmpeg rendering. To avoid wasted generation costs and hallucinated claims, **Commerce** strictly locks real product footage rather than letting generative AI fabricate product details. Similarly, **Drama** enforces an approval gate: expensive image and video generation only starts after the storyboard and scene shots are reviewed.

## What It Can Do For You

- **Track-Specific Workflows**: Choose Knowledge, Commerce, or Drama when creating a project. The UI displays only the inputs, constraints, and inspector fields needed for that specific workflow.
- **Scene-Level Fine-Tuning**: Generated videos are never black boxes. In the storyboard editor, preview individual scenes, tweak narration text, audition voiceover lines, regenerate visuals, or swap footage. Changing scene #3 never throws off the pacing of the rest of the video.
- **Flexible Visual Sources**: Use local ComfyUI, Volcengine, Aliyun Bailian, or Google Gemini/Veo for generative assets. Or search free Pexels stock video, generate typography cards, or bind your own custom footage.
- **Auto Audio-Visual-Subtitle Alignment**: Includes built-in Microsoft Edge-TTS (free, no API key required) and Volcengine Doubao speech synthesis. The system automatically sizes scene durations to match spoken audio and aligns subtitles across 9:16 (vertical), 16:9 (horizontal), and 1:1 (square) formats (19 built-in layout templates).
- **Pause Anywhere & Partial Retry**: Every stage state is saved to the local database automatically. Resume after network drops or crashes. Retrying a single scene does not require re-rendering the entire project.
- **Direct Douyin Creator Center Publishing**: Scan a QR code to link your Douyin account. Configure titles, hashtags, and cover frames right inside the publishing center, with support for instant release or scheduled posting.

## Production Workflow

```text
Knowledge: Topic / Trend / Script ──> Research & Brief ──> Script breakdown ──> Storyboard Studio ──> Scene editing & composition
Commerce:  Product facts ──> Creative Plan ──> Lock real footage ──> Commercial storyboard ──> Preflight QA ──> Composition
Drama:     Story concept / Script ──> Drama Bible ──> Characters & Locations ──> Episodes & Shots ──> Approval ──> Media generation
                                                                                                            │
                                           Shared Provider integration, durable retries, and local rendering ───┘
```

- **Trending Topics**: An integrated Hotspot Center pulls live trending feeds across 7 platforms via public APIs, matches project preferences with an LLM, and converts approved angles into Knowledge video tasks.
- **Direct Script Input**: When you already have a finalized script, the pipeline skips research and topic planning, jumping straight into script breakdown and storyboard layout.
- **Locked Real Footage**: For product reviews or documentary-style clips, bind real product images or footage to key scenes. The pipeline honors bound media without generative hallucination.

## Interface Preview

| 01. Workbench Dashboard |
| :---: |
| <a href="docs/assets/screenshots/01-workbench-dashboard.png"><img src="docs/assets/screenshots/01-workbench-dashboard.png" width="100%" alt="Workbench Dashboard" /></a> |
| Monitor project workspaces, active generation pipelines, and recently rendered videos |

| 02. New Video Task | 03. Storyboard Studio |
| :---: | :---: |
| <a href="docs/assets/screenshots/02-create-task-modal.png"><img src="docs/assets/screenshots/02-create-task-modal.png" width="100%" alt="New Video Task" /></a> | <a href="docs/assets/screenshots/03-storyboard-editor.png"><img src="docs/assets/screenshots/03-storyboard-editor.png" width="100%" alt="Storyboard Studio" /></a> |
| KnowledgeBrief planning card, topic angle breakdown, aspect ratios & template presets | Full pipeline monitoring, live preview player & layout adjustments |

| 04. Scene-Level Fine-Tuning | 05. Task Pipeline Center |
| :---: | :---: |
| <a href="docs/assets/screenshots/04-storyboard-scenes.png"><img src="docs/assets/screenshots/04-storyboard-scenes.png" width="100%" alt="Scene-Level Fine-Tuning" /></a> | <a href="docs/assets/screenshots/05-task-pipeline.png"><img src="docs/assets/screenshots/05-task-pipeline.png" width="100%" alt="Task Pipeline Center" /></a> |
| Edit narration, audition voices, regenerate images & bind footage scene-by-scene | Centralized task management with pause, resume, and failure recovery |

| 06. Douyin Publishing Center | 07. Multi-Provider Settings |
| :---: | :---: |
| <a href="docs/assets/screenshots/06-douyin-publishing.png"><img src="docs/assets/screenshots/06-douyin-publishing.png" width="100%" alt="Douyin Publishing Center" /></a> | <a href="docs/assets/screenshots/07-system-settings.png"><img src="docs/assets/screenshots/07-system-settings.png" width="100%" alt="System Settings" /></a> |
| QR code authorization, video tagging, cover selection & scheduled posting | Configure and test LLMs, image generation, video models, stock footage & TTS |

## Supported Models & Services

Configure and test all providers directly from the Web Settings UI. API keys are encrypted at rest locally and masked in application logs.

| Category | Supported Providers / Models | Notes & Prerequisites |
| --- | --- | --- |
| **Hotspot Center** | Public trending feeds from 7 platforms | Weibo, Douyin, Zhihu, Toutiao, Xiaohongshu, Bilibili, Baidu. Relies on public endpoints; no platform credentials or cookies required |
| **Large Language Models** | DeepSeek, OpenAI, Anthropic Claude, Cloudflare Workers AI, local Ollama | DeepSeek or local Ollama recommended for daily cost efficiency |
| **Web Research** | Tavily Search | Live web retrieval and factual context gathering. Requires Tavily API key (optional) |
| **Image Generation** | Local ComfyUI (Flux / SDXL)<br>Volcengine Seedream<br>Aliyun Bailian Qwen Image 3.0 Pro<br>Google Gemini Image<br>RunningHub Cloud Workflows | ComfyUI connects to a local GPU. Cloud options include Volcengine, Aliyun (1–3 reference images), Google (multi-reference character consistency), or custom ComfyUI workflows on RunningHub |
| **Video Generation** | Local ComfyUI (Wan 2.1 / CogVideoX)<br>Volcengine Seedance<br>Aliyun Bailian Wan 2.7<br>Google Veo 3.1<br>RunningHub Video Workflows | Local generation requires dedicated VRAM. Cloud providers include Volcengine Seedance, Aliyun Wan 2.7 (image-to-video / text-to-video), Google Veo 3.1 (references & frame interpolation), or RunningHub node mapping |
| **Stock Footage** | Pexels | Free royalty-free HD video footage. Requires Pexels API key (optional) |
| **Text-to-Speech** | Microsoft Edge-TTS (Free built-in)<br>Volcengine Doubao TTS | Edge-TTS works out of the box with zero keys or setup. Volcengine Doubao TTS offers expressive conversational voices |
| **Publishing** | Douyin Creator Center | Official web QR code authorization, supporting immediate release or scheduled publishing |

## Quick Start

### Option 1: Standalone Executable (Recommended, Zero Setup)

Batteries-included (no Python, Node.js, FFmpeg, or Docker installation needed). Download, extract, and run:

1. **Download**: Visit **GitHub Releases** and download the archive for your operating system (ZIP for Windows, tar.gz for macOS/Linux; verify integrity with the accompanying `.sha256` file).
2. **Launch**: Extract and run the `Trendlume` executable (on macOS/Linux, run `chmod +x Trendlume-*` if prompted).
3. **Start Creating**: The launcher automatically spins up backend services and opens [http://127.0.0.1:3000](http://127.0.0.1:3000) in your browser. Configure your LLM API key in **Settings** to begin.

### Option 2: Docker Compose

Ideal for containerized setups or deployment on a private server or NAS. The image bundles the backend runtime, FFmpeg, and Playwright Chromium:

1. **Start containers**:

   ```bash
   docker compose up --build -d
   docker compose ps
   ```

2. **Access the workspace**:
   - Frontend interface: [http://127.0.0.1:8080](http://127.0.0.1:8080)
   - Backend health check: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)
   - Configure your LLM key (e.g., DeepSeek) under **Settings** in the top right.
   - Monitor logs:

     ```bash
     docker compose logs -f backend
     docker compose logs -f frontend
     ```

3. **Data Persistence**:

   All runtime data persists on your host machine under **`./data`** (mapped to `/app/data` in the container):
   - `trendlume.db`: SQLite database storing projects, storyboards, pipelines, and provider settings.
   - `.credential-encryption-key`: Fernet secret key used to encrypt API credentials. Back this up alongside the database.
   - `storage/`: Rendered MP4 videos, speech audio clips, subtitle files, and uploaded assets.

## Local Source Development

To develop or debug features locally, run the backend and frontend independently:

### 0. Prerequisites

| Tool | Minimum Version | Purpose |
| --- | --- | --- |
| **[Python](https://www.python.org/downloads/)** | 3.11+ | Backend service runtime |
| **[uv](https://docs.astral.sh/uv/getting-started/installation/)** | Latest stable | Fast Python virtualenv & dependency management |
| **[Node.js](https://nodejs.org/en/download)** | 18.17+ (LTS recommended) | Frontend runtime environment (includes npm) |
| **[FFmpeg](https://ffmpeg.org/download.html)** | 6.0+ | Video composition & media probing (ensure `bin` is in your PATH) |

Verification commands:
```bash
uv --version
node --version
npm --version
ffmpeg -version
ffprobe -version
```

### 1. Backend Setup

```bash
cp backend/.env.example backend/.env
cd backend
uv sync --extra dev
uv run playwright install chromium
uv run alembic upgrade head
uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

> Tip: Interactive API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) when `DEBUG=true`.

### 2. Frontend Setup

In a separate terminal:

```bash
cd frontend
npm ci
npm run dev
```

The frontend will be available at [http://127.0.0.1:3000](http://127.0.0.1:3000).

## Security & Deployment Notice

> **Important: Do NOT expose Trendlume directly to the public internet!**

- **No Multi-Tenant Authentication**: Trendlume is built as a **single-user creator workbench for local or trusted private networks**. It does not provide built-in user login, multi-tenant isolation, or fine-grained access control.
- **No Formal Penetration Audit**: The codebase has not been audited by third-party security firms.
- **Recommended Deployment**: Run only on personal machines (`127.0.0.1` / `localhost`) or within a protected private network. If remote access is required, use Tailscale, WireGuard, or place the service behind a reverse proxy enforcing HTTP Basic Auth or OAuth2 Proxy.

## Exported Artifacts

Once video rendering finishes, inspect or download the following from the task page:

- **Final Video**: High-definition MP4 file rendered locally via FFmpeg.
- **Independent Subtitles**: `.srt` and `.ass` subtitle files ready for secondary editing in CapCut, Premiere, or DaVinci Resolve.
- **Timeline & Manifest**: `timeline.json` and `render_manifest.json`, detailing audio clips, timestamps, and layout parameters for every scene.

## Upcoming Roadmap

- [x] **Trending Topics Center**: Aggregated public hotlists matched against project topic preferences.
- [x] **Three Production Modes Architecture**: Independent workflows for Knowledge, Commerce, and Drama.
- [x] **Cloud Image & Video Providers**: Aliyun Bailian (Qwen Image / Wan 2.7), Google (Gemini Image / Veo 3.1), and RunningHub cloud ComfyUI workflows.
- [ ] **Additional Provider Integrations**:
  - LLM: MiniMax, Zhipu GLM, and additional API relays
  - Visuals: Kling AI and other video generation services
  - Voice: Expressive multi-emotion TTS providers
- [ ] **Expanded Social Publishing**:
  - Publishing support for Bilibili, Xiaohongshu, YouTube, and TikTok.

## Project Structure

```text
Trendlume/
├── backend/                          # Backend services (Python 3.11+ / FastAPI)
│   ├── alembic/                      # SQLite database migrations
│   ├── templates/                    # Dynamic HTML/CSS video layout templates (9:16 / 16:9 / 1:1)
│   ├── workflows/                    # ComfyUI image & video generation workflows (JSON)
│   └── src/
│       ├── api/                      # RESTful API layer (projects, tasks, scenes, trends, publishing, settings)
│       ├── core/                     # Infrastructure (config, cipher encryption, exceptions, logging)
│       ├── domain/                   # Domain models (production modes, content mode contracts)
│       ├── models/                   # SQLAlchemy ORM models (projects, tasks, scenes, trends, artifacts)
│       ├── providers/                # External provider integrations (strictly adhering to Protocol contracts)
│       │   ├── image/                # ComfyUI, Volcengine, Aliyun, Google, RunningHub image generation
│       │   ├── video/                # ComfyUI, Volcengine, Aliyun, Google, RunningHub video generation
│       │   ├── llm/                  # DeepSeek, OpenAI, Claude, Cloudflare, Ollama
│       │   ├── tts/                  # Edge-TTS, Volcengine Doubao speech synthesis
│       │   ├── materials/            # Pexels stock video footage
│       │   └── publishing/           # Douyin creator center integration
│       ├── repositories/             # Data access layer (CRUD database abstractions)
│       ├── schemas/                  # Pydantic request & response schemas (DTOs)
│       ├── services/                 # Core business logic & workflow runtime (pipeline, renderer, scheduler)
│       └── storage/                  # Unified local file storage & asset management
├── frontend/                         # Frontend workbench (Next.js 14 / React 18 / TailwindCSS)
│   └── src/
│       ├── app/                      # Page routes (/trends, /projects, /tasks, /publishing, /settings)
│       ├── components/               # UI components (Storyboard Studio, scene editor, task creation dialog)
│       └── lib/                      # API client, state contracts & TypeScript definitions
├── data/                             # Local persistent storage directory (gitignored)
│   ├── trendlume.db                  # SQLite database
│   ├── .credential-encryption-key    # Fernet secret key
│   └── storage/                      # Rendered video, audio, subtitles, and snapshots
└── tests/                            # Automated test suite (unit, pipeline & regression tests)
```

## General Notes

- **API Credentials**: Except for the built-in free Edge-TTS (which requires only an internet connection), external LLMs, cloud image/video generation, and search services require API keys. The Trending Center uses public feeds without requiring platform login or cookies.
- **Douyin QR Login**: Uses official web creator center QR code authorization. If prompted with secondary SMS verification, confirm on your mobile device.
- **Stock Media Licenses**: When using Pexels stock footage, comply with the Pexels royalty-free license terms.
- **Local Rendering Dependencies**: When running from source, the application relies on system FFmpeg and Playwright Chromium. If an error indicates a missing browser, run `uv run playwright install chromium`.

## Contributing

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.
Backend provider adapters live in [`backend/src/providers`](backend/src/providers); frontend logic lives in [`frontend/src`](frontend/src).

## Sponsorship & Support

If Trendlume helps your video creation or development workflow, consider sponsoring ongoing development! For collaboration or business inquiries: [colin0921@outlook.com](mailto:colin0921@outlook.com).

| WeChat Pay | Alipay | PayPal |
| :---: | :---: | :---: |
| <img src="docs/assets/WeChatPay.png" width="220" alt="WeChat Pay" /> | <img src="docs/assets/AliPay.png" width="220" alt="Alipay" /> | <img src="docs/assets/PayPal.png" width="220" alt="PayPal" /> |

## Acknowledgments

Trendlume draws inspiration from these open-source projects:

- [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)
- [Pixelle-Video](https://github.com/ATH-MaaS/Pixelle-Video)
- [Easel](https://github.com/ZJU-REAL/Easel)
- [social-auto-upload](https://github.com/dreammis/social-auto-upload)

## License

This project is licensed under the [Apache License 2.0](LICENSE).
