"""FastAPI backend for ArcBrief."""

from datetime import datetime, timedelta
import hmac
from hashlib import sha256
import ipaddress
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse, Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from foreign_query_agent import QueryAgent, Settings
from foreign_query_agent.tools.factory import ProviderUnavailableError, create_search_tool_with_meta
from foreign_query_agent.tools.openai_compat_search import classify_provider_error
from foreign_query_agent.utils import slugify

from .state import RUNS, RunEvent, RunRecord
from .constants import APP_CONFIG_DEFAULTS
from .db import ArcBriefDB
from .collection import Collector, collect_for_topic
from .briefing import build_brief_for_topic, llm_chat
from .pdf_export import render_pdf
from .rate_limit import RateLimiter
from .scraper import fetch_tldr_document, validate_public_http_url
from .scheduler import ArcBriefScheduler


app = FastAPI(title="ArcBrief API")

# ---------- Rate limits ----------
ADMIN_RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
PUBLIC_RATE_LIMIT = int(os.getenv("ARCBRIEF_PUBLIC_RATE_LIMIT_PER_MIN", "15"))
PUBLIC_READ_RATE_LIMIT = int(os.getenv("ARCBRIEF_PUBLIC_READ_RATE_LIMIT_PER_MIN", "60"))
PUBLIC_EXPORT_RATE_LIMIT = int(os.getenv("ARCBRIEF_PUBLIC_EXPORT_RATE_LIMIT_PER_MIN", "10"))
RUN_ROUTE_LIMIT = int(os.getenv("ARCBRIEF_ROUTE_LIMIT_RUN_PER_MIN", "4"))
CHAT_ROUTE_LIMIT = int(os.getenv("ARCBRIEF_ROUTE_LIMIT_CHAT_PER_MIN", "8"))
ADMIN_ROUTE_LIMIT_MULTIPLIER = int(os.getenv("ARCBRIEF_ADMIN_ROUTE_LIMIT_MULTIPLIER", "10"))
RATE_LIMIT_STORAGE_URI = os.getenv("ARCBRIEF_RATE_LIMIT_STORAGE_URI", "")
MAX_CONCURRENT_RESEARCH = int(os.getenv("MAX_CONCURRENT_RESEARCH", "3"))
MAX_CONCURRENT_CHAT = int(os.getenv("MAX_CONCURRENT_CHAT", "10"))
MAX_REFLECTIONS = int(os.getenv("FQ_MAX_REFLECTIONS", "3"))
RUNS_TTL_HOURS = int(os.getenv("ARCBRIEF_RUNS_TTL_HOURS", "24"))
RUNS_MAX_RECORDS = int(os.getenv("ARCBRIEF_RUNS_MAX_RECORDS", "500"))
SIGNED_IP_WINDOW_SECONDS = int(os.getenv("ARCBRIEF_PROXY_SIGNED_IP_MAX_AGE_SECONDS", "60"))
PROXY_SIGNING_SECRET = (os.getenv("ARCBRIEF_PROXY_SIGNING_SECRET", "") or "").strip()
_RATE_LIMITER = RateLimiter(RATE_LIMIT_STORAGE_URI)
_active_research = 0
_research_lock = threading.Lock()
_active_chat = 0
_chat_lock = threading.Lock()
_collecting_topics: Dict[int, bool] = {}
_collect_lock = threading.Lock()
_diagnostics_lock = threading.Lock()
_LAST_SEARCH_DIAGNOSTICS: Dict[str, Any] = {
    "search_provider_configured": APP_CONFIG_DEFAULTS.get("search_provider", "Tavily Search API"),
    "search_provider_effective": APP_CONFIG_DEFAULTS.get("search_provider", "Tavily Search API"),
    "search_provider_fallback": "",
    "search_llm_assisted": False,
}


def _snapshot_search_diagnostics() -> Dict[str, Any]:
    with _diagnostics_lock:
        snap = dict(_LAST_SEARCH_DIAGNOSTICS)
    return {
        "search_provider_configured": snap.get("search_provider_configured", "Tavily Search API"),
        "search_provider_effective": snap.get("search_provider_effective", "Unavailable"),
        "search_provider_fallback": snap.get("search_provider_fallback", ""),
        "search_llm_assisted": bool(snap.get("search_llm_assisted", False)),
    }


def _tool_attr(tool: Any, name: str, default: Any = "") -> Any:
    value = getattr(tool, name, None)
    if value not in (None, ""):
        return value
    client = getattr(tool, "client", None)
    if client is not None:
        client_value = getattr(client, name, None)
        if client_value not in (None, ""):
            return client_value
    return default


def _provider_check_status(tool: Any, response: Any) -> tuple[str, Optional[str], str]:
    error_class = str(_tool_attr(tool, "last_error_class", "") or "").strip()
    error_detail = str(_tool_attr(tool, "last_error_message", "") or "").strip() or None
    search_mode = str(_tool_attr(tool, "search_mode", "search_api") or "search_api")

    if error_class:
        return error_class, error_detail, search_mode

    results = list(getattr(response, "results", []) or [])
    if search_mode == "plain_chat":
        has_structured_urls = any((getattr(item, "url", "") or "").strip() for item in results)
        if results and not has_structured_urls:
            return "degraded_plain_chat", "Plain-chat fallback returned ungrounded text without source URLs.", search_mode

    status = "ok" if results else "empty_results"
    return status, error_detail, search_mode


_PUBLIC_READ_PATTERNS = (
    re.compile(r"^/api/health$"),
    re.compile(r"^/api/topics$"),
    re.compile(r"^/api/briefs/recent$"),
)
_PUBLIC_EXPORT_PATTERNS = (
    re.compile(r"^/api/briefs/\d+/export$"),
    re.compile(r"^/api/briefs/\d+/export/pdf$"),
)
_GUEST_POST_PATHS = frozenset({"/api/run", "/api/chat"})
_SUPPORTED_LANGUAGES = frozenset({"English (US)", "Chinese (Simplified)", "Japanese"})


