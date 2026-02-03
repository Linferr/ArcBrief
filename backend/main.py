"""FastAPI backend for ArcBrief."""

from datetime import datetime
import os
import threading
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from foreign_query_agent import QueryAgent, Settings
from foreign_query_agent.utils import slugify

from .state import RUNS, RunEvent, RunRecord
from .db import ArcBriefDB
from .collection import Collector, collect_for_topic
from .briefing import build_brief_for_topic
from .scheduler import ArcBriefScheduler


app = FastAPI(title="ArcBrief API")

# CORS配置 - 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB: ArcBriefDB | None = None
SCHEDULER: ArcBriefScheduler | None = None


class RunRequest(BaseModel):
    query: str


class RunResponse(BaseModel):
    run_id: str
    status: str


class StatusResponse(BaseModel):
    run_id: str
    status: str
    events: List[RunEvent]
    report_path: Optional[str] = None
    report_content: Optional[str] = None


class TopicCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    keywords: List[str] = Field(default_factory=list)
    rss_sources: List[str] = Field(default_factory=list)
    scrape_frequency_hours: int = 4
    push_time: str = "08:00"
    push_channels: List[str] = Field(default_factory=lambda: ["discord"])


class TopicResponse(BaseModel):
    id: int
    name: str
    keywords: List[str]
    rss_sources: List[str]
    scrape_frequency_hours: int
    push_time: str
    push_channels: List[str]
    is_active: bool


def _run_job(run_id: str, query: str) -> None:
    record = RUNS[run_id]
    record.status = "running"
    record.started_at = datetime.utcnow().isoformat()

    settings = Settings(output_dir="outputs")
    agent = QueryAgent(settings)

    def progress_cb(evt):
        record.events.append(RunEvent(**evt))

    report = agent.research(query, progress_cb=progress_cb)
    path = agent.save_report(report, settings.output_dir)

    record.report_path = path
    record.report_content = report
    record.status = "done"
    record.finished_at = datetime.utcnow().isoformat()


def _safe_report_path(path: str) -> Optional[str]:
    if not path:
        return None
    base_dir = os.path.abspath(os.getenv("FQ_OUTPUT_DIR", "outputs"))
    abs_path = os.path.abspath(path)
    try:
        if os.path.commonpath([abs_path, base_dir]) != base_dir:
            return None
    except Exception:
        return None
    return abs_path if os.path.exists(abs_path) else None


@app.on_event("startup")
def _startup() -> None:
    global DB, SCHEDULER
    db_path = os.getenv("ARCBRIEF_DB_PATH", "arcbrief.db")
    DB = ArcBriefDB(db_path)

    # Seed default topics if empty
    if DB.count_topics() == 0:
        defaults = [
            {
                "name": "Global Trending",
                "keywords": [
                    "Breaking News", "Geopolitics", "Sanctions", "Tech Breakthrough",
                    "Election", "Trade War", "Policy Change", "Global Economy"
                ],
                "rss_sources": [
                    "https://feeds.bbci.co.uk/news/world/rss.xml",
                    "https://feeds.reuters.com/Reuters/worldNews",
                    "https://www.aljazeera.com/xml/rss/all.xml",
                ],
                "scrape_frequency_hours": 4,
                "push_time": "08:00",
                "push_channels": ["discord"],
            },
            {
                "name": "Macro and Metals",
                "keywords": [
                    "Gold Price", "Spot Gold", "XAU", "Silver Price", "XAG",
                    "Federal Reserve", "Interest Rate", "Powell", "CPI",
                    "Inflation", "Treasury Yield"
                ],
                "rss_sources": [
                    "https://www.kitco.com/rss/news/",
                    "https://www.federalreserve.gov/feeds/press_all.xml",
                    "https://www.investing.com/rss/news_285.rss",
                ],
                "scrape_frequency_hours": 6,
                "push_time": "08:30",
                "push_channels": ["discord"],
            },
            {
                "name": "AI Daily",
                "keywords": [
                    "AI", "OpenAI", "Anthropic", "Claude", "GPT",
                    "LLM", "大模型", "机器学习", "深度学习"
                ],
                "rss_sources": [
                    "https://hnrss.org/frontpage",
                    "https://huggingface.co/blog/feed.xml",
                    "https://www.theverge.com/ai/rss/index.xml",
                ],
                "scrape_frequency_hours": 4,
                "push_time": "09:00",
                "push_channels": ["discord"],
            },
        ]
        for preset in defaults:
            DB.create_topic(preset)

    tavily_key = os.getenv("TAVILY_API_KEY", "")
    discord_token = os.getenv("DISCORD_TOKEN", "")
    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL", "")

    SCHEDULER = ArcBriefScheduler(
        DB,
        tavily_api_key=tavily_key,
        discord_token=discord_token,
        discord_webhook=discord_webhook
    )
    SCHEDULER.start()


