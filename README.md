# ArcBrief

ArcBrief 是一个本地优先的情报助手，具备两条核心能力：
- **Deep Research**（Agent + Host 研究流水线，输出报告）
- **Daily Brief**（RSS + Tavily 采集，关键词聚类，LLM 摘要）

本 README 与 `docs/specification.md` 保持一致，作为当前版本的对外说明。

---

## 1. 功能概览

### A. 每日简讯（News Feed）
- 采集：RSS + Tavily
- 聚类：关键词匹配（Phase 1）
- 摘要：LLM 优先，缺省时用正文片段兜底
- 输出内容包含：
  - 标题 + 日期
  - 摘要
  - 重点标题列表
  - 来源统计

### B. 深度研究（Deep Research）
- 用户输入问题
- Agent 流水线阶段：
  `outline → search → summary → host → reflection → final`
- 前端展示进度 + 报告预览
- 历史记录可查看

---

## 2. 技术栈（暂定）

- 后端：FastAPI 单体
- 数据库：SQLite（起步）
- 定时任务：APScheduler
- 采集：RSS (feedparser) + Tavily
- 聚类：关键词匹配（Phase 1）
- 摘要：LLM 可选，缺省时兜底
- 前端：Next.js
- 部署：本地优先

---

## 3. 项目结构

```
ArcBrief/
├─ foreign_query_agent/      # Query Agent 核心
├─ backend/                  # FastAPI + SQLite + Scheduler
├─ frontend/                 # Next.js 前端
├─ scripts/                  # 快速启动 / 主题管理
├─ logs/                     # 研究日志
├─ outputs/                  # 报告输出
├─ app.py                    # Streamlit 最小调试 UI
├─ discord_bot.py            # Discord Bot（可选）
├─ requirements.txt
└─ .env
```

---

## 4. 快速启动

### 4.1 安装后端依赖

```
cd d:\桌面\Agent\ArcBrief
pip install -r requirements.txt
```

### 4.2 配置环境变量

在项目根目录创建 `.env`：

```
FQ_LLM_API_KEY=your_key
FQ_LLM_BASE_URL=your_base_url
FQ_LLM_MODEL=your_model
TAVILY_API_KEY=your_tavily_key
ARCBRIEF_DB_PATH=arcbrief.db
```

可选（Discord）：
```
DISCORD_TOKEN=your_discord_bot_token
ARCBRIEF_API_BASE=http://localhost:8000/api
```

### 4.3 启动后端

```
uvicorn backend.main:app --reload --port 8000
```

### 4.4 启动前端

```
cd frontend
npm install
npm run dev
```

前端 API 地址（可选）：
```
NEXT_PUBLIC_API_BASE=http://localhost:8000/api
```

---

## 5. 核心 API

研究：
- `POST /api/run`
- `GET /api/status/{run_id}`
- `GET /api/history`

简讯：
- `POST /api/topics/collect_all`
- `POST /api/topics/brief_all`
- `GET /api/briefs/{topic_id}/latest`
- `GET /api/topics/{topic_id}/articles?hours=72&sort=time`

---

## 6. 默认主题

后端启动时自动注入 3 个默认主题：
- Global Trending
- Macro and Metals
- AI Daily

可在前端 Settings 页面修改。

---

## 7. 当前状态（对照需求）

已实现：
- Agent + Host 研究流程
- Daily Brief 流程（Phase 1）
- 关键词聚类 + 摘要
- 默认主题
- 前端 Research / News / Settings

未实现：
- RSS 稳定性监控
- Phase 2 LLM 归类
- 向量化 / pgvector
- Discord Bot 部署

---

## 8. 相关文档

- 需求文档：`docs/specification.md`
- 进度日志：`docs/Progress/progress.md`
- 任务清单：`docs/tasks.md`

---

## 9. 备注

- Phase 1 以“可跑 + 可解释”为目标
- Phase 2 以“摘要质量 + 自动分类”为优化目标