def _check_rate_limit(bucket_key: str, limit: int) -> bool:
    return _RATE_LIMITER.allow(bucket_key, max(1, limit), window_seconds=60)


def _check_route_rate_limit(route: str, identity: str, limit: int) -> bool:
    return _check_rate_limit(f"route:{route}:{identity}", limit)


def _public_rate_limit_for_path(path: str) -> Optional[tuple[str, int]]:
    if any(pattern.match(path) for pattern in _PUBLIC_EXPORT_PATTERNS):
        return ("export", PUBLIC_EXPORT_RATE_LIMIT)
    if any(pattern.match(path) for pattern in _PUBLIC_READ_PATTERNS):
        return ("read", PUBLIC_READ_RATE_LIMIT)
    return None

# CORS - whitelist origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-API-Key",
        "X-Arcbrief-Client-Ip",
        "X-Arcbrief-Client-Ts",
        "X-Arcbrief-Client-Sig",
    ],
)

DB: ArcBriefDB | None = None
SCHEDULER: ArcBriefScheduler | None = None
DEFAULT_LOCAL_API_KEY = "arcbrief-local-dev-key"
DEFAULT_PUBLIC_API_KEY = "arcbrief-public-demo-key"
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


def _expected_admin_api_key() -> str:
    raw = os.getenv("ARCBRIEF_API_KEY", "").strip()
    # Treat placeholder or empty values as "not configured" to avoid local mismatch.
    if raw in {"", "replace-with-your-key", "your_key", "changeme"}:
        return DEFAULT_LOCAL_API_KEY
    return raw or DEFAULT_LOCAL_API_KEY


def _expected_public_api_key() -> str:
    raw = os.getenv("ARCBRIEF_PUBLIC_API_KEY", "").strip()
    if raw in {"", "replace-with-your-key", "your_public_key", "changeme"}:
        return DEFAULT_PUBLIC_API_KEY
    return raw or DEFAULT_PUBLIC_API_KEY


def _normalize_language(language: Optional[str]) -> str:
    candidate = (language or "").strip()
    if candidate in _SUPPORTED_LANGUAGES:
        return candidate
    return "English (US)"


