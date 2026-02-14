"""FastAPI backend for ArcBrief."""

from datetime import datetime
from hashlib import sha256
import logging
import os
import threading
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse, Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from foreign_query_agent import QueryAgent, Settings
from foreign_query_agent.utils import slugify

from .state import RUNS, RunEvent, RunRecord
from .db import ArcBriefDB
from .collection import Collector, collect_for_topic
from .briefing import build_brief_for_topic
from .pdf_export import render_pdf
from .scheduler import ArcBriefScheduler


app = FastAPI(title="ArcBrief API")

APP_CONFIG_DEFAULTS = {
    "strict_academic_mode": True,
    "critical_analysis_layer": True,
    "cognitive_model": "Neutral (Fact-first)",
    "report_language": "English (US)",
    "primary_model": "Qwen3 MAX",
    "search_provider": "Tavily Search API",
    "entity_watchlist": "",
}

# ---------- Rate limiter (in-memory, per-key) ----------
_rate_buckets: Dict[str, List[float]] = {}
_rate_lock = threading.Lock()
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
MAX_CONCURRENT_RESEARCH = int(os.getenv("MAX_CONCURRENT_RESEARCH", "3"))
MAX_REFLECTIONS = int(os.getenv("FQ_MAX_REFLECTIONS", "3"))
_active_research = 0
_research_lock = threading.Lock()
_collecting_topics: Dict[int, bool] = {}
_collect_lock = threading.Lock()


def _check_rate_limit(key: str) -> bool:
    now = datetime.utcnow().timestamp()
    window = now - 60
    with _rate_lock:
        bucket = _rate_buckets.setdefault(key, [])
        _rate_buckets[key] = [t for t in bucket if t > window]
        if len(_rate_buckets[key]) >= RATE_LIMIT:
            return False
        _rate_buckets[key].append(now)
        return True

# CORS配置 - 白名单限制
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

DB: ArcBriefDB | None = None
SCHEDULER: ArcBriefScheduler | None = None
DEFAULT_LOCAL_API_KEY = "arcbrief-local-dev-key"
_STARTUP_TIME: Optional[str] = None
DISABLE_AUTH = os.getenv("ARCBRIEF_DISABLE_AUTH", "0") == "1"


