# ArcBrief

> Local-first AI intelligence workstation — continuous tracking meets deep research in one product loop.

![Architecture](product_image/AecBrief.png)

ArcBrief is a deployable AI intelligence workstation with two core engines:
- **Daily Brief** — RSS collection, clustering, LLM synthesis, multi-channel push (Discord)
- **Deep Research** — multi-stage agent pipeline (Outline → Search → Summary → Host → Reflection → Formatting)

## Product Walkthrough

| Scene | Screenshot | Description |
|---|---|---|
| Daily Brief | ![Daily Brief](product_image/每日简报页面.jpg) | Topic-grouped briefs with one-click refresh, citation tracking, and structured card rendering. |
| Deep Research | ![Deep Research](product_image/research页面.jpg) | Multi-stage research flow with real-time progress, iterative search rounds, and full report preview. |
| Settings | ![Settings](product_image/settings页面.jpg) | Configure focus topics, keywords, search providers, LLM models, and push schedules. |
| Discord Push | ![Discord Push](product_image/每日dc推送.jpg) | Automated brief delivery to team channels — minimizing the gap between generation and consumption. |

## Technical Highlights

| Capability | Detail |
|---|---|
| Dual Engine | Daily Brief (breadth) + Deep Research (depth) in one product |
| Multi-Provider Search | Tavily, Bocha, Zhipu (GLM), Exa, plus Volcano Engine in degraded plain-chat compatibility mode until native web-search integration is added |
| Intelligence-Grade Prompts | First-principles analysis, cross-verification, confidence calibration, banned buzzword filtering |
| BFF Security Proxy | Frontend route classification (`public_get` / `guest_post` / `admin` / `forbidden`) — browser never sees backend keys |
| Multi-Language | English, Simplified Chinese, Japanese — all prompts, UI, and output |
| Observability | Search provider diagnostics, strict failure mode, per-request metadata |
| Export | One-click PDF export for briefs and research reports |
| Push | Discord bot with scheduled delivery |

## Architecture

```
Next.js 16 (App Router)          FastAPI Backend          SQLite
┌─────────────────┐       ┌─────────────────────┐    ┌──────────┐
│  BFF Proxy       │──────▶│  /api/brief          │───▶│  briefs  │
│  (classifyRoute) │       │  /api/research       │    │  reports │
│                  │       │  /api/topics          │    │  topics  │
│  MarkdownViewer  │       │  /api/settings        │    └──────────┘
│  ResearchPanel   │       │                       │
│  NewsFeedPanel   │       │  foreign_query_agent/ │
│  ArchivesPanel   │       │  ├── nodes/           │
└─────────────────┘       │  ├── prompts/         │
                           │  └── tools/           │
                           │      (factory.py)     │
                           └─────────────────────┘
```

## Quick Start

```bash
# Backend
pip install -r requirements.txt
cp .env.example .env          # fill in API keys
uvicorn backend.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Portfolio Report

- Product Case (Markdown): `docs/portfolio/arcbrief-product-case.md`
- Product Case (PDF): `docs/portfolio/ArcBrief_Product_Case_PM.pdf`
