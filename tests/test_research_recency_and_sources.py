"""Deep Research recency and source-priority tests."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from foreign_query_agent.nodes.search_plan import SearchPlanNode
from foreign_query_agent.nodes.reflection import ReflectionNode
from foreign_query_agent.prompts.prompts import FIRST_SEARCH_PROMPT, recency_instruction


class _JsonlessLLM:
    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        return "{}"


def test_search_plan_fallback_queries_include_recency_and_keyword_anchors():
    node = SearchPlanNode(_JsonlessLLM())
    plan = node.run(
        "Anthropic company business model and moat",
        "Need current strategic and financial signals.",
        recency_mode="recent_12m_with_90d_anchor",
        report_type="company_analysis",
        evidence_type="primary",
        target_words=320,
    )
    queries = [item.get("query", "") for item in plan.get("search_queries", []) if isinstance(item, dict)]
    merged = " ".join(queries)
    assert any("90 days" in q for q in queries)
    assert "official" in merged.lower() or "investor" in merged.lower() or "earnings" in merged.lower()


def test_reflection_node_accepts_recency_mode_and_returns_query_pack():
    node = ReflectionNode(_JsonlessLLM())
    reflect = node.run(
        "Karpathy tooling",
        "Need practical techniques.",
        "Current summary is generic.",
        recency_mode="recent_12m_with_90d_anchor",
    )
    assert isinstance(reflect.get("search_queries"), list)
    assert reflect.get("search_tool") == "basic_search"
    assert "90 days" in reflect["search_queries"][0]["query"]


def test_prompts_include_primary_source_priority_language():
    assert "official statements" in FIRST_SEARCH_PROMPT
    assert "GitHub" in FIRST_SEARCH_PROMPT
    assert "podcasts/interviews" in FIRST_SEARCH_PROMPT
    assert "last 90 days" in recency_instruction("recent_12m_with_90d_anchor")
