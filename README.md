# ArcBrief

ArcBrief 是一个本地优先、可部署的 AI 情报工作台，聚焦两条主线：
- `Daily Brief`：RSS 采集、聚合、简报生成与多端推送
- `Deep Research`：多阶段 Agent 流程（Outline -> Search -> Summary -> Host -> Reflection -> Final）

当前版本已覆盖前后端联通、SQLite 持久化、定时任务、PDF 导出与 Discord Bot 交互。

## Highlights

- 多阶段 Research Pipeline（可追踪事件流）
- Daily Brief 全链路（采集、过滤、聚类、摘要、归档）
- Brief/Report 一键导出 PDF
- 前端同源 BFF 代理，浏览器不暴露后端密钥
- 公开演示安全基线：只读公开 + 限额交互 + 管理操作默认关闭

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
cd frontend 
npm install
```

2. 配置环境变量（最小必填）

```env
FQ_LLM_API_KEY=...
FQ_LLM_BASE_URL=...
FQ_LLM_MODEL=...
ARCBRIEF_API_KEY=replace-with-your-key
ARCBRIEF_PUBLIC_API_KEY=replace-with-public-key
```

完整变量见 `.env.example`。

3. 启动服务

```bash
# Terminal 1
uvicorn backend.main:app --reload --port 8000

# Terminal 2
cd frontend 
npm run dev
```

访问：`http://localhost:3000`

## Deploy Snapshot

推荐拓扑：
- Backend: Railway（`Dockerfile`）
- Frontend: Vercel（Root Directory=`frontend`）
- Discord Bot: Railway 第二服务（`railway.bot.json` + `Dockerfile.bot`）

关键环境变量：
- Backend:
  - `ARCBRIEF_API_KEY`
  - `ARCBRIEF_PUBLIC_API_KEY`
  - `ARCBRIEF_PUBLIC_READ_RATE_LIMIT_PER_MIN`
  - `ARCBRIEF_PUBLIC_EXPORT_RATE_LIMIT_PER_MIN`
  - `ARCBRIEF_RATE_LIMIT_STORAGE_URI`（生产建议 Redis）
  - `ARCBRIEF_RESEARCH_STRICT_PROVIDER=1`（provider 不可用时 Research 直接失败）
  - `ZHIPU_OPENAI_BASE_URL`、`ZHIPU_WEB_SEARCH_MODEL`
  - `VOLCENGINE_OPENAI_BASE_URL`、`VOLCENGINE_MODEL_EP`
  - `ARCBRIEF_PROXY_SIGNING_SECRET`
  - `ALLOWED_ORIGINS`
  - `ARCBRIEF_DB_PATH=/data/arcbrief.db`
- Frontend (BFF):
  - `ARCBRIEF_PROXY_API_BASE`
  - `ARCBRIEF_PROXY_API_KEY`（必须使用 `ARCBRIEF_PUBLIC_API_KEY`，不可使用 admin key）
  - `ARCBRIEF_PROXY_SIGNING_SECRET`（与后端一致）
  - `NEXT_PUBLIC_ARCBRIEF_ENABLE_ADMIN_ACTIONS=0`（公开演示默认）
- Bot:
  - `DISCORD_TOKEN`
  - `ARCBRIEF_API_BASE`
  - `ARCBRIEF_API_KEY`

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

## Security Notes (Phase 3A.1)

- 前端 BFF 仅放行：公开 GET + `POST /run` + `POST /chat`
- 管理写接口不再经公网 BFF 暴露
- 后端不再信任裸 `X-Forwarded-For`，仅信任带签名的 `X-Arcbrief-*` 头
- 公开 GET 端点纳入独立限流策略
- 限流支持 Redis 共享桶，避免多实例失效

## Provider Notes (Phase 3A.4)

- OpenAI 兼容 provider：`Zhipu`、`Volcano`
- 自定义搜索 API provider：`Exa`、`Bocha`、`Tavily`
- Diagnostics 为实时探测语义：当 provider 不可用时 `Effective provider = Unavailable`

## Default Topics

首次启动数据库为空时会注入：
- `Global Trending`（active）
- `Macro and Metals`（default inactive）
- `AI Daily`（active）

## Roadmap

- 提升 Brief 覆盖率与质量评估
- 强化 Topic 反馈闭环（feedback -> ranking）
- 继续完善公开演示安全基线与可观测性
