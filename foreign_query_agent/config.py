"""Runtime settings for the foreign query agent."""

from dataclasses import dataclass
from pathlib import Path
import os


def _load_env_file(env_path: Path) -> None:
    """Load key=value pairs from .env into os.environ if not already set."""
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        # Fail silently; env file is optional
        return


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_load_env_file(_PROJECT_ROOT / ".env")


@dataclass
class Settings:
    llm_api_key: str = os.getenv("FQ_LLM_API_KEY", "")
    llm_base_url: str = os.getenv("FQ_LLM_BASE_URL", "")
    llm_model: str = os.getenv("FQ_LLM_MODEL", "gpt-4o-mini")

    search_provider: str = os.getenv("ARCBRIEF_SEARCH_PROVIDER", "Tavily Search API")
    research_strict_provider: bool = os.getenv("ARCBRIEF_RESEARCH_STRICT_PROVIDER", "1") == "1"
    research_recency_mode: str = os.getenv("ARCBRIEF_RESEARCH_RECENCY_MODE", "recent_12m_with_90d_anchor")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    bocha_api_key: str = os.getenv("BOCHA_API_KEY", "")
    zhipu_api_key: str = os.getenv("ZHIPU_API_KEY", "")
    zhipu_openai_base_url: str = os.getenv("ZHIPU_OPENAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
    zhipu_web_search_model: str = os.getenv("ZHIPU_WEB_SEARCH_MODEL", "glm-4-plus")
    exa_api_key: str = os.getenv("EXA_API_KEY", "")
    volcengine_api_key: str = os.getenv("VOLCENGINE_API_KEY", "")
    volcengine_openai_base_url: str = os.getenv("VOLCENGINE_OPENAI_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    volcengine_model_ep: str = os.getenv("VOLCENGINE_MODEL_EP", "")

    max_reflections: int = int(os.getenv("FQ_MAX_REFLECTIONS", "3"))
    max_paragraphs: int = int(os.getenv("FQ_MAX_PARAGRAPHS", "4"))
    max_results: int = int(os.getenv("FQ_MAX_RESULTS", "8"))

    output_dir: str = os.getenv("FQ_OUTPUT_DIR", "outputs")

    mock_mode: bool = os.getenv("FQ_MOCK", "0") == "1"