def _default_topic_presets() -> List[Dict]:
    return [
        {
            "name": "Global Trending",
            "keywords": [
                "Geopolitics | Sanctions | Trade War",
                "Election | Referendum | Coup",
                "NATO | UN | G7 | G20 | BRICS",
                "War | Conflict | Ceasefire",
                "Policy | Legislation | Executive Order",
            ],
            "rss_sources": [
                "https://news.google.com/rss/search?q=site:reuters.com+world&hl=en-US&gl=US",
                "https://feeds.npr.org/1004/rss.xml",
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
                "https://www.aljazeera.com/xml/rss/all.xml",
                "https://www.theguardian.com/world/rss",
                "https://www.scmp.com/rss/91/feed",
                "https://www.foreignaffairs.com/rss.xml",
            ],
            "scrape_frequency_hours": 4,
            "push_time": "08:00",
            "push_channels": ["discord"],
        },
        {
            "name": "Macro and Metals",
            "is_active": False,
            "keywords": [
                "Gold | XAU | Silver | XAG | Platinum",
                "Federal Reserve | Fed | Powell | FOMC",
                "Interest Rate | Rate Cut | Rate Hike",
                "CPI | Inflation | PCE | PPI",
                "Treasury Yield | Bond | Dollar Index | DXY",
            ],
            "rss_sources": [
                "https://news.google.com/rss/search?q=site:kitco.com+gold&hl=en-US",
                "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
                "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
                "https://www.marketwatch.com/rss/topstories",
                "https://www.federalreserve.gov/feeds/press_all.xml",
                "https://www.federalreserve.gov/feeds/speeches.xml",
                "https://news.google.com/rss/search?q=site:treasury.gov&hl=en-US",
                "https://www.mining.com/feed/",
            ],
            "scrape_frequency_hours": 6,
            "push_time": "08:30",
            "push_channels": ["discord"],
        },
        {
            "name": "AI Daily",
            "keywords": [
                "OpenAI | Anthropic | Google DeepMind | Meta AI | Mistral | xAI",
                "GPT | Claude | Gemini | Llama | Qwen | reasoning model",
                "AI coding assistant | coding agent | Claude Code | Codex | OpenCode | Cursor | Cline",
                "Agent | MCP | tool calling | workflow | RAG | evals",
                "AI launch | model release | API update | benchmark | capability trend",
            ],
            "rss_sources": [
                "https://hnrss.org/newest?q=AI",
                "https://huggingface.co/blog/feed.xml",
                "https://venturebeat.com/feed/",
                "https://www.theverge.com/rss/index.xml",
                "https://www.marktechpost.com/feed/",
                "https://blog.google/technology/ai/rss/",
                "https://openai.com/blog/rss.xml",
                "https://deepmind.google/blog/rss.xml",
                "https://techcrunch.com/category/artificial-intelligence/feed/",
                "https://www.technologyreview.com/feed/",
                "http://export.arxiv.org/rss/cs.AI",
                "https://www.wired.com/feed/tag/ai/latest/rss",
                "https://simonwillison.net/atom/everything/",
                "https://minimaxir.com/index.xml",
                "https://www.geoffreylitt.com/feed.xml",
                "https://garymarcus.substack.com/feed",
                "https://www.wheresyoured.at/rss/",
                "https://www.dwarkeshpatel.com/feed",
                "https://joanwestenberg.com/rss",
                "https://grantslatton.com/rss.xml",
            ],
            "scrape_frequency_hours": 4,
            "push_time": "09:00",
            "push_channels": ["discord"],
        },
        {
            "name": "AI Builder Signals",
            "keywords": [
                "vibe coding | AI IDE | AI workflow | developer tools",
                "Claude Code | Codex | OpenCode | Cursor | Cline | Continue",
                "MCP | tool use | local model | retrieval | evals | prompt ops",
                "agent runtime | memory | planner | review loop | automation",
            ],
            "rss_sources": [
                "https://simonwillison.net/atom/everything/",
                "https://www.geoffreylitt.com/feed.xml",
                "https://overreacted.io/rss.xml",
                "https://mitchellh.com/feed.xml",
                "https://matklad.github.io/feed.xml",
                "https://skyfall.dev/rss.xml",
                "https://xania.org/feed",
                "https://danielchasehooper.com/feed.xml",
                "https://blog.jim-nielsen.com/feed.xml",
                "https://www.abortretry.fail/feed",
            ],
            "scrape_frequency_hours": 6,
            "push_time": "10:30",
            "push_channels": ["discord"],
        },
        {
            "name": "AI Policy & Safety",
            "keywords": [
                "AI policy | AI regulation | governance | compliance | risk framework",
                "EU AI Act | executive order | NIST AI RMF | ISO 42001 | OECD AI",
                "AI safety | alignment | red teaming | model eval | model card",
                "copyright lawsuit | antitrust | privacy | data protection | liability",
            ],
            "rss_sources": [
                "https://news.google.com/rss/search?q=EU+AI+Act&hl=en-US&gl=US&ceid=US:en",
                "https://news.google.com/rss/search?q=AI+safety+policy&hl=en-US&gl=US&ceid=US:en",
                "https://news.google.com/rss/search?q=AI+copyright+lawsuit&hl=en-US&gl=US&ceid=US:en",
                "https://www.technologyreview.com/feed/",
                "https://www.wired.com/feed/tag/ai/latest/rss",
                "https://www.theverge.com/rss/index.xml",
                "https://pluralistic.net/feed/",
                "https://anildash.com/feed.xml",
                "https://www.wheresyoured.at/rss/",
                "https://garymarcus.substack.com/feed",
            ],
            "scrape_frequency_hours": 6,
            "push_time": "11:00",
            "push_channels": ["discord"],
        },
    ]


def _sync_default_topic_sources(db: ArcBriefDB, defaults: List[Dict]) -> None:
    existing = {topic.name: topic for topic in db.list_topics()}
    for preset in defaults:
        if preset["name"] not in existing:
            db.create_topic(preset)


_LEGACY_PRESET_MARKERS: Dict[str, Dict[str, List[str]]] = {
    "Global Trending": {
        "rss": [
            "feeds.reuters.com/reuters/worldnews",
            "feeds.reuters.com/reuters/politicsnews",
            "www.state.gov/feed/",
            "www.whitehouse.gov/briefing-room/feed/",
        ],
        "keywords": ["breaking news", "tech breakthrough"],
    },
    "Macro and Metals": {
        "rss": [
            "www.kitco.com/rss/news/",
            "feeds.reuters.com/reuters/businessnews",
            "feeds.reuters.com/news/wealth",
            "home.treasury.gov/news/press-releases/feed",
        ],
        "keywords": ["spot gold", "treasury yield"],
    },
    "AI Daily": {
        "rss": [
            "https://venturebeat.com/ai/feed/",
            "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
        ],
        "keywords": ["stability aiperplexity", "xai，meta ai"],
    },
}