def _is_valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _signed_client_ip(request: Request) -> Optional[str]:
    if not PROXY_SIGNING_SECRET:
        return None
    ip = (request.headers.get("X-Arcbrief-Client-Ip") or "").strip()
    ts_raw = (request.headers.get("X-Arcbrief-Client-Ts") or "").strip()
    sig = (request.headers.get("X-Arcbrief-Client-Sig") or "").strip().lower()
    if not ip or not ts_raw or not sig or not _is_valid_ip(ip):
        return None
    try:
        ts_val = int(ts_raw)
    except ValueError:
        return None
    now = int(time.time())
    if abs(now - ts_val) > max(1, SIGNED_IP_WINDOW_SECONDS):
        return None
    expected = hmac.new(
        PROXY_SIGNING_SECRET.encode("utf-8"),
        f"{ip}.{ts_raw}".encode("utf-8"),
        sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    return ip


def _client_ip(request: Request) -> str:
    trusted = _signed_client_ip(request)
    if trusted:
        return trusted
    if request.client and request.client.host and _is_valid_ip(request.client.host):
        return request.client.host
    return "unknown"


def _client_fingerprint(request: Request) -> str:
    return sha256(_client_ip(request).encode("utf-8")).hexdigest()


def _is_public_read_endpoint(request: Request) -> bool:
    if request.method != "GET":
        return False
    path = request.url.path
    return _public_rate_limit_for_path(path) is not None


def _route_limit_for(path: str, role: str) -> Optional[int]:
    if path == "/api/run":
        base = RUN_ROUTE_LIMIT
    elif path == "/api/chat":
        base = CHAT_ROUTE_LIMIT
    else:
        return None
    if role == "admin":
        return max(base * max(1, ADMIN_ROUTE_LIMIT_MULTIPLIER), base)
    return base


@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    if request.method == "OPTIONS" or not request.url.path.startswith("/api/"):
        return await call_next(request)
    if DISABLE_AUTH:
        return await call_next(request)
    path = request.url.path
    identity = _client_fingerprint(request)
    if _is_public_read_endpoint(request):
        public_limit = _public_rate_limit_for_path(path)
        if public_limit:
            bucket_name, bucket_limit = public_limit
            if not _check_rate_limit(f"public:{bucket_name}:{identity}", bucket_limit):
                return JSONResponse(
                    status_code=429,
                    content={
                        "error_code": "RATE_LIMITED_PUBLIC",
                        "message": f"Public rate limit exceeded ({bucket_limit} req/min)",
                    },
                )
        return await call_next(request)

    provided = (request.headers.get("X-API-Key") or "").strip()
    admin_key = _expected_admin_api_key()
    public_key = _expected_public_api_key()

    role: Optional[str] = None
    if provided == admin_key:
        role = "admin"
    elif path in _GUEST_POST_PATHS and provided == public_key:
        role = "guest"

    if role is None:
        return JSONResponse(
            status_code=401,
            content={"error_code": "UNAUTHORIZED", "message": "Invalid or missing API key"},
        )

    if path not in _GUEST_POST_PATHS and role != "admin":
        return JSONResponse(
            status_code=403,
            content={"error_code": "FORBIDDEN", "message": "This endpoint requires admin privileges"},
        )

    per_key_limit = ADMIN_RATE_LIMIT if role == "admin" else PUBLIC_RATE_LIMIT
    key_hash = sha256(provided.encode("utf-8")).hexdigest()
    if not _check_rate_limit(f"global:{role}:{key_hash}", per_key_limit):
        return JSONResponse(
            status_code=429,
            content={"error_code": "RATE_LIMITED", "message": f"Rate limit exceeded ({per_key_limit} req/min)"},
        )

    route_limit = _route_limit_for(path, role)
    if route_limit is not None and not _check_route_rate_limit(path, identity, route_limit):
        return JSONResponse(
            status_code=429,
            content={
                "error_code": "ROUTE_RATE_LIMITED",
                "message": f"Route rate limit exceeded for {path} ({route_limit} req/min)",
            },
        )
    return await call_next(request)


class RunRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    language: Optional[str] = Field(default=None, max_length=64)


class AnalyzeRequest(BaseModel):
    product: str = Field(..., min_length=1, max_length=500)
    language: Optional[str] = Field(default=None, max_length=64)


class BookmarkCreateRequest(BaseModel):
    user_id: str = Field(..., min_length=3, max_length=128)
    brief_id: int = Field(..., gt=0)
    note: Optional[str] = Field(default=None, max_length=280)


class RunResponse(BaseModel):
    run_id: str
    status: str
    language_used: str


class StatusResponse(BaseModel):
    run_id: str
    status: str
    events: List[RunEvent]
    report_path: Optional[str] = None
    report_content: Optional[str] = None
    language_used: Optional[str] = None


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
    brief_generation_framework: Optional[str] = None
    research_recency_mode: Optional[str] = None
    entity_watchlist: Optional[str] = None


class BriefGenerateRequest(BaseModel):
    language: Optional[str] = Field(default=None, max_length=64)


class DigestGenerateRequest(BaseModel):
    date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    language: Optional[str] = Field(default=None, max_length=64)


class RefreshRequest(BaseModel):
    scope: Literal["digest", "topic", "all"]
    topic_id: Optional[int] = Field(default=None, gt=0)
    language: Optional[str] = Field(default=None, max_length=64)
    push: bool = True


def _sanitize_query(query: str) -> str:
    """Strip common prompt injection patterns from user query."""
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


def _estimate_source_count(report_content: Optional[str]) -> int:
    if not report_content:
        return 0

    lines = report_content.splitlines()
    in_sources = False
    source_lines: List[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^#{1,6}\s*sources?\b", line, flags=re.IGNORECASE):
            in_sources = True
            continue
        if in_sources and line.startswith("#"):
            break
        if in_sources and re.match(r"^(-|\*|\d+\.)\s+", line):
            source_lines.append(re.sub(r"^(-|\*|\d+\.)\s+", "", line).strip().lower())

    if source_lines:
        return len({s for s in source_lines if s})

    urls = re.findall(r"https?://[^\s)>\"]+", report_content)
    return len(set(urls))


def _get_voter_key(request: Request) -> str:
    return sha256(_client_ip(request).encode("utf-8")).hexdigest()


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


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(tz=None).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _cleanup_inmemory_runs() -> int:
    cutoff = datetime.utcnow() - timedelta(hours=max(1, RUNS_TTL_HOURS))
    to_remove: set[str] = set()

    for run_id, record in list(RUNS.items()):
        finished_dt = _parse_iso(record.finished_at)
        started_dt = _parse_iso(record.started_at)
        anchor = finished_dt or started_dt
        if anchor and anchor < cutoff:
            to_remove.add(run_id)

    if len(RUNS) - len(to_remove) > RUNS_MAX_RECORDS:
        remaining = [(rid, rec) for rid, rec in RUNS.items() if rid not in to_remove]
        remaining.sort(
            key=lambda pair: _parse_iso(pair[1].finished_at) or _parse_iso(pair[1].started_at) or datetime.min
        )
        overflow = max(0, len(remaining) - RUNS_MAX_RECORDS)
        to_remove.update(rid for rid, _ in remaining[:overflow])

    for run_id in to_remove:
        RUNS.pop(run_id, None)

    return len(to_remove)


def _build_analyze_query(product: str) -> str:
    subject = (product or "").strip()
    return (
        f"Analyze the product/company/initiative: {subject}\n\n"
        "Research objective:\n"
        "- Produce a PM-oriented strategic analysis grounded in recent evidence.\n"
        "- Prioritize official product pages, pricing pages, launch notes, API/docs, benchmarks, "
        "customer adoption signals, competitor comparisons, and credible commentary.\n\n"
        "Target sections:\n"
        "1. Product Overview\n"
        "2. Business Model\n"
        "3. Competitive Landscape\n"
        "4. SWOT\n"
        "5. User & Market\n"
        "6. Strategic Watchpoints\n"
    )


def _rewrite_analysis_report(report: str, product: str, language: str) -> str:
    language_hint = {
        "Chinese (Simplified)": "Write in Simplified Chinese.",
        "Japanese": "Write in Japanese.",
    }.get(language, "Write in English (US).")
    system_prompt = (
        "You are a product strategy analyst. Rewrite the research report into a concise PM-oriented markdown report "
        "with exactly these sections in order:\n"
        "## Product Overview\n"
        "## Business Model\n"
        "## Competitive Landscape\n"
        "## SWOT\n"
        "## User & Market\n"
        "## Strategic Watchpoints\n"
        "Use evidence-driven language. Keep concrete facts, comparisons, risks, and market signals. "
        "Do not add a sources section.\n"
        f"{language_hint}"
    )
    rewritten = llm_chat(system_prompt, f"Subject: {product}\n\nResearch report:\n{report}")
    if rewritten and "## Product Overview" in rewritten:
        return rewritten
    fallback = (
        "## Product Overview\n"
        f"- Subject: **{product}**\n"
        f"- Source report excerpt: {report[:300].strip() or 'Evidence insufficient.'}\n\n"
        "## Business Model\n- Evidence insufficient.\n\n"
        "## Competitive Landscape\n- Evidence insufficient.\n\n"
        "## SWOT\n- Evidence insufficient.\n\n"
        "## User & Market\n- Evidence insufficient.\n\n"
        "## Strategic Watchpoints\n- Evidence insufficient."
    )
    return fallback


def _run_job(run_id: str, query: str, language: str, run_type: str = "research") -> None:
    record = RUNS[run_id]
    record.status = "running"
    record.started_at = datetime.utcnow().isoformat()
    record.language_used = _normalize_language(language)
    record.run_type = run_type

    try:
        settings = Settings(output_dir="outputs")
        selected_model = settings.llm_model
        configured_search_provider = settings.search_provider

        # Apply app_config overrides
        if DB is not None:
            try:
                config = DB.get_app_config()
                merged = {**APP_CONFIG_DEFAULTS, **config}
                model_label = merged.get("primary_model", "")
                settings.search_provider = str(merged.get("search_provider") or settings.search_provider)
                settings.research_recency_mode = str(
                    merged.get("research_recency_mode") or settings.research_recency_mode
                )
                configured_search_provider = settings.search_provider
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
            try:
                agent = QueryAgent(settings)
            except ProviderUnavailableError as provider_err:
                meta = provider_err.meta
                record.events.append(
                    RunEvent(
                        stage="search_provider",
                        message=(
                            f"configured={meta.provider_requested} "
                            f"effective={meta.provider_effective} "
                            f"llm_assisted={str(meta.llm_assisted_search).lower()}"
                        ),
                    )
                )
                unavailable_reason = meta.fallback_reason or str(provider_err)
                record.events.append(RunEvent(stage="error", message=f"PROVIDER_UNAVAILABLE: {unavailable_reason}"))
                with _diagnostics_lock:
                    _LAST_SEARCH_DIAGNOSTICS.update(
                        {
                            "search_provider_configured": meta.provider_requested,
                            "search_provider_effective": meta.provider_effective,
                            "search_provider_fallback": unavailable_reason,
                            "search_llm_assisted": bool(meta.llm_assisted_search),
                        }
                    )
                raise RuntimeError(f"PROVIDER_UNAVAILABLE: {unavailable_reason}") from provider_err
            meta = getattr(agent, "search_meta", None)

            if meta is not None:
                record.events.append(
                    RunEvent(
                        stage="search_provider",
                        message=(
                            f"configured={meta.provider_requested} "
                            f"effective={meta.provider_effective} "
                            f"llm_assisted={str(meta.llm_assisted_search).lower()}"
                        ),
                    )
                )
                with _diagnostics_lock:
                    _LAST_SEARCH_DIAGNOSTICS.update(
                        {
                            "search_provider_configured": meta.provider_requested,
                            "search_provider_effective": meta.provider_effective,
                            "search_provider_fallback": meta.fallback_reason,
                            "search_llm_assisted": bool(meta.llm_assisted_search),
                        }
                    )
            else:
                with _diagnostics_lock:
                    _LAST_SEARCH_DIAGNOSTICS.update(
                        {
                            "search_provider_configured": configured_search_provider,
                            "search_provider_effective": configured_search_provider,
                            "search_provider_fallback": "",
                            "search_llm_assisted": False,
                        }
                    )

            def progress_cb(evt):
                record.events.append(RunEvent(**evt))

            raw_query = _build_analyze_query(query) if run_type == "analyze" else query
            safe_query = _sanitize_query(raw_query)
            try:
                report = agent.research(
                    safe_query,
                    progress_cb=progress_cb,
                    language=record.language_used,
                )
                if run_type == "analyze":
                    report = _rewrite_analysis_report(report, query, record.language_used)
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
                    language_used=record.language_used,
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
    SCHEDULER.scheduler.add_job(
        _cleanup_inmemory_runs,
        trigger="interval",
        minutes=30,
        id="cleanup_inmemory_runs",
        replace_existing=True,
    )


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
    merged = dict(APP_CONFIG_DEFAULTS)
    if DB is not None:
        try:
            config = DB.get_app_config()
            merged = {**APP_CONFIG_DEFAULTS, **config}
            if not merged.get("critical_analysis_layer", True):
                effective_max_reflections = 1
            with _diagnostics_lock:
                _LAST_SEARCH_DIAGNOSTICS["search_provider_configured"] = str(
                    merged.get("search_provider", _LAST_SEARCH_DIAGNOSTICS.get("search_provider_configured", "Tavily Search API"))
                )
        except Exception:
            pass
    configured_provider = str(merged.get("search_provider", "Tavily Search API"))
    try:
        settings_probe = Settings(output_dir="outputs")
        _tool, meta = create_search_tool_with_meta(
            configured_provider,
            fallback_tavily_key=settings_probe.tavily_api_key,
            bocha_api_key=settings_probe.bocha_api_key,
            zhipu_api_key=settings_probe.zhipu_api_key,
            zhipu_openai_base_url=settings_probe.zhipu_openai_base_url,
            zhipu_web_search_model=settings_probe.zhipu_web_search_model,
            exa_api_key=settings_probe.exa_api_key,
            volcengine_api_key=settings_probe.volcengine_api_key,
            volcengine_openai_base_url=settings_probe.volcengine_openai_base_url,
            volcengine_model_ep=settings_probe.volcengine_model_ep,
            strict=settings_probe.research_strict_provider,
        )
        with _diagnostics_lock:
            _LAST_SEARCH_DIAGNOSTICS.update(
                {
                    "search_provider_configured": configured_provider,
                    "search_provider_effective": meta.provider_effective,
                    "search_provider_fallback": meta.fallback_reason,
                    "search_llm_assisted": bool(meta.llm_assisted_search),
                }
            )
    except ProviderUnavailableError as probe_unavailable:
        probe_meta = probe_unavailable.meta
        with _diagnostics_lock:
            _LAST_SEARCH_DIAGNOSTICS.update(
                {
                    "search_provider_configured": configured_provider,
                    "search_provider_effective": "Unavailable",
                    "search_provider_fallback": probe_meta.fallback_reason or str(probe_unavailable),
                    "search_llm_assisted": False,
                }
            )
    except Exception as probe_err:
        with _diagnostics_lock:
            _LAST_SEARCH_DIAGNOSTICS.update(
                {
                    "search_provider_configured": configured_provider,
                    "search_provider_effective": "Unavailable",
                    "search_provider_fallback": f"Probe failed: {probe_err}",
                    "search_llm_assisted": False,
                }
            )
    return {
        "started_at": _STARTUP_TIME,
        "scheduler_running": SCHEDULER is not None and SCHEDULER.scheduler.running,
        "active_research": _active_research,
        "max_concurrent_research": MAX_CONCURRENT_RESEARCH,
        "active_chat": _active_chat,
        "max_concurrent_chat": MAX_CONCURRENT_CHAT,
        "max_reflections": effective_max_reflections,
        "rate_limit_backend": _RATE_LIMITER.backend_name,
        "rate_limit_per_min": ADMIN_RATE_LIMIT,
        "public_rate_limit_per_min": PUBLIC_RATE_LIMIT,
        "public_read_rate_limit_per_min": PUBLIC_READ_RATE_LIMIT,
        "public_export_rate_limit_per_min": PUBLIC_EXPORT_RATE_LIMIT,
        "run_route_limit_per_min": RUN_ROUTE_LIMIT,
        "chat_route_limit_per_min": CHAT_ROUTE_LIMIT,
        **_snapshot_search_diagnostics(),
        "jobs": jobs,
    }


@app.get("/api/system/provider-check")
def provider_check():
    """Diagnose all configured search providers with a real test search."""
    settings_probe = Settings(output_dir="outputs")
    providers_config = [
        (
            "Tavily Search API",
            {"fallback_tavily_key": settings_probe.tavily_api_key},
        ),
        (
            "Bocha Search",
            {"bocha_api_key": settings_probe.bocha_api_key},
        ),
        (
            "Zhipu Web Search",
            {
                "zhipu_api_key": settings_probe.zhipu_api_key,
                "zhipu_openai_base_url": settings_probe.zhipu_openai_base_url,
                "zhipu_web_search_model": settings_probe.zhipu_web_search_model,
            },
        ),
        (
            "Exa Search",
            {"exa_api_key": settings_probe.exa_api_key},
        ),
        (
            "Volcano Engine",
            {
                "volcengine_api_key": settings_probe.volcengine_api_key,
                "volcengine_openai_base_url": settings_probe.volcengine_openai_base_url,
                "volcengine_model_ep": settings_probe.volcengine_model_ep,
            },
        ),
    ]
    results = []
    for provider_name, kwargs in providers_config:
        start = time.monotonic()
        try:
            tool, _meta = create_search_tool_with_meta(
                provider_name, strict=True, **kwargs,
            )
            response = tool.search("test", max_results=1)
            latency_ms = int((time.monotonic() - start) * 1000)
            status, error_detail, search_mode = _provider_check_status(tool, response)
            results.append({
                "provider": provider_name,
                "status": status,
                "latency_ms": latency_ms,
                "result_count": len(response.results),
                "error_detail": error_detail,
                "search_mode": search_mode,
            })
        except ProviderUnavailableError as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            results.append({
                "provider": provider_name,
                "status": "config_error",
                "latency_ms": latency_ms,
                "result_count": 0,
                "error_detail": str(e)[:200],
                "search_mode": "unavailable",
            })
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            error_class = classify_provider_error(e)
            results.append({
                "provider": provider_name,
                "status": error_class,
                "latency_ms": latency_ms,
                "result_count": 0,
                "error_detail": str(e)[:200],
                "search_mode": "unknown",
            })
    return {"providers": results, "checked_at": datetime.utcnow().isoformat()}


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
    raw_lang = payload.language
    if not raw_lang:
        config = DB.get_app_config()
        raw_lang = config.get("report_language")
    language_used = _normalize_language(raw_lang)
    with _research_lock:
        if _active_research >= MAX_CONCURRENT_RESEARCH:
            raise HTTPException(status_code=429, detail=f"Too many concurrent research tasks (max {MAX_CONCURRENT_RESEARCH})")
        _active_research += 1
    run_id = f"{slugify(payload.query)}_{datetime.utcnow().strftime('%H%M%S')}"
    if run_id in RUNS:
        with _research_lock:
            _active_research -= 1
        raise HTTPException(status_code=400, detail="Run already exists")
    record = RunRecord(run_id=run_id, query=payload.query, run_type="research", language_used=language_used)
    RUNS[run_id] = record
    thread = threading.Thread(target=_run_job, args=(run_id, payload.query, language_used, "research"), daemon=True)
    thread.start()
    return RunResponse(run_id=run_id, status="running", language_used=language_used)


@app.post("/api/analyze", response_model=RunResponse)
def start_analysis(payload: AnalyzeRequest):
    global _active_research
    raw_lang = payload.language
    if not raw_lang and DB is not None:
        config = DB.get_app_config()
        raw_lang = config.get("report_language")
    language_used = _normalize_language(raw_lang)
    with _research_lock:
        if _active_research >= MAX_CONCURRENT_RESEARCH:
            raise HTTPException(status_code=429, detail=f"Too many concurrent research tasks (max {MAX_CONCURRENT_RESEARCH})")
        _active_research += 1
    run_id = f"analyze_{slugify(payload.product)}_{datetime.utcnow().strftime('%H%M%S')}"
    if run_id in RUNS:
        with _research_lock:
            _active_research -= 1
        raise HTTPException(status_code=400, detail="Run already exists")
    record = RunRecord(run_id=run_id, query=payload.product, run_type="analyze", language_used=language_used)
    RUNS[run_id] = record
    thread = threading.Thread(target=_run_job, args=(run_id, payload.product, language_used, "analyze"), daemon=True)
    thread.start()
    return RunResponse(run_id=run_id, status="running", language_used=language_used)


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
            language_used=record.language_used,
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
                language_used=row.get("language_used"),
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
            "language_used": r.language_used,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "created_at": r.started_at or r.finished_at,
            "report_path": r.report_path,
            "source_count": _estimate_source_count(r.report_content),
        })
    if DB is not None:
        for row in DB.list_research_runs(limit=200):
            if row["run_id"] not in memory_ids:
                row["source_count"] = _estimate_source_count(row.get("report_content"))
                row.pop("report_content", None)
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


