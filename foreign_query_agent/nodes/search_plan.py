"""Search planning node."""

from datetime import datetime
from typing import Dict, List, Optional

from .base import BaseNode
from ..prompts.prompts import FIRST_SEARCH_PROMPT, language_instruction, recency_instruction
from ..utils import parse_json_fallback


class SearchPlanNode(BaseNode):
    def run(
        self,
        title: str,
        content: str,
        language: str = "English (US)",
        recency_mode: str = "recent_12m_with_90d_anchor",
        report_type: str = "industry_brief",
        evidence_type: str = "mixed",
        target_words: Optional[int] = None,
        subquestions: Optional[List[str]] = None,
        original_query: str = "",
        effective_query: str = "",
        premise_status: str = "valid",
        official_queries: Optional[List[str]] = None,
    ) -> Dict[str, object]:
        payload = str(
            {
                "title": title,
                "content": content,
                "report_type": report_type,
                "evidence_type": evidence_type,
                "target_words": target_words,
                "subquestions": subquestions or [],
                "original_query": original_query,
                "effective_query": effective_query,
                "premise_status": premise_status,
                "official_queries": official_queries or [],
            }
        )
        system_prompt = (
            f"{FIRST_SEARCH_PROMPT}\n"
            f"{language_instruction(language)}\n"
            f"{recency_instruction(recency_mode)}"
        )
        raw = self.llm.invoke(system_prompt, payload)
        current_year = datetime.utcnow().year
        if report_type == "claim_audit":
            default_queries = self._claim_audit_default_queries(
                title=title,
                content=content,
                original_query=original_query,
                effective_query=effective_query,
                official_queries=official_queries or [],
            )
        elif report_type == "company_analysis":
            default_queries = [
                {
                    "intent": "latest_viewpoints",
                    "query": f"{title} latest 90 days {current_year} official statements company update",
                },
                {
                    "intent": "actionable_tactics",
                    "query": f"{title} product pricing revenue business model investor presentation",
                },
                {
                    "intent": "risks_counterpoints",
                    "query": f"{title} competition criticism risks execution issues",
                },
            ]
        elif report_type == "policy_analysis":
            default_queries = [
                {
                    "intent": "latest_viewpoints",
                    "query": f"{title} latest 90 days official policy rule guidance {current_year}",
                },
                {
                    "intent": "actionable_tactics",
                    "query": f"{title} compliance implementation enforcement checklist",
                },
                {
                    "intent": "risks_counterpoints",
                    "query": f"{title} opposition criticism unintended consequences",
                },
            ]
        elif report_type == "person_profile":
            default_queries = [
                {
                    "intent": "latest_viewpoints",
                    "query": f"{title} latest 90 days interview statement talk {current_year}",
                },
                {
                    "intent": "actionable_tactics",
                    "query": f"{title} operating style strategy influence network",
                },
                {
                    "intent": "risks_counterpoints",
                    "query": f"{title} criticism controversy counterpoint",
                },
            ]
        else:
            default_queries = [
                {
                    "intent": "latest_viewpoints",
                    "query": f"{title} latest 90 days {current_year} official analysis",
                },
                {
                    "intent": "actionable_tactics",
                    "query": f"{title} workflow template tooling implementation",
                },
                {
                    "intent": "risks_counterpoints",
                    "query": f"{title} risks limitations critique alternative approach",
                },
            ]
        default_search_query = "" if report_type == "claim_audit" else f"{title} latest {current_year}"
        default = {
            "search_queries": default_queries,
            "search_query": default_search_query,
            "search_tool": "basic_search",
            "reasoning": "default",
        }
        data = parse_json_fallback(raw, default)
        if not isinstance(data, dict):
            return default
        search_queries = data.get("search_queries", default["search_queries"])
        if report_type == "claim_audit":
            search_queries = self._sanitize_claim_audit_queries(
                search_queries,
                fallback_queries=default_queries,
            )
        single_query = data.get("search_query", default["search_query"])
        if report_type == "claim_audit":
            lowered_single = str(single_query or "").strip().lower()
            if any(
                marker in lowered_single
                for marker in (
                    "gpt-5-turbo-0318",
                    "chatgpt-5.4 latest 90 days",
                    "chatgpt5.4 latest 90 days",
                    "gpt-5.4 latest 90 days",
                )
            ):
                single_query = ""
        return {
            "search_queries": search_queries,
            "search_query": single_query,
            "search_tool": data.get("search_tool", "basic_search"),
            "reasoning": data.get("reasoning", ""),
        }

    @staticmethod
    def _claim_audit_default_queries(
        *,
        title: str,
        content: str,
        original_query: str,
        effective_query: str,
        official_queries: List[str],
    ) -> List[Dict[str, str]]:
        normalized_title = (title or "").strip().lower()
        if normalized_title == "official status check":
            queries = official_queries or [
                "site:openai.com/blog official announcement",
                "site:platform.openai.com/docs models official",
            ]
            return [
                {"intent": "official_status", "query": query}
                for query in queries[:3]
            ]
        if normalized_title == "where the claim came from":
            base = (original_query or effective_query or title or "").strip()
            return [
                {
                    "intent": "rumor_origin",
                    "query": f"\"{base}\" rumor OR leak OR discussion site:x.com OR site:github.com OR site:reddit.com",
                }
            ]
        if normalized_title == "what is actually true now":
            effective = (effective_query or content or "").strip()
            return [
                {"intent": "actual_recent_changes", "query": "site:openai.com/blog latest OpenAI model update official"},
                {"intent": "actual_recent_changes", "query": "site:platform.openai.com/docs models OpenAI latest"},
                {"intent": "actual_recent_changes", "query": effective or "OpenAI latest public model updates"},
            ]
        return [
            {"intent": "practical_implications", "query": "site:platform.openai.com/docs model selection guide OpenAI"},
            {"intent": "practical_implications", "query": "site:openai.com/blog OpenAI API updates latest"},
        ]

    @staticmethod
    def _sanitize_claim_audit_queries(search_queries, *, fallback_queries: List[Dict[str, str]]) -> List[Dict[str, str]]:
        blocked_markers = (
            "gpt-5-turbo-0318",
            "chatgpt-5.4 latest 90 days",
            "chatgpt5.4 latest 90 days",
            "gpt-5.4 latest 90 days",
        )
        cleaned: List[Dict[str, str]] = []
        for item in search_queries if isinstance(search_queries, list) else []:
            if isinstance(item, dict):
                value = str(item.get("query") or "").strip()
                intent = str(item.get("intent") or "").strip() or "claim_audit"
            else:
                value = str(item or "").strip()
                intent = "claim_audit"
            lowered = value.lower()
            if not value or any(marker in lowered for marker in blocked_markers):
                continue
            cleaned.append({"intent": intent, "query": value})
        return cleaned or list(fallback_queries)
