# ArcBrief

ArcBrief 是一个本地优先的情报助手，包含两条主线能力：
- `Deep Research`：Agent/Host 协作式研究，生成可预览、可下载报告
- `Daily Brief`：RSS + Tavily 采集，聚类后生成每日简讯

当前实现以单机可用、流程闭环和可迭代为目标。

---

## 1. 当前能力

### 1.1 Deep Research
- 流程阶段：`outline -> search -> summary -> host -> reflection -> final`
- 前端显示 Pipeline 进度、事件日志、报告预览
- 报告会持久化到 SQLite（`research_runs`），服务重启后历史仍可查
- 历史支持查看全文与下载

### 1.2 Daily Brief
- 数据来源：RSS 优先 + Tavily 补充
- 聚类：关键词匹配（Phase 1）
- 摘要：LLM 优先，失败时使用规则兜底
- 支持全主题一键 `Refresh & Generate`
- 支持 `All Topics` 聚合视图（每个 topic 展示最新一份简讯）
- 支持按 topic 查看 `Recent Briefs` 历史并切换当日卡片
- 简讯卡片内直接展示 `Sources` 与关键词摘要
- 简讯与研究报告均支持 `Export PDF`
- 采集返回细粒度统计：`collected` / `saved` / `duplicates` / `failed_topics`
- 默认仅展示最近 48 小时内容（可配置）
- 内置质量闸门：过滤首页 URL、浅路径、短标题、短正文
- 内置低信息清洗：过滤 HN 类 `Article URL / Comments / Points` 噪声字段

---

## 2. 技术栈

- 后端：FastAPI（单体）
- 数据库：SQLite（起步）
- 定时任务：APScheduler
- 采集：feedparser（RSS）+ Tavily
- 前端：Next.js
- 部署：本地优先

---

## 3. 项目结构

```text
ArcBrief/
├─ backend/                  # FastAPI API、SQLite、Scheduler
├─ foreign_query_agent/      # Research Agent 核心
├─ frontend/                 # Next.js 前端
├─ scripts/                  # 辅助脚本
├─ outputs/                  # 研究报告输出
├─ logs/                     # 运行日志
├─ discord_bot.py            # Discord Bot（可选）
├─ requirements.txt
└─ .env
```

---

## 4. 快速启动（本地测试）

### 第 1 步：安装依赖

```bash
# 后端
pip install -r requirements.txt

# 前端
cd frontend 
npm install 
```

### 第 2 步：配置 .env

项目根目录已有 `.env`，也可参考 `.env.example`，只需确认以下三项有值：

```env
# LLM（必填，OpenAI 兼容接口）
FQ_LLM_API_KEY=your_key
FQ_LLM_BASE_URL=your_base_url
FQ_LLM_MODEL=your_model

# 搜索（必填，用于采集和研究）
TAVILY_API_KEY=your_tavily_key
ARCBRIEF_ENABLE_TAVILY=1
```

可选（推荐在非本机环境配置）：
```env
ARCBRIEF_API_KEY=replace-with-your-key
ALLOWED_ORIGINS=http://localhost:3000
ARCBRIEF_NEWS_MAX_AGE_HOURS=48
ARCBRIEF_ALLOW_UNDATED=1
ARCBRIEF_RSS_REQUIRE_PUBLISHED=1
ARCBRIEF_RSS_ONLY=0
ARCBRIEF_MIN_RSS_ITEMS_BEFORE_TAVILY=12
ARCBRIEF_MIN_TITLE_LEN=12
ARCBRIEF_MIN_CONTENT_LEN=40
ARCBRIEF_MIN_URL_PATH_DEPTH=1
# 前端开发者面板（默认关闭，避免普通用户看到运行诊断）
NEXT_PUBLIC_SHOW_DEV_PANELS=0
# Brief 关键词矩阵与论文限流（默认开启）
ARCBRIEF_ENABLE_KEYWORD_MATRIX=1
ARCBRIEF_KEYWORD_MIN_SCORE=1
ARCBRIEF_ARXIV_MIN_SCORE=2
ARCBRIEF_ARXIV_MAX_ITEMS=3
```

> 鉴权、数据库、CORS 均有本地默认值，无需额外配置即可启动。
> 前端也无需创建 `.env.local`，默认连 `localhost:8000` 且使用本地开发密钥。

### 第 3 步：启动

打开两个终端：

```bash
# 终端 1 — 后端
uvicorn backend.main:app --reload --port 8000

# 终端 2 — 前端
cd frontend && npm run dev
```

打开浏览器访问 **http://localhost:3000**

---

## 5. API 鉴权说明

- 所有 `/api/*` 请求都需要请求头：`X-API-Key`
- Key 来自后端环境变量 `ARCBRIEF_API_KEY`
- 前端通过 `NEXT_PUBLIC_ARCBRIEF_API_KEY` 自动附加请求头
- 未携带或不匹配会返回 `401 Unauthorized`
> 若 `ARCBRIEF_API_KEY` 为空或仍是占位值（如 `replace-with-your-key`），后端会自动使用本地默认值 `arcbrief-local-dev-key`，方便本机测试。
> 本机访问（`127.0.0.1`/`::1`）默认跳过鉴权，避免本地联调频繁 401。

--- 

## 5.1 RSS-Only 调试模式

如需验证“只用 RSS 是否能收到消息”，可在后端启动前设置：

```env
ARCBRIEF_RSS_ONLY=1
```

这会关闭 Tavily 补充，仅使用 RSS 采集链路。

如需临时完全禁用 Tavily（例如 API 配额不足），可设置：

```env
ARCBRIEF_ENABLE_TAVILY=0
```

---

## 6. 关键接口（当前）

Research：
- `POST /api/run`
- `GET /api/status/{run_id}`
- `GET /api/history`
- `GET /api/report/{run_id}`
- `GET /api/report/{run_id}/download`

Brief：
- `GET /api/topics`
- `POST /api/topics`
- `PUT /api/topics/{topic_id}`
- `DELETE /api/topics/{topic_id}`
- `POST /api/topics/{topic_id}/collect`
- `POST /api/topics/collect_all`
- `POST /api/topics/{topic_id}/brief`
- `POST /api/topics/brief_all`
- `GET /api/briefs/{topic_id}/latest`
- `GET /api/briefs/{topic_id}/history?limit=14`
- `GET /api/briefs/recent?limit=200`
- `GET /api/briefs/{brief_id}/feedback`
- `POST /api/briefs/{brief_id}/feedback?rating=1|-1`
- `GET /api/briefs/{brief_id}/export/pdf`
- `GET /api/topics/{topic_id}/articles?hours=72&sort=time`

---

## 7. 默认主题

首次启动且数据库为空时，自动注入 3 个主题：
- Global Trending
- Macro and Metals
- AI Daily

可在前端 `Settings` 中增删改。

---

## 8. 已实现与待实现

已实现：
- API Key 基础鉴权
- Research 报告持久化与历史查询
- 简讯采集与生成（Phase 1）
- 全主题批量采集/生成
- 超时提示、空状态引导、报告下载
- 老文章定时清理（默认 30 天）

待实现：
- 更完整的认证/授权模型（多用户）
- Prompt Injection 防护与限流
- Phase 2：LLM 归类与质量反馈回路
- Discord Bot 正式部署与运维

---

## 9. 文档入口

- 需求基线：`docs/specification.md`
- 任务清单：`docs/tasks.md`
- 进度记录：`docs/progress.md`
