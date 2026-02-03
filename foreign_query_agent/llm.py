"""LLM client wrappers."""

from dataclasses import dataclass
from typing import Dict, Any
from datetime import datetime

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency for mock mode
    OpenAI = None


@dataclass
class LLMConfig:
    api_key: str
    model: str
    base_url: str = ""


class LLMClient:
    """OpenAI-compatible client."""

    DEFAULT_TIMEOUT = 120  # 2 minutes timeout
    MAX_RETRIES = 2

    def __init__(self, config: LLMConfig):
        if not config.api_key:
            raise ValueError("LLM API key is required (FQ_LLM_API_KEY).")
        if not config.model:
            raise ValueError("LLM model is required (FQ_LLM_MODEL).")
        if OpenAI is None:
            raise RuntimeError("openai package not available.")
        kwargs: Dict[str, Any] = {
            "api_key": config.api_key,
            "timeout": self.DEFAULT_TIMEOUT,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self.client = OpenAI(**kwargs)
        self.model = config.model

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        user_prompt = f"Current time: {current_time}\n{user_prompt}" if user_prompt else f"Current time: {current_time}"

        last_error = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    timeout=self.DEFAULT_TIMEOUT,
                )
                if response.choices and response.choices[0].message:
                    return (response.choices[0].message.content or "").strip()
                return ""
            except Exception as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    import time
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
                    continue
                break

        # All retries failed
        raise RuntimeError(f"LLM call failed after {self.MAX_RETRIES + 1} attempts: {last_error}")


class MockLLM:
    """Deterministic mock LLM for offline tests."""

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        text = (system_prompt or "").lower()
        if "report structure" in text:
            return (
                "["
                "{\"title\":\"Overview\",\"content\":\"High-level context and key points.\"},"
                "{\"title\":\"Key Developments\",\"content\":\"Recent events and updates.\"}"
                "]"
            )
        if "search tool" in text:
            return (
                "{\"search_query\":\"example topic latest news\","
                "\"search_tool\":\"basic_search\","
                "\"reasoning\":\"Need broad overview\"}"
            )
        if "reflection" in text and "search" in text:
            return (
                "{\"search_query\":\"example topic background\","
                "\"search_tool\":\"basic_search\","
                "\"reasoning\":\"Fill missing context\"}"
            )
        if "moderator" in text or "critique" in text:
            return (
                "{"
                "\"questions\":[\"What evidence is missing?\"],"
                "\"suggested_search_queries\":[\"example topic evidence statistics\"],"
                "\"critique\":\"Add stronger sources and counterpoints.\""
                "}"
            )
        if "summary" in text and "updated" not in text:
            return "{\"paragraph_latest_state\":\"Mock summary based on search results.\"}"
        if "updated_paragraph_latest_state" in text:
            return "{\"updated_paragraph_latest_state\":\"Mock improved summary with added evidence.\"}"
        if "format" in text:
            return "# Report\n\n## Overview\nMock final report."
        return "{}"

