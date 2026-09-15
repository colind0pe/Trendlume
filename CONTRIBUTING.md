# 贡献指南 (Contributing)

欢迎参与 Trendlume 的开发！

为了保证代码整洁并保持架构轻巧，我们在设计上有几个明确的原则。提交 PR 之前，请花几分钟阅读这篇指南。

---

## 🧭 架构原则与底线

Trendlume 定位是一个轻量、自闭环、开箱即用的个人与工作室短视频创作工作台。为了防止系统过度膨胀，代码库有以下几条不可逾越的底线：

1. **坚持轻量单机架构，严禁引入重型中间件**：
   - 严禁引入 Redis、Celery、Kafka、RabbitMQ、PostgreSQL、MinIO 等外部常驻服务。
   - 异步调度使用内置的 `asyncio` 单机队列与 Worker 机制；数据持久化全部走本地 SQLite（WAL 模式）。
   - 用户只需要 Docker 或 Python 本地环境就能把全部功能跑起来，不要随意把部署门槛做高。

2. **简单胜过过度抽象**：
   - 50 行直观代码能搞定的逻辑，不要写 300 行的抽象工厂或中间层。
   - 避免为单次使用的业务逻辑设计泛化框架。

3. **严格遵守 Provider Protocol 契约**：
   - 所有外部大模型、图像、语音、搜索与发布逻辑必须放在 `src/providers/` 下，并实现对应的 Protocol 接口。
   - 上层业务逻辑只能面向 Protocol 编程，**严禁**在业务流程中写 `if provider == "xxx"` 针对特定厂商打补丁。

4. **统一的文件与产物管理**：
   - 业务代码严禁在本地随意使用 `open()` 或裸 `Path()` 写入或读取文件，必须通过 `StorageService` 统一管理生命周期与路径。

5. **热点采集与视频流水线物理隔离**：
   - 热点数据采集与订阅调度使用独立数据表（`trend_runs`、`trend_subscriptions` 等）与 `TrendScheduler`，严禁将其作为普通 Task 压入 `workflow_jobs` 队列。
   - 热点转化为视频创作时，严格遵循 `Trend → Proposal → Task` 的单向流转。通过提案阶段沉淀切入点后，再生成标准 Task，保持下游故事板与渲染逻辑幂等且不被热点轮询污染。

6. **遵守画面来源模式（Content Modes）契约**：
   - 所有视觉素材流转必须遵守 `backend/src/domain/content_modes.py` 定义的契约（`generated_image`、`generated_video`、`online_asset`、`uploaded_asset`、`static`）。
   - 新增模板或扩展视觉生成能力时，必须在 `supported_content_modes` 中显式声明支持的模式，不得使用未受约束的自定义字符串。

---

## 🛠️ 本地开发环境准备

### 1. 克隆仓库

```bash
git clone <repository-url>
cd Trendlume
```

### 2. 后端开发环境 (Python 3.11+)

