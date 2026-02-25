"""Search tool factory."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Dict, Tuple

from .base import SearchTool
from .bocha_tool import BochaSearchTool
from .exa_tool import ExaSearchTool
from .mock_tool import MockSearchTool
from .tavily_tool import TavilySearchTool
from .volcengine_tool import VolcEngineSearchTool
from .zhipu_tool import ZhipuSearchTool

logger = logging.getLogger(__name__)

TAVILY_PROVIDER = "Tavily Search API"
BOCHA_PROVIDER = "Bocha Search"
ZHIPU_PROVIDER = "Zhipu Web Search"
VOLCANO_PROVIDER = "Volcano Engine"
EXA_PROVIDER = "Exa Search"

_PROVIDER_ALIASES = {
    "Serper (Google)": TAVILY_PROVIDER,
    "Bing Search": TAVILY_PROVIDER,
}

_PROVIDER_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    TAVILY_PROVIDER: {"openai_compatible": False, "llm_assisted": False, "api_style": "search_api"},
    BOCHA_PROVIDER: {"openai_compatible": False, "llm_assisted": False, "api_style": "search_api"},
    ZHIPU_PROVIDER: {"openai_compatible": True, "llm_assisted": True, "api_style": "openai_compatible"},
    VOLCANO_PROVIDER: {"openai_compatible": True, "llm_assisted": True, "api_style": "openai_compatible"},
    EXA_PROVIDER: {"openai_compatible": False, "llm_assisted": False, "api_style": "search_api"},
}


@dataclass
class SearchToolBuildMeta:
    provider_requested: str
    provider_effective: str
    fallback_reason: str = ""
    llm_assisted_search: bool = False
    openai_compatible: bool = False
    api_style: str = "search_api"


class ProviderUnavailableError(RuntimeError):
    """Raised when strict provider mode is enabled and provider is unavailable."""

    def __init__(self, message: str, meta: SearchToolBuildMeta):
        super().__init__(message)
        self.meta = meta


def _normalize_provider(provider_label: str) -> str:
    label = (provider_label or "").strip()
    if not label:
        return TAVILY_PROVIDER
    return _PROVIDER_ALIASES.get(label, label)


def _build_tavily(api_key: str) -> SearchTool:
    return TavilySearchTool(api_key=api_key)


def _llm_assisted(provider: str) -> bool:
    return bool(_PROVIDER_CAPABILITIES.get(provider, {}).get("llm_assisted", False))


def _openai_compatible(provider: str) -> bool:
    return bool(_PROVIDER_CAPABILITIES.get(provider, {}).get("openai_compatible", False))


def _api_style(provider: str) -> str:
    return str(_PROVIDER_CAPABILITIES.get(provider, {}).get("api_style", "search_api"))


def _meta(provider_requested: str, provider_effective: str, fallback_reason: str = "") -> SearchToolBuildMeta:
    return SearchToolBuildMeta(
        provider_requested=provider_requested,
        provider_effective=provider_effective,
        fallback_reason=fallback_reason,
        llm_assisted_search=_llm_assisted(provider_effective),
        openai_compatible=_openai_compatible(provider_effective),
        api_style=_api_style(provider_effective),
    )


def create_search_tool_with_meta(
    provider_label: str,
    fallback_tavily_key: str = "",
    *,
    bocha_api_key: str = "",
    zhipu_api_key: str = "",
    exa_api_key: str = "",
    volcengine_api_key: str = "",
    volcengine_model_ep: str = "",
    zhipu_openai_base_url: str = "",
    zhipu_web_search_model: str = "",
    volcengine_openai_base_url: str = "",
    strict: bool = False,
) -> Tuple[SearchTool, SearchToolBuildMeta]:
    provider_requested = (provider_label or "").strip() or TAVILY_PROVIDER
    provider = _normalize_provider(provider_label)
    fallback_reason = ""
    try:
        if provider == TAVILY_PROVIDER:
            return _build_tavily(fallback_tavily_key), _meta(provider_requested, TAVILY_PROVIDER)
        if provider == BOCHA_PROVIDER:
            return BochaSearchTool(api_key=bocha_api_key), _meta(provider_requested, BOCHA_PROVIDER)
        if provider == ZHIPU_PROVIDER:
            return ZhipuSearchTool(
                api_key=zhipu_api_key,
                base_url=zhipu_openai_base_url,
                model=zhipu_web_search_model,
            ), _meta(provider_requested, ZHIPU_PROVIDER)
        if provider == VOLCANO_PROVIDER:
            return VolcEngineSearchTool(
                api_key=volcengine_api_key,
                base_url=volcengine_openai_base_url,
                model_endpoint=volcengine_model_ep,
            ), _meta(provider_requested, VOLCANO_PROVIDER)
        if provider == EXA_PROVIDER:
            return ExaSearchTool(api_key=exa_api_key), _meta(provider_requested, EXA_PROVIDER)
        fallback_reason = f"Unknown provider '{provider_requested}'."
        logger.warning("Unknown search provider '%s'.", provider_label)
    except Exception as exc:
        logger.warning("Search provider '%s' unavailable (%s).", provider, exc)
        fallback_reason = f"{provider} unavailable: {exc}"

    if strict:
        unavailable_meta = SearchToolBuildMeta(
            provider_requested=provider_requested,
            provider_effective="Unavailable",
            fallback_reason=fallback_reason,
            llm_assisted_search=False,
            openai_compatible=_openai_compatible(provider),
            api_style=_api_style(provider),
        )
        raise ProviderUnavailableError(fallback_reason or "Provider unavailable.", unavailable_meta)

    try:
        return _build_tavily(fallback_tavily_key), _meta(provider_requested, TAVILY_PROVIDER, fallback_reason)
    except Exception as exc:
        logger.warning("Tavily fallback unavailable (%s); fallback to MockSearchTool.", exc)
        return MockSearchTool(), SearchToolBuildMeta(
            provider_requested=provider_requested,
            provider_effective="MockSearchTool",
            fallback_reason=(fallback_reason + " " if fallback_reason else "") + f"Tavily fallback unavailable: {exc}",
            llm_assisted_search=False,
            openai_compatible=False,
            api_style="mock_search",
        )


def create_search_tool(
    provider_label: str,
    fallback_tavily_key: str = "",
    *,
    bocha_api_key: str = "",
    zhipu_api_key: str = "",
    exa_api_key: str = "",
    volcengine_api_key: str = "",
    volcengine_model_ep: str = "",
    zhipu_openai_base_url: str = "",
    zhipu_web_search_model: str = "",
    volcengine_openai_base_url: str = "",
    strict: bool = False,
) -> SearchTool:
    """Create a search tool from app_config label with Tavily/Mock fallback."""
    tool, _meta = create_search_tool_with_meta(
        provider_label,
        fallback_tavily_key=fallback_tavily_key,
        bocha_api_key=bocha_api_key,
        zhipu_api_key=zhipu_api_key,
        exa_api_key=exa_api_key,
        volcengine_api_key=volcengine_api_key,
        volcengine_model_ep=volcengine_model_ep,
        zhipu_openai_base_url=zhipu_openai_base_url,
        zhipu_web_search_model=zhipu_web_search_model,
        volcengine_openai_base_url=volcengine_openai_base_url,
        strict=strict,
    )
    return tool
