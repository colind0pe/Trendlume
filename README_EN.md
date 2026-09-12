# 🎬 Trendlume

> Trendlume is an automated AI short-video creation and publishing workbench tailored for creators.

Whether you start with a rough topic idea or an existing script, Trendlume helps you streamline web research, script planning, visual asset generation, voiceover synthesis, subtitle alignment, template composition, and direct publishing to Douyin. Every scene can be fine-tuned individually in the visual storyboard without re-rendering the entire video.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=flat-square)](LICENSE) [![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/) [![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/) [![Next.js 14](https://img.shields.io/badge/Next.js-14-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/) [![React 18](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/) [![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://www.sqlite.org/) [![FFmpeg](https://img.shields.io/badge/FFmpeg-6.0+-007808?style=flat-square&logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)

<p align="center">
  <a href="README.md">简体中文</a> | <b>English</b>

</p>

<p align="center">
  <img src="docs/assets/trendlume-readme-hero.png" alt="Trendlume AI Short Video Creation and Publishing Workbench" />
</p>

## ✨ What It Can Do For You

- **Dual Creation Workflows**: Provide a topic prompt to let AI autonomously research and expand into storyboards, or paste an existing script to jump straight into visual production.
- **Scene-Level Visual Fine-Tuning**: Videos are not black boxes. In the storyboard editor, preview each scene, adjust durations, tweak narration, regenerate visuals, or swap in Pexels stock footage without altering the flow of other scenes.
- **Diverse Visual Formats**: Supports AI image generation, AI video generation, Pexels royalty-free media search, kinetic typography cards, and custom user uploads.
- **Audio-Visual-Subtitle Auto-Alignment**: Free built-in Edge-TTS or Volcengine Doubao TTS. The system auto-calculates scene durations based on speech audio and aligns subtitles across 9:16 (vertical), 16:9 (horizontal), and 1:1 (square) templates (19 built-in layout templates).
- **Pause Anywhere & Partial Retry**: Each stage state is persisted automatically. Resume seamlessly after network drops or crashes. Changing the 3rd scene's image does not require re-rendering previously finished scenes.
- **Direct Douyin Publishing**: Authorize via QR code scanning, fill in title, hashtags, select a cover frame, and publish immediately or schedule for later.

## Creation Workflow

```text
Input Topic or Script ──> Research & Planning ──> Storyboard Generation ──> Visual Fine-tuning
                                                                                    │
Video Export / Publishing <── Composition & Rendering <── Voiceover & Subtitles <───┘
```

- **Custom Script**: If you choose fixed script mode, web research and topic planning stages are skipped automatically.
- **Stock Media**: In Pexels stock mode, the system searches matching footage based on scene narration keywords, eliminating slow image generation wait times.

## 🖼️ Interface Preview

| 01. Workbench Dashboard |
| :---: |
| <a href="docs/assets/screenshots/01-workbench-dashboard.png"><img src="docs/assets/screenshots/01-workbench-dashboard.png" width="100%" alt="Workbench Dashboard" /></a> |
| Monitor active tasks, project spaces, and recent exports |

| 02. New Video Task | 03. Storyboard Studio |
| :---: | :---: |
| <a href="docs/assets/screenshots/02-create-task-modal.png"><img src="docs/assets/screenshots/02-create-task-modal.png" width="100%" alt="New Video Task" /></a> | <a href="docs/assets/screenshots/03-storyboard-editor.png"><img src="docs/assets/screenshots/03-storyboard-editor.png" width="100%" alt="Storyboard Studio" /></a> |
| Topic expansion, script breakdown, style presets & specs | Pipeline stage status, live video preview & template tuning |

| 04. Scene-Level Editor | 05. Task Pipeline |
| :---: | :---: |
| <a href="docs/assets/screenshots/04-storyboard-scenes.png"><img src="docs/assets/screenshots/04-storyboard-scenes.png" width="100%" alt="Scene-Level Editor" /></a> | <a href="docs/assets/screenshots/05-task-pipeline.png"><img src="docs/assets/screenshots/05-task-pipeline.png" width="100%" alt="Task Pipeline" /></a> |
| Edit narration, audition voices, swap media & partial retry | Track stage progress with pause and resume support |

| 06. Douyin Publishing | 07. System Settings |
| :---: | :---: |
| <a href="docs/assets/screenshots/06-douyin-publishing.png"><img src="docs/assets/screenshots/06-douyin-publishing.png" width="100%" alt="Douyin Publishing" /></a> | <a href="docs/assets/screenshots/07-system-settings.png"><img src="docs/assets/screenshots/07-system-settings.png" width="100%" alt="System Settings" /></a> |
| QR code login, hashtag tagging & scheduled publishing | Configure and test LLMs, image generation, stock media, and TTS |

## Supported Models & Services

Configure and test all providers directly from the Web Settings UI. API keys are encrypted at rest locally and masked in application logs.

| Category | Supported Providers | Recommended Combination |
| --- | --- | --- |
| Large Language Model | DeepSeek, OpenAI-compatible APIs, Claude, Cloudflare Workers AI, local Ollama | DeepSeek or local Ollama for cost efficiency |
| Web Research | Tavily | Live information and factual context gathering |
| Image & Video | Local ComfyUI, Volcengine Seedream / Seedance | ComfyUI if you have a local GPU; Volcengine for cloud convenience |
| Stock Media | Pexels | Free high-definition photos and footage library |
| Text-to-Speech | Edge-TTS (Free built-in), Volcengine Doubao TTS | Edge-TTS for instant free zero-key setup |
| Publishing | Douyin Creator Center | Web QR code authorization, instant & scheduled release |

## 🚀 Quick Start

### Option 1: Standalone Executable (Recommended, Zero Setup)

Batteries-included (no Python, Node.js, FFmpeg, or Docker required). Download, extract, and run:

1. **Download**: Visit **GitHub Releases** and download the archive for your OS (ZIP for Windows, tar.gz for macOS/Linux; use the accompanying `.sha256` file to verify it).
2. **Launch**: Extract and run the `Trendlume` executable (on macOS/Linux, run `chmod +x Trendlume-*` first if needed).
3. **Get Started**: The launcher will automatically start services and open [http://127.0.0.1:3000](http://127.0.0.1:3000) in your browser. Configure your API keys in **Settings** to begin.

### Option 2: Using Docker Compose

Ideal for users who prefer containerization or want to run on a home server/NAS. The container image bundles the backend runtime, FFmpeg, and Playwright Chromium, requiring no local dependency setup on your host machine.

1. **Start services**:

   ```bash
   docker compose up --build -d
   docker compose ps
   ```

2. **Start creating**:

   - Open frontend: [http://127.0.0.1:8080](http://127.0.0.1:8080)
   - Backend health check: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)
   - First-time setup: Navigate to Settings (top-right) and configure your LLM API Key (e.g. DeepSeek). Bind your Douyin account on the Publishing page if you plan to publish directly.
   - View runtime logs:

      ```bash
      docker compose logs -f backend
      docker compose logs -f frontend
      ```

3. **Docker Data Persistence**

   All runtime data is persisted on the host machine under **`./data`** via volume mount (mapped to `/app/data` inside the container):

   - **`./data/trendlume.db`**: SQLite database (stores pipelines, storyboards, and configurations).
   - **`./data/.credential-encryption-key`**: Auto-generated credential-encryption key; back it up with the database and do not delete or replace it independently.
   - **`./data/storage/`**: Generated videos, audio clips, subtitle files, and uploaded media assets.

## 🛠️ Local Development Setup

If you want to modify code or debug features, run backend and frontend independently:

### 0. Local Prerequisites

Ensure the following core tools are installed on your host system before running from source:

| Tool | Requirement | Purpose |
|---|---|---|
| **[Python](https://www.python.org/downloads/)** | 3.11+ | Backend runtime |
| **[uv](https://docs.astral.sh/uv/getting-started/installation/)** | Latest stable | Python virtualenv & dependency manager |
| **[Node.js](https://nodejs.org/en/download)** | 18.17+ (LTS recommended) | Frontend runtime (includes `npm`) |
| **[FFmpeg](https://ffmpeg.org/download.html)** | 6.0+ | Video composition & media probing (add `bin` to PATH) |

**Verification:**
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
```

Configure `backend/.env` with your encryption keys, then launch:

```bash
cd backend
uv sync --extra dev
uv run playwright install chromium
uv run alembic upgrade head
uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

> Tip: Interactive API docs are available at `/docs` or `/redoc` when `DEBUG=true`.

### 2. Frontend Setup

Open another terminal:

```bash
cd frontend
npm ci
npm run dev
```

The frontend will be available at [http://127.0.0.1:3000](http://127.0.0.1:3000).

## ⚠️ Security & Deployment Notice

> **Important Warning: Do NOT expose this project directly to the public internet!**

- **No Built-in Authentication**: Trendlume is currently designed as a **single-user creator workbench for local or trusted private networks**. It **does not include user login, multi-tenant isolation, or fine-grained access control**. Anyone who can reach the open ports can view or modify stored API keys, task history, and generated videos.
- **Un-audited Security**: The codebase has not undergone comprehensive penetration testing or formal security audits.
- **Recommended Usage**: Run exclusively on personal machines (`127.0.0.1` / `localhost`) or within a protected private LAN. If remote access is necessary, place it behind a reverse proxy enforcing authentication (HTTP Basic Auth, OAuth2 Proxy) or use a private VPN (Tailscale / WireGuard). Never expose the ports directly to the public internet.

## 📦 Exported Artifacts

After video generation completes, you can inspect or download the following artifacts from the task details page:

- **Final Video**: High-definition MP4 file
- **Independent Subtitles**: `.srt` and `.ass` subtitle files, ready for secondary editing in CapCut or Premiere
- **Timeline & Manifest**: `timeline.json` and `render_manifest.json`, detailing audio, duration, and render parameters per scene

## 🗺️ Upcoming Roadmap

- [ ] **Trending Topics Dashboard**: Real-time aggregation of trending topics across major platforms to inspire one-click video creation.
- [ ] **Additional Provider Integrations**:
  - LLM: MiniMax, Zhipu GLM, Kimi, and popular API relays
  - Visuals: Midjourney, Kling AI, and additional video/image generation APIs
  - Voice: Enhanced expressive, multi-emotion TTS providers
- [ ] **Multi-Platform Publishing**: Cover adaptation, hashtag management, and publishing for TikTok, YouTube, Bilibili, Xiaohongshu, and WeChat Video Channel.
- [ ] **AI Short Drama Mode**: Multi-episode script continuity, character visual & costume consistency locking, multi-camera scene scheduling, and episodic generation.

## 📂 Project Structure

```text
Trendlume/
├── backend/                          # Backend core services (Python 3.11+ / FastAPI)
│   ├── alembic/                      # Database migrations & revision history
│   ├── templates/                    # Dynamic HTML/CSS video templates (9:16 / 16:9 / 1:1)
│   ├── workflows/                    # ComfyUI image & video generation workflows (JSON)
│   └── src/                          # Backend source code
│       ├── api/                      # RESTful API layer
│       │   ├── routes/               # Business routes (tasks, projects, generation, scenes, publishing, etc.)
│       │   ├── dependencies.py       # Dependency injection (DB session, services)
│       │   └── app.py                # FastAPI instance & middleware configuration
│       ├── core/                     # Infrastructure (config, cipher encryption, exceptions, logging)
│       ├── domain/                   # Domain models & workflow stage definitions
│       ├── models/                   # SQLAlchemy ORM database models (tasks, scenes, artifacts, publishers)
│       ├── providers/                # External provider integrations (strictly adhering to Protocol contracts)
│       ├── repositories/             # Data access layer (CRUD database abstractions)
│       ├── schemas/                  # Pydantic request & response schemas (DTOs)
│       ├── services/                 # Core business services (durable pipeline, rendering, publishing)
│       ├── storage/                  # Unified storage service (local persistent data & asset paths)
│       └── tasks/                    # Async task system (asyncio scheduler, workers, SSE broadcaster)
├── frontend/                         # Frontend workbench (Next.js 14 App Router / React 18 / TailwindCSS)
│   └── src/
│       ├── app/                      # Page routes & layouts (projects, tasks storyboard, publishing, settings)
│       ├── components/               # UI components & workflow stage visualization
│       └── lib/                      # API client, SSE event listener hooks, and TypeScript contracts
├── data/                             # Local persistent data directory (auto-generated, gitignored)
│   ├── trendlume.db                  # SQLite database (WAL mode task & config persistence)
│   └── storage/                      # Rendered video, audio, subtitles, snapshots, and cache
└── tests/                            # Automated test suite (fixtures, offline mocks, E2E tests)
```

## ℹ️ General Notes

- **API Credentials**: Except for the built-in free Edge-TTS (internet connection required), external LLM, image generation, and search services require your own API keys.
- **Douyin Publishing**: Uses official web creator center QR code authorization. If prompted with secondary SMS verification, confirm via your mobile device.
- **Stock Media Licenses**: When using Pexels, ensure compliance with their royalty-free license and terms of use.
- **Rendering Dependencies**: When running from source, the system requires local FFmpeg and Playwright Chromium. If an error indicates a missing browser, run `uv run playwright install chromium`.

## 🤝 Contributing

Issues and Pull Requests are welcome! Please review [CONTRIBUTING.md](CONTRIBUTING.md) for architectural guidelines and PR checklists.

## ☕ Sponsor & Support

If Trendlume has helped your video creation or development workflow, consider sponsoring the project's ongoing development and feature expansion! If you would like to discuss other forms of sponsorship or collaboration, feel free to reach out via email: [colin0921@outlook.com](mailto:1370227996@qq.com).

| WeChat Pay (微信支付) | Alipay (支付宝) | PayPal |
| :---: | :---: | :---: |
| <img src="docs/assets/WeChatPay.png" width="220" alt="WeChat Pay" /> | <img src="docs/assets/AliPay.png" width="220" alt="Alipay" /> | <img src="docs/assets/PayPal.png" width="220" alt="PayPal" /> |

## 🙏 Acknowledgements
 
Special thanks to the following open-source projects:

- [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)
- [Pixelle-Video](https://github.com/ATH-MaaS/Pixelle-Video)
- [Easel](https://github.com/ZJU-REAL/Easel)
- [social-auto-upload](https://github.com/dreammis/social-auto-upload)

## 📄 License

This project is licensed under the [Apache License 2.0](LICENSE).