后端推荐使用包管理工具 [`uv`](https://github.com/astral-sh/uv)：

```bash
cd backend

# 复制环境变量配置文件
cp .env.example .env

# 安装依赖（包含 dev 工具集）
uv sync --extra dev

# 安装 Playwright Chromium（用于模板渲染与封面截图）
uv run playwright install chromium

# 执行数据库迁移
uv run alembic upgrade head

# 启动后端 API（支持热重载）
uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

后端 API 交互文档在 `DEBUG=true` 时可通过 `http://127.0.0.1:8000/docs` 访问。

### 3. 前端开发环境 (Node.js 18+)

```bash
cd frontend

# 安装依赖（必须使用 npm ci 保持版本锁定，请勿使用 pnpm 或重建符号链接树）
npm ci

# 启动前端开发服务器
npm run dev
```

浏览器打开 [http://127.0.0.1:3000](http://127.0.0.1:3000) 即可进行调试。

---

## 🧩 如何扩展 Provider

为 Trendlume 接入新的 AI 模型、媒体生成能力或发布渠道，是项目中最常见的贡献方式。

目前系统抽象了以下几类能力，对应的 Protocol 位于 `backend/src/providers/`：

- **大语言模型**：`src/providers/llm/protocol.py` (`LLMProvider`)
- **语音合成**：`src/providers/tts/protocol.py` (`TTSProvider`)
- **图片生成**：`src/providers/image/protocol.py` (`ImageProvider`)
- **视频生成**：`src/providers/video/protocol.py` (`VideoProvider`)
- **联网搜索**：`src/providers/search/protocol.py` (`SearchProvider`)
- **发布渠道**：`src/providers/publishing/protocol.py` (`PublishProvider`)

### 接入新 Provider 的标准步骤：

1. **实现 Protocol**：
   在对应子目录下创建新模块，实现接口中定义的异步方法（如 `generate_text()`、`generate_structured()` 等）。
2. **重试与日志脱敏**：
   - 网络请求方法使用 `src/providers/base.py` 提供的 `@retry_async` 装饰器，自动处理指数退避与重试。
   - 涉及 API Key 或敏感信息输出时，使用 `mask_secret()` 进行脱敏，严禁明文打入日志。
3. **注册与配置**：
   在 `src/providers/registry.py` 中注册新 Provider，并确保前端「设置」页面可以通过设置中心传入该 Provider 的配置项（密钥将通过后端对称加密安全保存）。
4. **补充单元测试**：
   在 `tests/` 下添加对应测试，使用 Mock 对象模拟网络返回，严禁在 CI/单元测试中直接调用外部真实付费 API。

---

## 🌐 如何扩展热点平台来源 (Trend Sources)

系统通过 `TrendSourceAdapter` 协议抽象多平台公开热榜数据源，相关实现位于 `backend/src/services/trend_sources.py`。

### 接入新热点来源的原则：
1. **使用公开稳定的规范化接口**：优先使用公开 JSON Feed 或公益 API，并配置主源（如 60s）与备用源（如 xxapi）以实现自动降级。
2. **不编写针对平台 Web 页面的爬虫**：主流平台前端页面存在严格的登录校验与风控机制，直接抓取容易导致服务中断和账号封禁。
3. **保留原始指标，不做跨平台数学比对**：通过 `TrendSourceItem` 分别保存各平台的原始热度数值（`raw_metric`）与度量单位（`metric_unit`），不得在跨平台场景下直接对不同算法产出的热度值进行大小比较。
4. **测试要求**：在 `tests/test_trend_sources.py` 中补充针对该数据源的数据解析与错误降级单元测试（使用本地静态 payload 模拟）。

---

## 🗄️ 数据库变更规范

如果你修改了 `src/models/` 下的 SQLAlchemy 模型定义，必须通过 Alembic 生成对应的数据库迁移脚本：

```bash
cd backend

# 1. 自动生成迁移版本
uv run alembic revision --autogenerate -m "描述你的变更，例如 add_aspect_ratio_to_tasks"

# 2. 检查 alembic/versions/ 下新生成的迁移脚本，确保字段类型与索引无误

# 3. 本地应用迁移
uv run alembic upgrade head
```

---

## 🧪 提交前检查清单 (PR Checklist)

在发起 Pull Request 前，请确保以下本地质量检查全部通过：

### 后端代码规范与测试

```bash
cd backend

# 代码风格与语法检查
uv run ruff check src --fix
uv run ruff format src

# 运行自动化测试套件
uv run --extra dev pytest ../tests -q
```

### 前端类型与构建检查

```bash
cd frontend

# TypeScript 类型检查
npm run typecheck

# 生产构建验证
npm run build
```

---

## 📝 提交与 PR 规范

1. **分支命名**：
   - 新功能：`feature/your-feature-name`
   - 缺陷修复：`fix/your-bugfix-name`
   - 文档与优化：`docs/your-doc-name` 或 `refactor/your-refactor-name`

2. **Commit Message**：
   遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范，保持信息清晰、动宾分明：
   - `feat(llm): add DeepSeek v3 structured output support`
   - `fix(render): handle subtitle line wrap on vertical templates`
   - `docs: update provider extension guidelines`

3. **PR 描述要求**：
   - 说明为什么要做此修改（背景或解决的 Issue）。
   - 列举具体修改了哪些模块。
   - 附上本地测试的方法与通过结果。