def _should_backfill_legacy_topic(topic) -> bool:
    markers = _LEGACY_PRESET_MARKERS.get(topic.name)
    if not markers:
        return False
    normalized_rss = [(u or "").strip().lower() for u in (topic.rss_sources or [])]
    normalized_keywords = [(k or "").strip().lower() for k in (topic.keywords or [])]
    hits = 0
    for marker in markers.get("rss", []):
        if any(marker in u for u in normalized_rss):
            hits += 1
    for marker in markers.get("keywords", []):
        if any(marker in kw for kw in normalized_keywords):
            hits += 1
    # Require at least two legacy hits to avoid overwriting intentionally customized topics.
    return hits >= 2


def _backfill_legacy_default_topics(db: ArcBriefDB, defaults: List[Dict]) -> int:
    defaults_by_name = {preset["name"]: preset for preset in defaults}
    updated = 0
    for topic in db.list_topics():
        preset = defaults_by_name.get(topic.name)
        if not preset:
            continue
        if not _should_backfill_legacy_topic(topic):
            continue
        db.update_topic(
            topic.id,
            {
                "keywords": preset.get("keywords", []),
                "rss_sources": preset.get("rss_sources", []),
                "scrape_frequency_hours": int(preset.get("scrape_frequency_hours", topic.scrape_frequency_hours)),
                "push_time": preset.get("push_time", topic.push_time),
                "push_channels": preset.get("push_channels", topic.push_channels),
                "is_active": bool(preset.get("is_active", topic.is_active)),
            },
        )
        updated += 1
        logger.info("Backfilled legacy default topic: %s (id=%s)", topic.name, topic.id)
    return updated


def _expected_api_key() -> str:
    raw = os.getenv("ARCBRIEF_API_KEY", "").strip()
    # Treat placeholder or empty values as "not configured" to avoid local mismatch.
    if raw in {"", "replace-with-your-key", "your_key", "changeme"}:
        return DEFAULT_LOCAL_API_KEY
    return raw or DEFAULT_LOCAL_API_KEY


@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    if request.method == "OPTIONS" or not request.url.path.startswith("/api/"):
        return await call_next(request)
    if DISABLE_AUTH:
        return await call_next(request)
    # Localhost dev bypass
    client_host = request.client.host if request.client else ""
    if client_host in {"127.0.0.1", "::1"}:
        return await call_next(request)
    # Health endpoint bypasses auth
    if request.url.path == "/api/health":
        return await call_next(request)
    provided = (request.headers.get("X-API-Key") or "").strip()
    if provided != _expected_api_key():
        return JSONResponse(status_code=401, content={"error_code": "UNAUTHORIZED", "message": "Invalid or missing API key"})
    if not _check_rate_limit(provided):
        return JSONResponse(status_code=429, content={"error_code": "RATE_LIMITED", "message": f"Rate limit exceeded ({RATE_LIMIT} req/min)"})
    return await call_next(request)


class RunRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


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
    name: str = Field(..., min_length=1, max_length=200)
    keywords: List[str] = Field(default_factory=list)
    rss_sources: List[str] = Field(default_factory=list)
    scrape_frequency_hours: int = Field(default=4, ge=1, le=168)
    push_time: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    push_channels: List[str] = Field(default_factory=lambda: ["discord"])


class TopicUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    keywords: Optional[List[str]] = None
    rss_sources: Optional[List[str]] = None
    scrape_frequency_hours: Optional[int] = Field(default=None, ge=1, le=168)
    push_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    push_channels: Optional[List[str]] = None
    is_active: Optional[bool] = None


class TopicResponse(BaseModel):
    id: int
    name: str
    keywords: List[str]
    rss_sources: List[str]
    scrape_frequency_hours: int
    push_time: str
    push_channels: List[str]
    is_active: bool


class AppConfigUpdateRequest(BaseModel):
    strict_academic_mode: Optional[bool] = None
    critical_analysis_layer: Optional[bool] = None
    cognitive_model: Optional[str] = None
    report_language: Optional[str] = None
    primary_model: Optional[str] = None
    search_provider: Optional[str] = None
    entity_watchlist: Optional[str] = None


def _sanitize_query(query: str) -> str:
    """Strip common prompt injection patterns from user query."""
    import re
    sanitized = query
    # Remove common injection delimiters
    for pattern in [
        r"```.*?```",                       # code blocks
        r"<\|.*?\|>",                       # special tokens
        r"(ignore|forget|disregard)\s+(all\s+)?(previous|above|prior)\s+(instructions|rules|prompts)",
        r"(system|assistant|user)\s*:",     # role injection
        r"(?i)\[INST\].*?\[/INST\]",       # instruction tags
    ]:
        sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE | re.DOTALL)
    # Limit to printable chars + CJK
    sanitized = re.sub(r"[^\w\s\u4e00-\u9fff\u3000-\u303f.,;:!?()@#$%&*+\-=/\[\]{}'\"|<>~`]", "", sanitized)
    return sanitized.strip()[:500]