@app.on_event("shutdown")
def _shutdown() -> None:
    if SCHEDULER:
        SCHEDULER.stop()


@app.post("/api/run", response_model=RunResponse)
def start_run(payload: RunRequest):
    run_id = f"{slugify(payload.query)}_{datetime.utcnow().strftime('%H%M%S')}"
    if run_id in RUNS:
        raise HTTPException(status_code=400, detail="Run already exists")
    record = RunRecord(run_id=run_id, query=payload.query)
    RUNS[run_id] = record
    thread = threading.Thread(target=_run_job, args=(run_id, payload.query), daemon=True)
    thread.start()
    return RunResponse(run_id=run_id, status="running")


@app.get("/api/status/{run_id}", response_model=StatusResponse)
def get_status(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail="Run not found")
    record = RUNS[run_id]
    return StatusResponse(
        run_id=record.run_id,
        status=record.status,
        events=record.events,
        report_path=record.report_path,
        report_content=record.report_content,
    )


@app.get("/api/history")
def get_history():
    return [
        {
            "run_id": r.run_id,
            "query": r.query,
            "status": r.status,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "report_path": r.report_path,
        }
        for r in RUNS.values()
    ]


@app.get("/api/report/{run_id}")
def get_report(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail="Run not found")
    record = RUNS[run_id]
    if record.report_content:
        return PlainTextResponse(record.report_content)
    safe_path = _safe_report_path(record.report_path or "")
    if safe_path:
        return FileResponse(safe_path, media_type="text/markdown")
    raise HTTPException(status_code=404, detail="Report not found")


@app.get("/api/report/{run_id}/download")
def download_report(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail="Run not found")
    record = RUNS[run_id]
    safe_path = _safe_report_path(record.report_path or "")
    if not safe_path:
        raise HTTPException(status_code=404, detail="Report not found")
    filename = os.path.basename(safe_path)
    return FileResponse(safe_path, media_type="text/markdown", filename=filename)


@app.post("/api/topics", response_model=TopicResponse)
def create_topic(payload: TopicCreateRequest):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    topic_id = DB.create_topic(payload.model_dump())
    topic = DB.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=500, detail="Topic creation failed")
    if SCHEDULER:
        SCHEDULER.refresh_jobs()
    return TopicResponse(**topic.__dict__)


@app.get("/api/topics", response_model=List[TopicResponse])
def list_topics():
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    return [TopicResponse(**t.__dict__) for t in DB.list_topics()]


@app.post("/api/topics/{topic_id}/collect")
def collect_topic(topic_id: int):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    topic = DB.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    collector = Collector()
    items = collect_for_topic(topic, collector)
    saved = DB.save_articles(topic.id, items)
    return {"topic_id": topic.id, "collected": len(items), "saved": saved}


