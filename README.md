# ArcBrief

ArcBrief 是一个本地优先、可部署的 AI 情报工作台，面向两类核心场景：
- `Daily Brief`：面向固定 Topic 的自动采集、聚合与简报生成
- `Deep Research`：多阶段 Agent 研究流程与可追踪报告输出

当前版本已经完成前后端联通、数据持久化、定时任务、PDF 导出，以及 Discord 推送/命令集成的可运行闭环。

## Highlights

- 多阶段 Research Pipeline：`outline -> search -> summary -> host -> reflection -> final`
- Daily Brief 全链路：采集、过滤、聚类、摘要、历史查询
- All Topics Digest 视图：按 Topic 查看最新简报
- Topic 管理可持久化：启用/暂停状态写入数据库
- 报告导出：Research / Brief 均支持 PDF
- 部署就绪：Backend 可部署到 Railway，Frontend 可部署到 Vercel
- Discord 集成：Webhook 定时推送 + Slash Bot（`/topics`、`/brief`、`/research`）

## Tech Stack

- Backend: FastAPI + APScheduler
- Frontend: Next.js (App Router)
- Data: SQLite
- Collection: RSS (feedparser) + Tavily（可开关）
- Deploy: Railway (backend/bot) + Vercel (frontend)

## Project Structure

```text
ArcBrief/
├─ backend/                  # FastAPI API, scheduler, data pipeline
├─ foreign_query_agent/      # Research agent runtime
├─ frontend/                 # Next.js frontend
├─ discord_bot.py            # Discord slash bot
├─ Dockerfile                # Backend container
├─ Dockerfile.bot            # Bot container
├─ railway.json              # Railway config (backend)
├─ railway.bot.json          # Railway config (bot)
└─ .env.example
```

## Quick Start (Local)

1. 安装依赖

```bash
pip install -r requirements.txt
cd frontend && npm install
```

2. 配置环境变量（最小必填）

```env
FQ_LLM_API_KEY=...
FQ_LLM_BASE_URL=...
FQ_LLM_MODEL=...
ARCBRIEF_API_KEY=replace-with-your-key
```

说明：
- 完整模板见 `.env.example`
- 当前默认策略是 RSS-only（可在 `.env` 中切换 Tavily）

3. 启动服务

```bash
# Terminal 1
uvicorn backend.main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

访问：`http://localhost:3000`

## Deploy Snapshot

推荐部署拓扑：
- Backend: Railway（使用 `Dockerfile`）
- Frontend: Vercel（Root Directory = `frontend`）
- Discord Bot: Railway 第二服务（使用 `railway.bot.json` + `Dockerfile.bot`）

核心环境变量：
- Backend: `ARCBRIEF_API_KEY`、`ALLOWED_ORIGINS`、`ARCBRIEF_DB_PATH=/data/arcbrief.db`、`ARCBRIEF_SCHED_TZ`（例如 `America/Toronto`）
- Frontend: `NEXT_PUBLIC_API_BASE`、`NEXT_PUBLIC_ARCBRIEF_API_KEY`
- Bot: `DISCORD_TOKEN`、`ARCBRIEF_API_BASE`、`ARCBRIEF_API_KEY`

## Core APIs

Research:
- `POST /api/run`
- `GET /api/status/{run_id}`
- `GET /api/history`
- `GET /api/report/{run_id}`

Brief:
- `GET /api/topics`
- `POST /api/topics/{topic_id}/collect`
- `POST /api/topics/{topic_id}/brief`
- `POST /api/topics/collect_all`
- `POST /api/topics/brief_all`
- `GET /api/briefs/{topic_id}/latest`
- `GET /api/briefs/{topic_id}/history`

System:
- `GET /api/health`

## Default Topics

首次启动数据库为空时会注入：
- `Global Trending`（active）
- `Macro and Metals`（default inactive）
- `AI Daily`（active）

## Roadmap (Next)

- 提升 Brief 内容质量与覆盖率评估
- 完成 Topic 反馈闭环（feedback -> ranking）
- 强化生产安全（更细粒度认证与权限）