def _parse_ts_for_sort(value: Optional[str]) -> datetime:
    if not value:
        return datetime.min
    raw = value.strip()
    # SQLite default timestamp: "YYYY-MM-DD HH:MM:SS"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo:
            dt = dt.astimezone(tz=None).replace(tzinfo=None)
        return dt
    except Exception:
        return datetime.min


def _get_voter_key(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",")[0].strip() if forwarded else ""
    if not ip and request.client:
        ip = request.client.host or ""
    raw = ip or "unknown"
    return sha256(raw.encode("utf-8")).hexdigest()


_MODEL_MAP = {
    "Qwen3 MAX": "qwen3-max",
    "GPT-4o mini (OpenAI)": "gpt-4o-mini",
    "GPT-4o (OpenAI)": "gpt-4o",
    "GPT-4.1 mini (OpenAI)": "gpt-4.1-mini",
    "Claude 3.5 Sonnet (Anthropic)": "claude-3-5-sonnet-20241022",
    "Gemini 1.5 Pro (Google)": "gemini-1.5-pro",
}


def _is_model_not_found_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "modelnotfound" in text
        or "does not exist or you do not have access to it" in text
        or "not_found_error" in text
    )


def _build_model_candidates(primary: str) -> List[str]:
    candidates: List[str] = []
    for model in [
        primary,
        os.getenv("FQ_LLM_MODEL", "").strip(),
        "gpt-4o-mini",
        "gpt-4.1-mini",
    ]:
        if model and model not in candidates:
            candidates.append(model)
    return candidates


def _run_job(run_id: str, query: str) -> None:
    record = RUNS[run_id]
    record.status = "running"
    record.started_at = datetime.utcnow().isoformat()

    try:
        settings = Settings(output_dir="outputs")
        selected_model = settings.llm_model

        # Apply app_config overrides
        if DB is not None:
            try:
                config = DB.get_app_config()
                merged = {**APP_CONFIG_DEFAULTS, **config}
                model_label = merged.get("primary_model", "")
                if model_label in _MODEL_MAP:
                    selected_model = _MODEL_MAP[model_label]
                if not merged.get("critical_analysis_layer", True):
                    settings.max_reflections = 1
            except Exception as cfg_err:
                logger.warning("Failed to read app_config for research: %s", cfg_err)
        settings.llm_model = selected_model

        model_candidates = _build_model_candidates(settings.llm_model)
        report = None
        path = None

        for idx, candidate_model in enumerate(model_candidates):
            settings.llm_model = candidate_model
            agent = QueryAgent(settings)

            def progress_cb(evt):
                record.events.append(RunEvent(**evt))

            safe_query = _sanitize_query(query)
            try:
                report = agent.research(safe_query, progress_cb=progress_cb)
                path = agent.save_report(report, settings.output_dir)
                if idx > 0:
                    record.events.append(
                        RunEvent(
                            stage="warning",
                            message=f"Primary model unavailable. Switched to fallback model: {candidate_model}",
                        )
                    )
                break
            except Exception as e:
                if _is_model_not_found_error(e) and idx < len(model_candidates) - 1:
                    record.events.append(
                        RunEvent(
                            stage="warning",
                            message=f"Model unavailable: {candidate_model}. Retrying with fallback model.",
                        )
                    )
                    continue
                raise

        if report is None or path is None:
            raise RuntimeError("No available model succeeded for this run.")

        record.report_path = path
        record.report_content = report
        record.status = "done"

    except Exception as e:
        error_msg = f"Research failed: {str(e)}"
        record.events.append(RunEvent(stage="error", message=error_msg))
        record.status = "failed"
        record.report_content = f"# Error\n\n{error_msg}\n\nPlease try again or adjust your query."

    finally:
        global _active_research
        with _research_lock:
            _active_research = max(_active_research - 1, 0)
        record.finished_at = datetime.utcnow().isoformat()
        # Persist to DB
        if DB is not None:
            try:
                DB.save_research_run(
                    run_id=record.run_id,
                    query=record.query,
                    status=record.status,
                    report_path=record.report_path,
                    report_content=record.report_content,
                    started_at=record.started_at,
                    finished_at=record.finished_at,
                )
            except Exception as db_err:
                logger.error("Failed to persist research run %s: %s", run_id, db_err)
                record.events.append(RunEvent(stage="warning", message=f"Report completed but DB save failed: {db_err}"))


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


@app.exception_handler(HTTPException)
async def unified_http_error(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": f"HTTP_{exc.status_code}", "message": exc.detail},
    )


@app.exception_handler(Exception)
async def unified_generic_error(request: Request, exc: Exception):
    logger.error("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error_code": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
    )