def _fallback_daily_digest_content(date_str: str, briefs: List[Dict[str, Any]], missing_topics: List[str]) -> str:
    lines = [
        f"# Daily Digest | {date_str}",
        "",
        "## Executive Summary",
        f"This digest summarizes {len(briefs)} active topics for {date_str}.",
        "",
        "## Topic Highlights",
    ]
    for brief in briefs:
        topic_name = brief.get("topic_name", f"Topic {brief.get('topic_id', '')}")
        content = (brief.get("content") or "").strip()
        snippet = content.split("\n\n", 2)[1] if "\n\n" in content else content
        snippet = snippet.strip() or "No summary available."
        lines.extend([
            f"### {topic_name}",
            snippet[:1200],
            "",
        ])
    if missing_topics:
        lines.extend([
            "## Missing Topics",
            *[f"- {name}" for name in missing_topics],
            "",
        ])
    return "\n".join(lines).strip()


def _build_daily_digest_content(date_str: str, briefs: List[Dict[str, Any]], missing_topics: List[str], language_used: str) -> str:
    blocks: List[str] = []
    for brief in briefs:
        topic_name = brief.get("topic_name", f"Topic {brief.get('topic_id', '')}")
        content = (brief.get("content") or "").strip()
        blocks.append(f"[{topic_name}]\n{content[:5000]}")

    if not blocks:
        return _fallback_daily_digest_content(date_str, briefs, missing_topics)

    missing_text = ", ".join(missing_topics) if missing_topics else "None"
    prompt = (
        "You are writing a complete daily intelligence digest for Discord readers. "
        "Return markdown with these sections only: "
        "'# Daily Digest | <date>', '## Executive Summary', '## Topic Highlights', and optionally '## Missing Topics'. "
        "Write a full digest article, not a one-line summary. "
        "Synthesize the most important developments across topics, preserve topic distinctions, and keep the output readable in Discord. "
        f"Write in {language_used}."
    )
    user = (
        f"Date: {date_str}\n"
        f"Missing active topics: {missing_text}\n\n"
        "Topic briefs:\n\n"
        + "\n\n---\n\n".join(blocks)
    )
    content = (llm_chat(prompt, user) or "").strip()
    if not content:
        return _fallback_daily_digest_content(date_str, briefs, missing_topics)
    return content