@app.post("/api/topics/{topic_id}/brief")
def generate_brief(topic_id: int):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    topic = DB.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    items = DB.get_recent_articles(topic_id, hours=24)
    brief = build_brief_for_topic(topic, items)
    date_str = datetime.now().strftime("%Y-%m-%d")
    DB.save_brief(topic_id, date_str, brief, len(items))
    return {"topic_id": topic.id, "date": date_str, "items": len(items)}


@app.post("/api/topics/collect_all")
def collect_all():
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    collector = Collector()
    results = []
    for topic in DB.list_topics():
        items = collect_for_topic(topic, collector)
        saved = DB.save_articles(topic.id, items)
        results.append({"topic_id": topic.id, "topic_name": topic.name, "collected": len(items), "saved": saved})
    return {"total_topics": len(results), "results": results}


@app.post("/api/topics/brief_all")
def generate_brief_all():
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    results = []
    date_str = datetime.now().strftime("%Y-%m-%d")
    for topic in DB.list_topics():
        items = DB.get_recent_articles(topic.id, hours=24)
        brief = build_brief_for_topic(topic, items)
        DB.save_brief(topic.id, date_str, brief, len(items))
        results.append({"topic_id": topic.id, "topic_name": topic.name, "items": len(items)})
    return {"date": date_str, "total_topics": len(results), "results": results}


@app.get("/api/briefs/{topic_id}/latest")
def latest_brief(topic_id: int):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    brief = DB.get_latest_brief(topic_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    return brief


@app.get("/api/topics/{topic_id}/articles")
def get_articles(topic_id: int, hours: int = 24, sort: str = "time"):
    """获取主题的文章列表，支持排序"""
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    topic = DB.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    articles = DB.get_recent_articles(topic_id, hours=hours)

    # 排序
    if sort == "time":
        articles.sort(key=lambda x: x.get("published_at") or x.get("created_at") or "", reverse=True)
    elif sort == "title":
        articles.sort(key=lambda x: x.get("title", "").lower())
    # 可以扩展更多排序方式

    return {"topic_id": topic_id, "topic_name": topic.name, "count": len(articles), "articles": articles}


@app.put("/api/topics/{topic_id}")
def update_topic(topic_id: int, data: dict):
    """更新主题配置"""
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    topic = DB.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    import sqlite3
    import json

    updates = []
    params = []

    if "name" in data:
        updates.append("name = ?")
        params.append(data["name"])
    if "keywords" in data:
        updates.append("keywords = ?")
        params.append(json.dumps(data["keywords"], ensure_ascii=False))
    if "rss_sources" in data:
        updates.append("rss_sources = ?")
        params.append(json.dumps(data["rss_sources"], ensure_ascii=False))
    if "scrape_frequency_hours" in data:
        updates.append("scrape_frequency_hours = ?")
        params.append(data["scrape_frequency_hours"])
    if "push_time" in data:
        updates.append("push_time = ?")
        params.append(data["push_time"])
    if "is_active" in data:
        updates.append("is_active = ?")
        params.append(1 if data["is_active"] else 0)

    if not updates:
        return {"status": "no changes"}

    conn = sqlite3.connect(DB.db_path)
    sql = f"UPDATE topics SET {', '.join(updates)} WHERE id = ?"
    params.append(topic_id)
    conn.execute(sql, params)
    conn.commit()
    conn.close()

    if SCHEDULER:
        SCHEDULER.refresh_jobs()

    return {"status": "updated", "topic_id": topic_id}


@app.delete("/api/topics/{topic_id}")
def delete_topic(topic_id: int):
    """删除主题"""
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    topic = DB.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    import sqlite3
    conn = sqlite3.connect(DB.db_path)
    conn.execute("DELETE FROM briefs WHERE topic_id = ?", (topic_id,))
    conn.execute("DELETE FROM articles WHERE topic_id = ?", (topic_id,))
    conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
    conn.commit()
    conn.close()

    if SCHEDULER:
        SCHEDULER.refresh_jobs()

    return {"status": "deleted", "topic_id": topic_id}