@app.on_event("startup")
def _startup() -> None:
    global DB, SCHEDULER, _STARTUP_TIME
    _STARTUP_TIME = datetime.utcnow().isoformat()
    db_path = os.getenv("ARCBRIEF_DB_PATH", "arcbrief.db")
    DB = ArcBriefDB(db_path)

    defaults = _default_topic_presets()
    if DB.count_topics() == 0:
        for preset in defaults:
            DB.create_topic(preset)
    else:
        _sync_default_topic_sources(DB, defaults)
        backfilled = _backfill_legacy_default_topics(DB, defaults)
        if backfilled:
            logger.info("Legacy default topic backfill updated %s topics.", backfilled)

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


@app.get("/api/health")
def health():
    return {"status": "ok", "started_at": _STARTUP_TIME, "db_connected": DB is not None}


@app.get("/api/system/status")
def system_status():
    jobs = []
    if SCHEDULER and SCHEDULER.scheduler.running:
        for job in SCHEDULER.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
    effective_max_reflections = MAX_REFLECTIONS
    if DB is not None:
        try:
            config = DB.get_app_config()
            merged = {**APP_CONFIG_DEFAULTS, **config}
            if not merged.get("critical_analysis_layer", True):
                effective_max_reflections = 1
        except Exception:
            pass
    return {
        "started_at": _STARTUP_TIME,
        "scheduler_running": SCHEDULER is not None and SCHEDULER.scheduler.running,
        "active_research": _active_research,
        "max_concurrent_research": MAX_CONCURRENT_RESEARCH,
        "max_reflections": effective_max_reflections,
        "rate_limit_per_min": RATE_LIMIT,
        "jobs": jobs,
    }


@app.get("/api/config")
def get_app_config():
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    current = DB.get_app_config()
    merged = dict(APP_CONFIG_DEFAULTS)
    merged.update(current)
    return merged


@app.put("/api/config")
def update_app_config(payload: AppConfigUpdateRequest):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        return {"status": "no changes"}
    DB.upsert_app_config(fields)
    current = DB.get_app_config()
    merged = dict(APP_CONFIG_DEFAULTS)
    merged.update(current)
    return {"status": "updated", "config": merged}


@app.post("/api/run", response_model=RunResponse)
def start_run(payload: RunRequest):
    global _active_research
    with _research_lock:
        if _active_research >= MAX_CONCURRENT_RESEARCH:
            raise HTTPException(status_code=429, detail=f"Too many concurrent research tasks (max {MAX_CONCURRENT_RESEARCH})")
        _active_research += 1
    run_id = f"{slugify(payload.query)}_{datetime.utcnow().strftime('%H%M%S')}"
    if run_id in RUNS:
        with _research_lock:
            _active_research -= 1
        raise HTTPException(status_code=400, detail="Run already exists")
    record = RunRecord(run_id=run_id, query=payload.query)
    RUNS[run_id] = record
    thread = threading.Thread(target=_run_job, args=(run_id, payload.query), daemon=True)
    thread.start()
    return RunResponse(run_id=run_id, status="running")


@app.get("/api/status/{run_id}", response_model=StatusResponse)
def get_status(run_id: str):
    if run_id in RUNS:
        record = RUNS[run_id]
        return StatusResponse(
            run_id=record.run_id,
            status=record.status,
            events=record.events,
            report_path=record.report_path,
            report_content=record.report_content,
        )
    if DB is not None:
        row = DB.get_research_run(run_id)
        if row:
            return StatusResponse(
                run_id=row["run_id"],
                status=row["status"],
                events=[],
                report_path=row.get("report_path"),
                report_content=row.get("report_content"),
            )
    raise HTTPException(status_code=404, detail="Run not found")


@app.get("/api/history")
def get_history(page: int = 1, size: int = 10, status: Optional[str] = None, q: Optional[str] = None):
    page = max(1, page)
    size = min(max(1, size), 50)
    # Merge in-memory (running) + DB (persisted) results
    memory_ids: set = set()
    results = []
    for r in RUNS.values():
        memory_ids.add(r.run_id)
        results.append({
            "run_id": r.run_id,
            "query": r.query,
            "status": r.status,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "report_path": r.report_path,
        })
    if DB is not None:
        for row in DB.list_research_runs(limit=200):
            if row["run_id"] not in memory_ids:
                results.append(row)
    # Filter
    if status:
        results = [r for r in results if r.get("status") == status]
    if q:
        q_lower = q.lower()
        results = [r for r in results if q_lower in (r.get("query") or "").lower()]
    results.sort(key=lambda x: x.get("started_at") or "", reverse=True)
    total = len(results)
    start = (page - 1) * size
    page_results = results[start:start + size]
    return {"total": total, "page": page, "size": size, "results": page_results}