def _generate_and_store_daily_digest(date_str: str, language_used: str) -> Dict[str, Any]:
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    briefs = DB.list_briefs_for_date(date_str, active_only=True)
    if not briefs:
        raise HTTPException(status_code=404, detail="No briefs found for requested date")
    active_topics = DB.list_active_topic_names()
    present_topics = {str(brief.get("topic_name") or "") for brief in briefs}
    missing_topics = [name for name in active_topics if name not in present_topics]
    content = _build_daily_digest_content(date_str, briefs, missing_topics, language_used)
    DB.save_daily_digest(date_str, content, len(briefs), missing_topics)
    digest = DB.get_daily_digest(date_str)
    if not digest:
        raise HTTPException(status_code=500, detail="Failed to save daily digest")
    return digest


def _run_refresh_operation(payload: RefreshRequest) -> Dict[str, Any]:
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")

    language_used = _normalize_language(payload.language or DB.get_app_config().get("report_language"))

    if payload.scope == "digest":
        date_str = DB.get_latest_active_brief_date()
        if not date_str:
            raise HTTPException(status_code=404, detail="No briefs available for digest generation")
        digest = _generate_and_store_daily_digest(date_str, language_used)
        return {
            "scope": "digest",
            "language_used": language_used,
            "digest": digest,
            "pushed": bool(payload.push),
        }

    if payload.scope == "topic":
        if payload.topic_id is None:
            raise HTTPException(status_code=400, detail="topic_id is required when scope=topic")
        collect_result = collect_topic(payload.topic_id)
        brief_result = generate_brief(payload.topic_id, BriefGenerateRequest(language=language_used))
        brief = latest_brief(payload.topic_id)
        return {
            "scope": "topic",
            "language_used": language_used,
            "collect": collect_result,
            "brief_result": brief_result,
            "brief": brief,
            "pushed": bool(payload.push),
        }

    collect_result = collect_all()
    briefs_result = generate_brief_all(BriefGenerateRequest(language=language_used))
    digest_date = str(briefs_result.get("date") or DB.get_latest_active_brief_date() or "")
    if not digest_date:
        raise HTTPException(status_code=404, detail="No briefs available after refresh")
    digest = _generate_and_store_daily_digest(digest_date, language_used)
    return {
        "scope": "all",
        "language_used": language_used,
        "collect": collect_result,
        "briefs": briefs_result,
        "digest": digest,
        "pushed": bool(payload.push),
    }


