"""LLM client wrappers."""

from dataclasses import dataclass
from datetime import datetime
import os
from typing import Any, Dict

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency for mock mode
    OpenAI = None


@dataclass
class LLMConfig:
    api_key: str
    model: str
    base_url: str = ""
    prompt_cost_per_1k: float = float(os.getenv("FQ_LLM_PROMPT_COST_PER_1K", "0"))
    completion_cost_per_1k: float = float(os.getenv("FQ_LLM_COMPLETION_COST_PER_1K", "0"))


@dataclass
class LLMUsageSummary:
    request_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    model_requested: str = ""
    model_effective: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_count": self.request_count,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "model_requested": self.model_requested,
            "model_effective": self.model_effective,
        }


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
        self.prompt_cost_per_1k = config.prompt_cost_per_1k
        self.completion_cost_per_1k = config.completion_cost_per_1k
        self.usage = LLMUsageSummary(model_requested=config.model, model_effective=config.model)

    def _record_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0)
        self.usage.request_count += 1
        self.usage.prompt_tokens += prompt_tokens
        self.usage.completion_tokens += completion_tokens
        self.usage.total_tokens += total_tokens
        self.usage.estimated_cost_usd += (
            (prompt_tokens / 1000.0) * self.prompt_cost_per_1k
            + (completion_tokens / 1000.0) * self.completion_cost_per_1k
        )

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
                self._record_usage(response)
                if response.choices and response.choices[0].message:
                    return (response.choices[0].message.content or "").strip()
                return ""
            except Exception as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    import time

                    time.sleep(2**attempt)
                    continue
                break

        raise RuntimeError(f"LLM call failed after {self.MAX_RETRIES + 1} attempts: {last_error}")

    def usage_summary(self) -> Dict[str, Any]:
        return self.usage.to_dict()


class MockLLM:
    """Deterministic mock LLM for offline tests."""

    def __init__(self):
        self.usage = LLMUsageSummary(model_requested="mock", model_effective="mock")

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        self.usage.request_count += 1
        text = (system_prompt or "").lower()
        if "premise validation analyst" in text:
            return "{}"
        if "template mode" in text:
            if "template mode: claim_audit" in text:
                return (
                    "{"
                    "\"report_type\":\"claim_audit\","
                    "\"sections\":["
                    "{\"title\":\"Official Status Check\",\"content\":\"Verify whether the claim is real in official channels.\",\"evidence_type\":\"official\",\"target_words\":360},"
                    "{\"title\":\"Where The Claim Came From\",\"content\":\"Trace rumor origin and secondary amplification.\",\"evidence_type\":\"contrarian\",\"target_words\":340},"
                    "{\"title\":\"What Is Actually True Now\",\"content\":\"Summarize the real current facts users should rely on.\",\"evidence_type\":\"official\",\"target_words\":420},"
                    "{\"title\":\"Practical Takeaways\",\"content\":\"Explain what users should do after the claim is corrected.\",\"evidence_type\":\"mixed\",\"target_words\":320}"
                    "]}"
                )
            return (
                "{"
                "\"report_type\":\"industry_brief\","
                "\"sections\":["
                "{\"title\":\"Overview\",\"content\":\"High-level context and key points.\",\"evidence_type\":\"mixed\",\"target_words\":260},"
                "{\"title\":\"Key Developments\",\"content\":\"Recent events and updates.\",\"evidence_type\":\"official\",\"target_words\":260}"
                "]}"
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
            return "# Long-Form Analysis\n\n## Overview\nMock final report."
        return "{}"

    def usage_summary(self) -> Dict[str, Any]:
        return self.usage.to_dict()