@app.get("/api/report/{run_id}")
def get_report(run_id: str):
    report_content = None
    report_path = None
    if run_id in RUNS:
        record = RUNS[run_id]
        report_content = record.report_content
        report_path = record.report_path
    elif DB is not None:
        row = DB.get_research_run(run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        report_content = row.get("report_content")
        report_path = row.get("report_path")
    else:
        raise HTTPException(status_code=404, detail="Run not found")
    if report_content:
        return PlainTextResponse(report_content)
    safe_path = _safe_report_path(report_path or "")
    if safe_path:
        return FileResponse(safe_path, media_type="text/markdown")
    raise HTTPException(status_code=404, detail="Report not found")


@app.get("/api/report/{run_id}/download")
def download_report(run_id: str):
    report_path = None
    if run_id in RUNS:
        report_path = RUNS[run_id].report_path
    elif DB is not None:
        row = DB.get_research_run(run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        report_path = row.get("report_path")
    else:
        raise HTTPException(status_code=404, detail="Run not found")
    safe_path = _safe_report_path(report_path or "")
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
def collect_topic(topic_id: int, dry_run: bool = False):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    topic = DB.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    with _collect_lock:
        if _collecting_topics.get(topic_id):
            return {"topic_id": topic_id, "topic_name": topic.name, "status": "skipped", "reason": "collection already in progress"}
        _collecting_topics[topic_id] = True
    started = datetime.utcnow().isoformat()
    try:
        collector = Collector()
        result = collect_for_topic(topic, collector)
        items = result["items"]
        for h in result.get("rss_health", []):
            DB.upsert_rss_health(topic.id, h["rss_url"], h["status"], h["items_fetched"], last_error=h.get("last_error"))
        if dry_run:
            return {"topic_id": topic.id, "topic_name": topic.name, "collected": len(items), "saved": 0, "duplicates": 0, "status": "dry_run"}
        saved = DB.save_articles(topic.id, items)
        duplicates = max(len(items) - saved, 0)
        DB.log_brief_run(topic.id, "collect", "ok", len(items), saved, started_at=started)
        return {"topic_id": topic.id, "topic_name": topic.name, "collected": len(items), "saved": saved, "duplicates": duplicates, "status": "ok"}
    except Exception as e:
        DB.log_brief_run(topic.id, "collect", "failed", error_message=str(e), started_at=started)
        raise HTTPException(status_code=500, detail=f"Collect failed: {str(e)}")
    finally:
        with _collect_lock:
            _collecting_topics[topic_id] = False


def _load_brief_items(topic_id: int, date_str: str) -> List[Dict]:
    """Load articles for brief generation with same-day-first policy."""
    if DB is None:
        return []
    same_day_only = os.getenv("ARCBRIEF_BRIEF_SAME_DAY_ONLY", "1") == "1"
    if same_day_only:
        items = DB.get_articles_by_date(topic_id, date_str)
        if items:
            return items
        allow_fallback = os.getenv("ARCBRIEF_BRIEF_ALLOW_CROSS_DAY_FALLBACK", "0") == "1"
        if not allow_fallback:
            return []
    brief_hours = int(os.getenv("ARCBRIEF_NEWS_MAX_AGE_HOURS", "48"))
    return DB.get_recent_articles(topic_id, hours=brief_hours)


@app.post("/api/topics/{topic_id}/brief")
def generate_brief(topic_id: int):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    topic = DB.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    started = datetime.utcnow().isoformat()
    date_str = datetime.now().strftime("%Y-%m-%d")
    try:
        items = _load_brief_items(topic_id, date_str)
        source_weights = DB.get_source_reputations(topic_id)
        config = DB.get_app_config()
        merged_config = {**APP_CONFIG_DEFAULTS, **config}
        brief = build_brief_for_topic(topic, items, source_weights=source_weights, app_config=merged_config)
        DB.save_brief(topic_id, date_str, brief, len(items))
        DB.log_brief_run(topic.id, "brief", "ok", items_collected=len(items), started_at=started)
        return {"topic_id": topic.id, "date": date_str, "items": len(items)}
    except Exception as e:
        DB.log_brief_run(topic.id, "brief", "failed", error_message=str(e), started_at=started)
        raise HTTPException(status_code=500, detail=f"Brief generation failed: {str(e)}")


@app.post("/api/topics/collect_all")
def collect_all():
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    collector = Collector()
    results = []
    total_collected = 0
    total_saved = 0
    total_duplicates = 0
    failed_topics = 0
    skipped_topics = 0
    for topic in DB.list_topics():
        if not topic.is_active:
            skipped_topics += 1
            results.append({"topic_id": topic.id, "topic_name": topic.name, "status": "inactive"})
            continue
        with _collect_lock:
            if _collecting_topics.get(topic.id):
                skipped_topics += 1
                results.append({"topic_id": topic.id, "topic_name": topic.name, "status": "skipped"})
                continue
            _collecting_topics[topic.id] = True
        try:
            result = collect_for_topic(topic, collector)
            items = result["items"]
            for h in result.get("rss_health", []):
                DB.upsert_rss_health(topic.id, h["rss_url"], h["status"], h["items_fetched"], last_error=h.get("last_error"))
            saved = DB.save_articles(topic.id, items)
            duplicates = max(len(items) - saved, 0)
            total_collected += len(items)
            total_saved += saved
            total_duplicates += duplicates
            results.append({"topic_id": topic.id, "topic_name": topic.name, "collected": len(items), "saved": saved, "duplicates": duplicates, "status": "ok"})
        except Exception as e:
            failed_topics += 1
            results.append({"topic_id": topic.id, "topic_name": topic.name, "collected": 0, "saved": 0, "duplicates": 0, "status": "failed", "error": str(e)})
        finally:
            with _collect_lock:
                _collecting_topics[topic.id] = False
    return {
        "total_topics": len(results),
        "success_topics": len(results) - failed_topics - skipped_topics,
        "failed_topics": failed_topics,
        "skipped_topics": skipped_topics,
        "total_collected": total_collected,
        "total_saved": total_saved,
        "total_duplicates": total_duplicates,
        "results": results,
    }


@app.post("/api/topics/brief_all")
def generate_brief_all():
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    results = []
    date_str = datetime.now().strftime("%Y-%m-%d")
    config = DB.get_app_config()
    merged_config = {**APP_CONFIG_DEFAULTS, **config}
    for topic in DB.list_topics():
        if not topic.is_active:
            continue
        items = _load_brief_items(topic.id, date_str)
        source_weights = DB.get_source_reputations(topic.id)
        brief = build_brief_for_topic(topic, items, source_weights=source_weights, app_config=merged_config)
        DB.save_brief(topic.id, date_str, brief, len(items))
        results.append({"topic_id": topic.id, "topic_name": topic.name, "items": len(items)})
    return {"date": date_str, "total_topics": len(results), "results": results}


@app.get("/api/briefs/recent")
def recent_briefs(limit: int = 40, topic_id: Optional[int] = None):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    if topic_id is not None:
        topic = DB.get_topic(topic_id)
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")
    rows = DB.list_recent_briefs(limit=limit, topic_id=topic_id)
    return {"count": len(rows), "items": rows}


@app.get("/api/briefs/{topic_id}/latest")
def latest_brief(topic_id: int):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    brief = DB.get_latest_brief(topic_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    return brief


@app.get("/api/briefs/{topic_id}/history")
def brief_history(topic_id: int, limit: int = 7):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    return DB.list_briefs(topic_id, limit=min(limit, 30))


def _extract_domain(url: str) -> str:
    """Extract hostname from URL, stripping www. prefix."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or url
        return host.replace("www.", "")
    except Exception:
        return url


@app.post("/api/briefs/{brief_id}/feedback")
def submit_brief_feedback(request: Request, brief_id: int, rating: int = 1):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    if rating not in (-1, 1):
        raise HTTPException(status_code=400, detail="Rating must be -1 or 1")
    voter_key = _get_voter_key(request)
    previous_rating = DB.get_brief_feedback_rating(brief_id, voter_key)
    DB.save_brief_feedback(brief_id, rating, voter_key)

    # Propagate feedback to source reputation
    try:
        brief = DB.get_brief_by_id(brief_id)
        if brief:
            topic_id = brief["topic_id"]
            articles = DB.get_articles_by_date(topic_id, brief["date"])
            # Apply only net vote change, so repeated same vote does not keep boosting.
            delta = (rating - (previous_rating or 0)) * 0.1
            domains: List[str] = []
            for article in articles:
                source_url = article.get("url") or article.get("source") or ""
                if not source_url:
                    continue
                domain = _extract_domain(source_url)
                if domain:
                    domains.append(domain)
            unique_domains = sorted(set(domains))
            if delta != 0 and unique_domains:
                per_domain_delta = delta / len(unique_domains)
                for domain in unique_domains:
                    DB.update_source_reputation(topic_id, domain, per_domain_delta)
    except Exception as e:
        logger.warning("Reputation propagation failed for brief %s: %s", brief_id, e)

    return DB.get_brief_feedback_stats(brief_id)


@app.get("/api/briefs/{brief_id}/feedback")
def get_brief_feedback(brief_id: int):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    return DB.get_brief_feedback_stats(brief_id)


@app.get("/api/briefs/{brief_id}/export")
def export_brief(brief_id: int):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    brief = DB.get_brief_by_id(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    topic = DB.get_topic(brief["topic_id"])
    topic_name = topic.name if topic else f"Topic {brief['topic_id']}"
    brief_hours = int(os.getenv("ARCBRIEF_NEWS_MAX_AGE_HOURS", "48"))

    header = (
        f"---\n"
        f"topic: {topic_name}\n"
        f"date: {brief['date']}\n"
        f"generated: {brief.get('created_at', 'N/A')}\n"
        f"articles: {brief.get('item_count', 0)}\n"
        f"time_window: {brief_hours}h\n"
        f"---\n\n"
    )
    content = header + (brief.get("content") or "")
    filename = f"ArcBrief_{topic_name.replace(' ', '_')}_{brief['date']}.md"
    return PlainTextResponse(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/briefs/{brief_id}/export/pdf")
def export_brief_pdf(brief_id: int):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    brief = DB.get_brief_by_id(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    topic = DB.get_topic(brief["topic_id"])
    topic_name = topic.name if topic else f"Topic {brief['topic_id']}"
    date_str = brief.get("date", "")
    try:
        pdf_bytes = render_pdf(
            brief.get("content") or "",
            f"{topic_name} Daily Brief",
            {"date": date_str, "item_count": str(brief.get("item_count", ""))},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
    filename = f"ArcBrief_{topic_name.replace(' ', '_')}_{date_str}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/report/{run_id}/export/pdf")
def export_report_pdf(run_id: str):
    report_content = None
    query = run_id
    if run_id in RUNS:
        record = RUNS[run_id]
        report_content = record.report_content
        query = record.query
    elif DB is not None:
        row = DB.get_research_run(run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        report_content = row.get("report_content")
        query = row.get("query") or run_id
    else:
        raise HTTPException(status_code=404, detail="Run not found")
    if not report_content:
        raise HTTPException(status_code=404, detail="Report content not available")
    try:
        pdf_bytes = render_pdf(
            report_content,
            f"Research Report: {query[:80]}",
            {"date": datetime.now().strftime("%Y-%m-%d"), "run_id": run_id},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
    safe_name = slugify(query[:50]) or "report"
    filename = f"ArcBrief_Report_{safe_name}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/topics/{topic_id}/run-stats")
def get_topic_run_stats(topic_id: int):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    return DB.get_brief_run_stats(topic_id, limit=20)


@app.get("/api/topics/{topic_id}/rss-health")
def get_topic_rss_health(topic_id: int):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    topic = DB.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return {"topic_id": topic_id, "topic_name": topic.name, "sources": DB.get_rss_health(topic_id)}


@app.get("/api/rss-health")
def get_all_rss_health():
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    return {"sources": DB.get_all_rss_health()}


@app.get("/api/topics/{topic_id}/articles")
def get_articles(topic_id: int, hours: int = 24, sort: str = "time", date: Optional[str] = None):
    """获取主题的文章列表，支持按日期或时间窗口筛选"""
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    topic = DB.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    if date:
        articles = DB.get_articles_by_date(topic_id, date)
    else:
        articles = DB.get_recent_articles(topic_id, hours=hours)

    # 排序
    if sort == "time":
        articles.sort(
            key=lambda x: _parse_ts_for_sort(x.get("published_at") or x.get("created_at")),
            reverse=True,
        )
    elif sort == "title":
        articles.sort(key=lambda x: x.get("title", "").lower())
    # 可以扩展更多排序方式

    enriched = []
    for item in articles:
        row = dict(item)
        row["time_source"] = "published_at" if row.get("published_at") else "fallback(created_at)"
        enriched.append(row)

    return {"topic_id": topic_id, "topic_name": topic.name, "count": len(enriched), "articles": enriched}


@app.put("/api/topics/{topic_id}")
def update_topic(topic_id: int, payload: TopicUpdateRequest):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    topic = DB.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    fields = payload.model_dump(exclude_none=True)
    if not fields:
        return {"status": "no changes"}

    DB.update_topic(topic_id, fields)

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
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("DELETE FROM clusters WHERE brief_id IN (SELECT id FROM briefs WHERE topic_id = ?)", (topic_id,))
        conn.execute("DELETE FROM brief_runs WHERE topic_id = ?", (topic_id,))
        conn.execute("DELETE FROM rss_health WHERE topic_id = ?", (topic_id,))
        conn.execute("DELETE FROM briefs WHERE topic_id = ?", (topic_id,))
        conn.execute("DELETE FROM articles WHERE topic_id = ?", (topic_id,))
        conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")
    finally:
        conn.close()

    if SCHEDULER:
        SCHEDULER.refresh_jobs()

    return {"status": "deleted", "topic_id": topic_id}