@app.post("/api/topics/{topic_id}/brief")
def generate_brief(topic_id: int, payload: Optional[BriefGenerateRequest] = None):
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
        requested_language = _normalize_language(payload.language if payload else None)
        if payload and payload.language:
            merged_config["report_language"] = requested_language
        else:
            requested_language = _normalize_language(merged_config.get("report_language"))
        brief = build_brief_for_topic(topic, items, source_weights=source_weights, app_config=merged_config)
        DB.save_brief(topic_id, date_str, brief, len(items))
        DB.log_brief_run(topic.id, "brief", "ok", items_collected=len(items), started_at=started)
        return {"topic_id": topic.id, "date": date_str, "items": len(items), "language_used": requested_language}
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
def generate_brief_all(payload: Optional[BriefGenerateRequest] = None):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    results = []
    date_str = datetime.now().strftime("%Y-%m-%d")
    config = DB.get_app_config()
    merged_config = {**APP_CONFIG_DEFAULTS, **config}
    requested_language = _normalize_language(payload.language if payload else None)
    if payload and payload.language:
        merged_config["report_language"] = requested_language
    else:
        requested_language = _normalize_language(merged_config.get("report_language"))
    for topic in DB.list_topics():
        if not topic.is_active:
            continue
        items = _load_brief_items(topic.id, date_str)
        source_weights = DB.get_source_reputations(topic.id)
        brief = build_brief_for_topic(topic, items, source_weights=source_weights, app_config=merged_config)
        DB.save_brief(topic.id, date_str, brief, len(items))
        results.append({"topic_id": topic.id, "topic_name": topic.name, "items": len(items)})
    return {"date": date_str, "total_topics": len(results), "results": results, "language_used": requested_language}


@app.get("/api/digest/latest")
def get_latest_digest():
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    latest_date = DB.get_latest_active_brief_date()
    if not latest_date:
        raise HTTPException(status_code=404, detail="No briefs available for digest generation")
    digest = DB.get_daily_digest(latest_date)
    if digest is None:
        config = DB.get_app_config()
        language_used = _normalize_language(config.get("report_language"))
        digest = _generate_and_store_daily_digest(latest_date, language_used)
    return digest


@app.get("/api/digest/{date_str}")
def get_digest_by_date(date_str: str):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str or ""):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    digest = DB.get_daily_digest(date_str)
    if digest is None:
        config = DB.get_app_config()
        language_used = _normalize_language(config.get("report_language"))
        digest = _generate_and_store_daily_digest(date_str, language_used)
    return digest


@app.post("/api/digest/generate")
def generate_daily_digest(payload: Optional[DigestGenerateRequest] = None):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    requested_date = payload.date if payload else None
    date_str = requested_date or DB.get_latest_active_brief_date()
    if not date_str:
        raise HTTPException(status_code=404, detail="No briefs available for digest generation")
    config = DB.get_app_config()
    language_used = _normalize_language(payload.language if payload and payload.language else config.get("report_language"))
    digest = _generate_and_store_daily_digest(date_str, language_used)
    return digest


@app.post("/api/ops/refresh")
def refresh_ops(payload: RefreshRequest):
    return _run_refresh_operation(payload)


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
def brief_history(topic_id: int, limit: int = 7, since_hours: int = 48):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    if since_hours < 0:
        raise HTTPException(status_code=400, detail="since_hours must be >= 0")
    normalized_limit = max(1, min(limit, 30))
    cutoff_hours: Optional[int] = since_hours if since_hours > 0 else None
    return DB.list_briefs(topic_id, limit=normalized_limit, since_hours=cutoff_hours)


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


@app.post("/api/bookmarks")
def create_bookmark(payload: BookmarkCreateRequest):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    brief = DB.get_brief_by_id(payload.brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    DB.save_bookmark(payload.user_id.strip(), payload.brief_id, (payload.note or "").strip() or None)
    return {"status": "saved", "user_id": payload.user_id.strip(), "brief_id": payload.brief_id}


@app.get("/api/bookmarks/{user_id}")
def list_bookmarks(user_id: str, limit: int = 50):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    normalized = (user_id or "").strip()
    if len(normalized) < 3:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    items = DB.list_bookmarks(normalized, limit=max(1, min(limit, 100)))
    return {"user_id": normalized, "count": len(items), "items": items}


@app.delete("/api/bookmarks/{user_id}/{brief_id}")
def delete_bookmark(user_id: str, brief_id: int):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")
    normalized = (user_id or "").strip()
    if len(normalized) < 3:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    deleted = DB.delete_bookmark(normalized, brief_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return {"status": "deleted", "user_id": normalized, "brief_id": brief_id}


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


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    topic_id: Optional[int] = None
    days: int = Field(default=7, ge=1, le=30)
    language: Optional[str] = Field(default=None, max_length=64)


class TLDRRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    language: Optional[str] = Field(default=None, max_length=64)
    created_by: Optional[str] = Field(default="system", max_length=128)


def _fallback_tldr_summary(content: str) -> str:
    compact = re.sub(r"\s+", " ", (content or "").strip())
    if len(compact) <= 280:
        return compact or "No summary available."
    return compact[:279].rstrip() + "…"


def _summarize_ingested_document(title: str, content: str, language_used: str) -> str:
    language_hint = {
        "Chinese (Simplified)": "Write in Simplified Chinese.",
        "Japanese": "Write in Japanese.",
    }.get(language_used, "Write in English (US).")
    prompt = (
        "You summarize a single article for mobile reading. "
        "Return one dense paragraph in 2-4 sentences. "
        "Focus on the core claim, why it matters, and any meaningful constraint. "
        "Do not use markdown bullets. Do not mention that you are an AI.\n"
        f"{language_hint}"
    )
    user = f"Title: {title}\n\nContent:\n{content[:6000]}"
    summary = llm_chat(prompt, user)
    return (summary or "").strip() or _fallback_tldr_summary(content)


def _chat_config_value(key: str, default: Any) -> Any:
    if DB is None:
        return default
    try:
        config = DB.get_app_config()
        return config.get(key, default)
    except Exception:
        return default


def _build_brief_chat_context(req: "ChatRequest") -> tuple[str, str, List[str]]:
    all_briefs = DB.list_recent_briefs(limit=20, topic_id=req.topic_id) if DB is not None else []
    cutoff = (datetime.utcnow() - timedelta(days=req.days)).isoformat()
    briefs = [b for b in all_briefs if (b.get("created_at") or "") >= cutoff]
    if not briefs:
        return "", "", []

    blocks: List[str] = []
    sources: List[str] = []
    total_chars = 0
    for b in briefs[:5]:
        content = (b.get("content") or "")[:1500]
        if total_chars + len(content) > 6000:
            break
        date_label = b.get("date") or b.get("created_at", "")[:10]
        topic_label = b.get("topic_name", f"Topic {b.get('topic_id', '')}")
        blocks.append(f"[{date_label} | {topic_label}]\n{content}")
        sources.append(f"{date_label} | {topic_label}")
        total_chars += len(content)
    if not blocks:
        return "", "", []
    return "brief_context", "\n\n---\n\n".join(blocks), sources


def _build_article_chat_context(req: "ChatRequest") -> tuple[str, str, List[str]]:
    if DB is None:
        return "", "", []
    articles = DB.search_articles(req.message, topic_id=req.topic_id, limit=5, days=req.days)
    if not articles:
        return "", "", []
    blocks = []
    sources = []
    for article in articles:
        title = article.get("title", "Untitled article")
        body = (article.get("content") or "")[:1200]
        url = article.get("url", "")
        source = article.get("source", "")
        blocks.append(f"[Article | {title}]\nSource: {source}\nURL: {url}\n{body}")
        sources.append(f"Article | {title} | {url}")
    return "article_context", "\n\n---\n\n".join(blocks), sources


def _build_ingestion_chat_context(req: "ChatRequest") -> tuple[str, str, List[str]]:
    if DB is None:
        return "", "", []
    ingestions = DB.search_user_ingestions(req.message, limit=5, days=max(req.days, 30))
    if not ingestions:
        return "", "", []
    blocks = []
    sources = []
    for row in ingestions:
        title = row.get("title", "Untitled ingestion")
        body = ((row.get("summary") or "") + "\n" + (row.get("content") or ""))[:1200]
        url = row.get("final_url") or row.get("url") or ""
        blocks.append(f"[Ingestion | {title}]\nURL: {url}\n{body}")
        sources.append(f"Ingestion | {title} | {url}")
    return "ingestion_context", "\n\n---\n\n".join(blocks), sources


def _build_web_fallback_chat_context(req: "ChatRequest") -> tuple[str, str, List[str]]:
    if DB is None:
        return "", "", []
    configured_provider = str(_chat_config_value("search_provider", APP_CONFIG_DEFAULTS.get("search_provider", "Tavily Search API")))
    settings = Settings(output_dir="outputs")
    tool, _meta = create_search_tool_with_meta(
        configured_provider,
        fallback_tavily_key=settings.tavily_api_key,
        bocha_api_key=settings.bocha_api_key,
        zhipu_api_key=settings.zhipu_api_key,
        zhipu_openai_base_url=settings.zhipu_openai_base_url,
        zhipu_web_search_model=settings.zhipu_web_search_model,
        exa_api_key=settings.exa_api_key,
        volcengine_api_key=settings.volcengine_api_key,
        volcengine_openai_base_url=settings.volcengine_openai_base_url,
        volcengine_model_ep=settings.volcengine_model_ep,
        strict=False,
    )
    response = tool.search(req.message, max_results=4)
    results = list(getattr(response, "results", []) or [])
    if not results:
        return "", "", []
    blocks = []
    sources = []
    for result in results[:4]:
        blocks.append(
            f"[Web | {result.title}]\nURL: {result.url}\n{(result.content or '')[:1000]}"
        )
        sources.append(f"Web | {result.title} | {result.url}")
    return "web_fallback", "\n\n---\n\n".join(blocks), sources


@app.post("/api/tldr")
def create_tldr(req: TLDRRequest):
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")

    try:
        safe_url = validate_public_http_url(req.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    language_used = _normalize_language(req.language)
    cached = DB.get_user_ingestion(safe_url)
    if cached and cached.get("summary"):
        return {
            "title": cached.get("title", ""),
            "summary": cached.get("summary", ""),
            "url": cached.get("final_url") or cached.get("url") or safe_url,
            "source_domain": cached.get("source_domain", ""),
            "ingested": True,
            "cached": True,
            "language_used": cached.get("language_used") or language_used,
        }

    try:
        doc = fetch_tldr_document(safe_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.warning("TLDR fetch failed for %s: %s", safe_url, exc)
        raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {exc}")

    summary = _summarize_ingested_document(doc.title, doc.content, language_used)
    DB.save_user_ingestion(
        url=safe_url,
        final_url=doc.final_url,
        title=doc.title,
        content=doc.content,
        summary=summary,
        source_domain=doc.source_domain,
        language_used=language_used,
        created_by=(req.created_by or "system").strip() or "system",
    )
    return {
        "title": doc.title,
        "summary": summary,
        "url": doc.final_url,
        "source_domain": doc.source_domain,
        "ingested": True,
        "cached": False,
        "language_used": language_used,
    }


@app.post("/api/chat")
def chat_with_briefs(req: ChatRequest):
    """Answer a user question based on recent brief content (no RAG/vector store needed)."""
    if DB is None:
        raise HTTPException(status_code=500, detail="DB not initialized")

    global _active_chat
    with _chat_lock:
        if _active_chat >= MAX_CONCURRENT_CHAT:
            raise HTTPException(status_code=429, detail=f"Too many concurrent chat tasks (max {MAX_CONCURRENT_CHAT})")
        _active_chat += 1

    cutoff = (datetime.utcnow() - timedelta(days=req.days)).isoformat()
    language_used = _normalize_language(req.language)

    try:
        context_layer = ""
        context = ""
        sources: List[str] = []
        for builder in (
            _build_brief_chat_context,
            _build_article_chat_context,
            _build_ingestion_chat_context,
            _build_web_fallback_chat_context,
        ):
            context_layer, context, sources = builder(req)
            if context:
                break

        if not context:
            return {
                "reply": "No recent briefs, articles, or ingested pages matched this query.",
                "sources": [],
                "context_layer": "none",
                "language_used": language_used,
            }

        language_hint = {
            "Chinese (Simplified)": "Write in Simplified Chinese.",
            "Japanese": "Write in Japanese.",
        }.get(language_used, "Write in English (US).")
        system_prompt = (
            "You are a concise news analyst assistant. Answer the user's question based ONLY on "
            "the provided brief context. Respond in 2-4 sentences in a conversational (not report) tone. "
            "If the context does not cover the question, say so clearly. "
            "Cite the brief date and topic you draw from. "
            "Keep source titles verbatim in their original language.\n"
            f"{language_hint}"
        )
        user_prompt = f"Context:\n{context}\n\nQuestion: {req.message}"

        reply = llm_chat(system_prompt, user_prompt)
        if reply is None:
            reply = "LLM is unavailable. Please try again later."

        return {
            "reply": reply,
            "sources": sources,
            "context_layer": context_layer,
            "language_used": language_used,
        }
    finally:
        with _chat_lock:
            _active_chat = max(_active_chat - 1, 0)


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
