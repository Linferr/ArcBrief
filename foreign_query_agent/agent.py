"""Main QueryAgent implementation."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import inspect
import os
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .config import Settings
from .llm import LLMClient, LLMConfig, MockLLM
from .state import (
    CriticResult,
    EvidenceItem,
    ParagraphState,
    ReportState,
    ResearchSpec,
    SearchItem,
    SectionAssessment,
    SectionPlan,
)
from .nodes.formatting import FormattingNode
from .nodes.host import HostNode
from .nodes.premise_check import PremiseCheckNode
from .nodes.reflection import ReflectionNode
from .nodes.report_structure import ReportStructureNode
from .nodes.search_plan import SearchPlanNode
from .nodes.summary import ReflectionSummaryNode, SummaryNode
from .logger import write_log
from .utils import slugify
from .tools.factory import TAVILY_PROVIDER, SearchToolBuildMeta, create_search_tool_with_meta
from .tools.mock_tool import MockSearchTool


_PRIORITY_SOURCE_HOSTS = (
    "x.com",
    "twitter.com",
    "github.com",
    "reddit.com",
    "substack.com",
    "youtube.com",
    "podcast",
)

_PRIMARY_SOURCE_HINTS = (
    "x.com",
    "twitter.com",
    "github.com",
    ".gov",
    ".edu",
    "sec.gov",
    "europa.eu",
    "whitehouse.gov",
    "docs.",
    "developer.",
    "research.",
    "blog.",
    "press.",
)


class _NullSemaphore:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class QueryAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_state = None
        self.runtime_fallback_tool = None
        self.runtime_fallback_meta: Optional[SearchToolBuildMeta] = None
        if settings.mock_mode:
            self.llm = MockLLM()
            self.tool = MockSearchTool()
            self.search_meta = SearchToolBuildMeta(
                provider_requested="MockSearchTool",
                provider_effective="MockSearchTool",
                fallback_reason="",
                llm_assisted_search=False,
            )
        else:
            llm_config = LLMConfig(
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                base_url=settings.llm_base_url,
            )
            self.llm = LLMClient(llm_config)
            self.tool, self.search_meta = create_search_tool_with_meta(
                settings.search_provider,
                fallback_tavily_key=settings.tavily_api_key,
                bocha_api_key=settings.bocha_api_key,
                zhipu_api_key=settings.zhipu_api_key,
                zhipu_openai_base_url=settings.zhipu_openai_base_url,
                zhipu_web_search_model=settings.zhipu_web_search_model,
                exa_api_key=settings.exa_api_key,
                volcengine_api_key=settings.volcengine_api_key,
                volcengine_openai_base_url=settings.volcengine_openai_base_url,
                volcengine_model_ep=settings.volcengine_model_ep,
                strict=settings.research_strict_provider,
            )
            if settings.search_provider != TAVILY_PROVIDER and settings.tavily_api_key:
                fallback_tool, fallback_meta = create_search_tool_with_meta(
                    TAVILY_PROVIDER,
                    fallback_tavily_key=settings.tavily_api_key,
                    strict=False,
                )
                if fallback_meta.provider_effective == TAVILY_PROVIDER:
                    self.runtime_fallback_tool = fallback_tool
                    self.runtime_fallback_meta = fallback_meta

        self.structure_node = ReportStructureNode(self.llm)
        self.premise_node = PremiseCheckNode(self.llm)
        self.search_node = SearchPlanNode(self.llm)
        self.summary_node = SummaryNode(self.llm)
        self.reflection_node = ReflectionNode(self.llm)
        self.reflection_summary_node = ReflectionSummaryNode(self.llm)
        self.formatting_node = FormattingNode(self.llm)
        self.host_node = HostNode(self.llm)

    @staticmethod
    def _normalize_language(language: str) -> str:
        return language if language in {"English (US)", "Chinese (Simplified)", "Japanese"} else "English (US)"

    @staticmethod
    def _invoke_node_run(node: Any, *args, **kwargs):
        run_fn = getattr(node, "run")
        signature = inspect.signature(run_fn)
        accepted_kwargs = {
            key: value for key, value in kwargs.items() if key in signature.parameters
        }
        return run_fn(*args, **accepted_kwargs)

    @staticmethod
    def _normalize_report_type(report_type: str) -> str:
        normalized = (report_type or "").strip().lower()
        mapping = {
            "industry": "industry_brief",
            "industry_brief": "industry_brief",
            "company": "company_analysis",
            "company_analysis": "company_analysis",
            "person": "person_profile",
            "person_profile": "person_profile",
            "policy": "policy_analysis",
            "policy_analysis": "policy_analysis",
            "claim_audit": "claim_audit",
            "claim-audit": "claim_audit",
            "fact_check": "claim_audit",
            "fact-check": "claim_audit",
            "product_fact_check": "claim_audit",
        }
        return mapping.get(normalized, "industry_brief")

    def llm_usage_summary(self) -> Dict[str, Any]:
        summary_fn = getattr(self.llm, "usage_summary", None)
        if callable(summary_fn):
            data = summary_fn()
            if isinstance(data, dict):
                return data
        return {}

    def research(
        self,
        query: str,
        progress_cb=None,
        language: str = "English (US)",
        report_type: Optional[str] = None,
        length_preset: str = "long",
    ) -> str:
        language_used = self._normalize_language(language)
        report_shape = "long_analysis"
        quality_mode = "quality_first"
        original_query = query
        requested_report_type = report_type or (
            self.structure_node.select_template(query)
            if hasattr(self.structure_node, "select_template")
            else "industry_brief"
        )
        premise_result = self._invoke_node_run(self.premise_node, query, language=language_used)
        premise_status = str(premise_result.get("premise_status") or "valid").strip().lower()
        if premise_status not in {"valid", "disputed", "invalid"}:
            premise_status = "valid"
        effective_query = str(premise_result.get("reframed_query") or query).strip() or query
        recommended_report_type = str(premise_result.get("recommended_report_type") or "").strip()
        report_type_requested = self._normalize_report_type(requested_report_type)
        report_type_effective = report_type_requested
        if premise_status in {"invalid", "disputed"} and recommended_report_type:
            report_type_effective = self._normalize_report_type(recommended_report_type)
        spec = ResearchSpec(
            query=original_query,
            language=language_used,
            report_shape=report_shape,
            report_type=report_type_effective,
            report_type_requested=report_type_requested,
            report_type_effective=report_type_effective,
            length_preset=length_preset,
            quality_mode=quality_mode,
            original_query=original_query,
            effective_query=effective_query,
            premise_status=premise_status,
            validation_notes=str(premise_result.get("validation_notes") or "").strip(),
            official_queries=[
                str(item).strip()
                for item in (premise_result.get("official_queries") or [])
                if str(item).strip()
            ],
        )
        state = ReportState(
            query=original_query,
            spec=spec,
            report_type=report_type_effective,
            report_type_requested=report_type_requested,
            report_type_effective=report_type_effective,
            report_shape=report_shape,
            length_preset=length_preset,
            quality_mode=quality_mode,
        )
        run_id = self._build_run_id(query)
        planning_template = report_type_effective
        state.planning_template = planning_template
        if progress_cb:
            progress_cb(
                {
                    "stage": "premise_check",
                    "message": (
                        f"premise={premise_status} "
                        f"reframed={str(effective_query != original_query).lower()} "
                        f"report_type={report_type_effective}"
                    ),
                    "run_id": run_id,
                }
            )
        if hasattr(self.structure_node, "run_plan"):
            plan_bundle = self.structure_node.run_plan(
                effective_query,
                language=language_used,
                report_shape=report_shape,
                length_preset=length_preset or "long",
                report_type=planning_template,
            )
            section_plans = [
                SectionPlan(
                    title=str(item.get("title") or "").strip(),
                    content=str(item.get("content") or "").strip(),
                    evidence_type=str(item.get("evidence_type") or "mixed").strip() or "mixed",
                    target_words=max(220, int(item.get("target_words") or 260)),
                    pass_criteria=str(item.get("pass_criteria") or "").strip(),
                    subquestions=[
                        str(question).strip()
                        for question in (item.get("subquestions") or [])
                        if str(question).strip()
                    ],
                )
                for item in (plan_bundle.get("sections") or [])
                if str(item.get("title") or "").strip() and str(item.get("content") or "").strip()
            ][: self.settings.max_paragraphs]
        else:
            outline = self.structure_node.run(effective_query, language=language_used)[: self.settings.max_paragraphs]
            section_plans = [
                SectionPlan(title=item["title"], content=item["content"])
                for item in outline
            ]
        state.section_plans = list(section_plans)
        if progress_cb:
            progress_cb(
                {
                    "stage": "outline",
                    "message": f"Outline generated ({planning_template})",
                    "run_id": run_id,
                }
            )

        for section_plan in section_plans:
            state.paragraphs.append(
                ParagraphState(title=section_plan.title, content=section_plan.content, plan=section_plan)
            )

        total_paragraphs = len(state.paragraphs)
        section_results = self._run_section_pipeline(
            state=state,
            run_id=run_id,
            total_paragraphs=total_paragraphs,
            progress_cb=progress_cb,
            language_used=language_used,
        )
        blocked_result = next((item for item in section_results if item.get("blocked")), None)
        if blocked_result:
            final_report = self._build_gate_blocked_report(
                query=state.query,
                paragraph=blocked_result["paragraph"],
                critic_result=blocked_result["critic_result"],
                language=language_used,
                exhausted=blocked_result.get("exhausted", False),
                state=state,
            )
            write_log("query", "Final report blocked by critic gate", run_id=run_id)
            if progress_cb:
                progress_cb({"stage": "final", "message": "Report blocked by critic gate", "run_id": run_id})
            state.final_report = final_report
            state.section_assessments = [
                paragraph.assessment.to_dict()
                for paragraph in state.paragraphs
                if paragraph.assessment is not None
            ]
            state.touch()
            self.last_state = state
            self.last_run_id = run_id
            return final_report

        final_report = self._invoke_node_run(
            self.formatting_node,
            [{"title": paragraph.title, "content": paragraph.latest_summary} for paragraph in state.paragraphs],
            language=language_used,
            section_plans=state.section_plans,
            report_shape=state.report_shape,
            report_type=state.report_type,
        )
        final_report = self._strip_stale_sources(final_report)
        final_report = self._strip_orphan_refs(final_report, state.global_source_map)
        final_report = self._append_sources_from_map(final_report, state.global_source_map, language_used)
        write_log("query", "Final report generated", run_id=run_id)
        if progress_cb:
            progress_cb({"stage": "final", "message": "Report formatted", "run_id": run_id})
        state.delivery_status = "full"
        state.gate_decision = "PASS"
        state.blocking_issues = []
        state.final_report = final_report
        state.section_assessments = [
            paragraph.assessment.to_dict()
            for paragraph in state.paragraphs
            if paragraph.assessment is not None
        ]
        state.touch()
        self.last_state = state
        self.last_run_id = run_id
        return final_report

    def _run_section_pipeline(
        self,
        state: ReportState,
        run_id: str,
        total_paragraphs: int,
        progress_cb,
        language_used: str,
    ) -> List[Dict[str, Any]]:
        source_lock = threading.Lock()
        max_parallel_sections = max(1, min(getattr(self.settings, "max_parallel_sections", 1), total_paragraphs or 1))
        if total_paragraphs <= 1 or max_parallel_sections <= 1:
            return [
                self._process_paragraph(
                    paragraph=paragraph,
                    idx=idx,
                    total_paragraphs=total_paragraphs,
                    state=state,
                    run_id=run_id,
                    progress_cb=progress_cb,
                    language_used=language_used,
                    source_lock=source_lock,
                    section_semaphore=None,
                )
                for idx, paragraph in enumerate(state.paragraphs)
            ]

        section_semaphore = threading.BoundedSemaphore(max_parallel_sections)
        results: List[Optional[Dict[str, Any]]] = [None] * total_paragraphs
        with ThreadPoolExecutor(max_workers=total_paragraphs) as executor:
            future_map = {
                executor.submit(
                    self._process_paragraph,
                    paragraph,
                    idx,
                    total_paragraphs,
                    state,
                    run_id,
                    progress_cb,
                    language_used,
                    source_lock,
                    section_semaphore,
                ): idx
                for idx, paragraph in enumerate(state.paragraphs)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                paragraph = state.paragraphs[idx]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    results[idx] = self._section_fallback_result(
                        paragraph=paragraph,
                        idx=idx,
                        total_paragraphs=total_paragraphs,
                        run_id=run_id,
                        progress_cb=progress_cb,
                        reason=str(exc),
                    )
        return [item for item in results if item is not None]

    @staticmethod
    def _tool_error_attr(tool: Any, name: str) -> str:
        value = getattr(tool, name, "") or ""
        if value:
            return str(value)
        client = getattr(tool, "client", None)
        if client is not None:
            client_value = getattr(client, name, "") or ""
            if client_value:
                return str(client_value)
        return ""

    @staticmethod
    def _should_runtime_fallback(error_class: str) -> bool:
        return error_class in {"auth_error", "quota_error"}

    def _mark_runtime_fallback(self, reason: str) -> None:
        if self.runtime_fallback_meta is None:
            return
        self.search_meta.provider_effective = self.runtime_fallback_meta.provider_effective
        self.search_meta.fallback_reason = reason
        self.search_meta.llm_assisted_search = self.runtime_fallback_meta.llm_assisted_search
        self.search_meta.openai_compatible = self.runtime_fallback_meta.openai_compatible
        self.search_meta.api_style = self.runtime_fallback_meta.api_style

    def _search_with_runtime_fallback(
        self,
        query_text: str,
        *,
        run_id: str,
        progress_cb,
        paragraph_title: str,
        paragraph_idx: int,
        total_paragraphs: int,
        round_number: Optional[int] = None,
    ):
        response = self.tool.search(query_text, max_results=self.settings.max_results)
        error_class = self._tool_error_attr(self.tool, "last_error_class").strip()
        error_message = self._tool_error_attr(self.tool, "last_error_message").strip()
        if response.results or not self.runtime_fallback_tool or not self._should_runtime_fallback(error_class):
            return response

        fallback_reason = (
            f"Runtime provider fallback: {self.search_meta.provider_requested} -> "
            f"{self.runtime_fallback_meta.provider_effective if self.runtime_fallback_meta else TAVILY_PROVIDER} "
            f"due to {error_class}: {error_message or 'provider returned no results'}"
        )
        write_log("query", fallback_reason, run_id=run_id)
        if progress_cb:
            event = {
                "stage": "warning",
                "message": fallback_reason,
                "paragraph": paragraph_title,
                "paragraph_idx": paragraph_idx + 1,
                "total_paragraphs": total_paragraphs,
                "run_id": run_id,
            }
            if round_number is not None:
                event["round"] = round_number
            progress_cb(event)

        fallback_response = self.runtime_fallback_tool.search(query_text, max_results=self.settings.max_results)
        if fallback_response.results:
            self._mark_runtime_fallback(fallback_reason)
            return fallback_response

        fallback_error = self._tool_error_attr(self.runtime_fallback_tool, "last_error_message").strip()
        if fallback_error:
            write_log("query", f"Tavily runtime fallback failed: {fallback_error}", run_id=run_id)
        return response

    def _process_paragraph(
        self,
        paragraph: ParagraphState,
        idx: int,
        total_paragraphs: int,
        state: ReportState,
        run_id: str,
        progress_cb,
        language_used: str,
        source_lock: threading.Lock,
        section_semaphore: Optional[threading.BoundedSemaphore],
    ) -> Dict[str, Any]:
        guard = section_semaphore or _NullSemaphore()
        with guard:
            try:
                plan = paragraph.plan or SectionPlan(title=paragraph.title, content=paragraph.content)
                effective_report_type = state.report_type_effective or state.report_type
                write_log("query", f"SearchPlan: {paragraph.title}", run_id=run_id)
                search_plan = self._invoke_node_run(
                    self.search_node,
                    paragraph.title,
                    paragraph.content,
                    language=language_used,
                    recency_mode=self.settings.research_recency_mode,
                    report_type=effective_report_type,
                    evidence_type=plan.evidence_type,
                    target_words=plan.target_words,
                    subquestions=plan.subquestions,
                    original_query=(state.spec.original_query if state.spec else state.query),
                    effective_query=(state.spec.effective_query if state.spec else state.query),
                    premise_status=(state.spec.premise_status if state.spec else "valid"),
                    official_queries=(state.spec.official_queries if state.spec else []),
                )
                queries = self._ensure_recency_query(
                    self._expand_query_pack(search_plan, fallback=f"{paragraph.title} latest {datetime.utcnow().year}"),
                    paragraph.title,
                    report_type=effective_report_type,
                )

                batches: List[List[Dict[str, str]]] = []
                for search_query in queries:
                    write_log("query", f"Search: {search_query}", run_id=run_id)
                    if progress_cb:
                        progress_cb(
                            {
                                "stage": "search",
                                "message": f"Search: {search_query}",
                                "paragraph": paragraph.title,
                                "paragraph_idx": idx + 1,
                                "total_paragraphs": total_paragraphs,
                                "run_id": run_id,
                            }
                        )
                    response = self._search_with_runtime_fallback(
                        search_query,
                        run_id=run_id,
                        progress_cb=progress_cb,
                        paragraph_title=paragraph.title,
                        paragraph_idx=idx,
                        total_paragraphs=total_paragraphs,
                    )
                    result_batch = [self._normalize_result_item(result.__dict__) for result in response.results]
                    batches.append(result_batch)
                    for result in response.results:
                        paragraph.search_history.append(
                            SearchItem(query=search_query, title=result.title, url=result.url, content=result.content)
                        )

                ranked_results = self._merge_and_rank_results(paragraph.title, paragraph.content, batches)
                paragraph.evidence_items = self._build_evidence_items(ranked_results)
                year_range = self._detect_year_range(ranked_results)
                if year_range and progress_cb:
                    progress_cb(
                        {
                            "stage": "search_window",
                            "message": f"Evidence year range: {year_range[0]}-{year_range[1]}",
                            "paragraph": paragraph.title,
                            "paragraph_idx": idx + 1,
                            "total_paragraphs": total_paragraphs,
                            "run_id": run_id,
                        }
                    )

                summary_text, summary_smap = self._invoke_node_run(
                    self.summary_node,
                    paragraph.title,
                    paragraph.content,
                    " | ".join(queries),
                    ranked_results,
                    language=language_used,
                    report_type=effective_report_type,
                    target_words=plan.target_words,
                    quality_mode=state.quality_mode,
                    evidence_type=plan.evidence_type,
                    original_query=(state.spec.original_query if state.spec else state.query),
                    effective_query=(state.spec.effective_query if state.spec else state.query),
                    premise_status=(state.spec.premise_status if state.spec else "valid"),
                )
                with source_lock:
                    paragraph.latest_summary, paragraph.source_map = self._assign_global_source_ids(
                        summary_text,
                        summary_smap,
                        state,
                    )
                if paragraph.latest_summary:
                    write_log("query", f"Summary round 1: {paragraph.latest_summary[:300]}...", run_id=run_id)
                    if progress_cb:
                        progress_cb(
                            {
                                "stage": "summary",
                                "message": "Summary round 1 ready",
                                "paragraph": paragraph.title,
                                "paragraph_idx": idx + 1,
                                "total_paragraphs": total_paragraphs,
                                "round": 1,
                                "run_id": run_id,
                            }
                        )

                while True:
                    host_feedback = self._invoke_node_run(
                        self.host_node,
                        paragraph.title,
                        paragraph.content,
                        paragraph.latest_summary,
                        language=language_used,
                        report_type=effective_report_type,
                        premise_status=(state.spec.premise_status if state.spec else "valid"),
                    )
                    critic_result = CriticResult.from_payload(
                        host_feedback,
                        fallback_query=f"{paragraph.title} evidence statistics",
                    )
                    paragraph.host_critiques.append(
                        {
                            "gate_decision": critic_result.gate_decision,
                            "overall_score": str(critic_result.overall_score),
                            "blocking_issues": "; ".join(critic_result.blocking_issues),
                            "critique": critic_result.critique,
                            "questions": "; ".join(critic_result.questions),
                            "suggested_search": "; ".join(critic_result.suggested_queries),
                        }
                    )
                    write_log("host", f"Critique: {critic_result.critique}", run_id=run_id)
                    write_log("host", f"Questions: {'; '.join(critic_result.questions)}", run_id=run_id)
                    write_log("host", f"Suggested search: {'; '.join(critic_result.suggested_queries)}", run_id=run_id)
                    write_log(
                        "host",
                        (
                            f"Critic gate: decision={critic_result.gate_decision} "
                            f"score={critic_result.overall_score} "
                            f"blocking={'; '.join(critic_result.blocking_issues) or 'none'}"
                        ),
                        run_id=run_id,
                    )
                    if progress_cb:
                        progress_cb(
                            {
                                "stage": "host",
                                "message": critic_result.critique,
                                "paragraph": paragraph.title,
                                "paragraph_idx": idx + 1,
                                "total_paragraphs": total_paragraphs,
                                "round": paragraph.reflection_count + 1,
                                "run_id": run_id,
                            }
                        )
                        progress_cb(
                            {
                                "stage": "critic_gate",
                                "message": (
                                    f"decision={critic_result.gate_decision} "
                                    f"score={critic_result.overall_score} "
                                    f"blocking={'; '.join(critic_result.blocking_issues) or 'none'}"
                                ),
                                "paragraph": paragraph.title,
                                "paragraph_idx": idx + 1,
                                "total_paragraphs": total_paragraphs,
                                "round": paragraph.reflection_count + 1,
                                "run_id": run_id,
                            }
                        )

                    paragraph.assessment = SectionAssessment(
                        title=paragraph.title,
                        gate_decision=critic_result.gate_decision,
                        overall_score=critic_result.overall_score,
                        blocking_issues=list(critic_result.blocking_issues),
                        source_count=len(paragraph.source_map),
                        primary_source_count=sum(
                            1 for info in paragraph.source_map.values() if (info.get("source_type") or "") == "primary"
                        ),
                    )

                    if critic_result.gate_decision == "PASS":
                        return {
                            "paragraph_idx": idx,
                            "paragraph": paragraph,
                            "blocked": False,
                            "critic_result": None,
                            "exhausted": False,
                            "fallback": False,
                        }

                    if critic_result.gate_decision == "REJECT":
                        return {
                            "paragraph_idx": idx,
                            "paragraph": paragraph,
                            "blocked": True,
                            "critic_result": critic_result,
                            "exhausted": False,
                            "fallback": False,
                        }

                    if paragraph.reflection_count >= self.settings.max_reflections:
                        return {
                            "paragraph_idx": idx,
                            "paragraph": paragraph,
                            "blocked": True,
                            "critic_result": critic_result,
                            "exhausted": True,
                            "fallback": False,
                        }

                    suggested_queries = list(critic_result.suggested_queries)
                    if suggested_queries:
                        queries = [item for item in suggested_queries[:3] if isinstance(item, str) and item.strip()]
                    else:
                        reflect = self._invoke_node_run(
                            self.reflection_node,
                            paragraph.title,
                            paragraph.content,
                            paragraph.latest_summary,
                            language=language_used,
                            recency_mode=self.settings.research_recency_mode,
                            report_type=effective_report_type,
                            evidence_type=plan.evidence_type,
                            target_words=plan.target_words,
                            subquestions=plan.subquestions,
                            original_query=(state.spec.original_query if state.spec else state.query),
                            effective_query=(state.spec.effective_query if state.spec else state.query),
                            premise_status=(state.spec.premise_status if state.spec else "valid"),
                            official_queries=(state.spec.official_queries if state.spec else []),
                        )
                        queries = self._expand_query_pack(
                            reflect,
                            fallback=f"{paragraph.title} updates {datetime.utcnow().year}",
                        )
                    queries = self._ensure_recency_query(
                        queries,
                        paragraph.title,
                        report_type=effective_report_type,
                    )

                    reflection_batches: List[List[Dict[str, str]]] = []
                    for query_text in queries:
                        write_log("query", f"Reflection search: {query_text}", run_id=run_id)
                        if progress_cb:
                            progress_cb(
                                {
                                    "stage": "reflection",
                                    "message": f"Reflection search: {query_text}",
                                    "paragraph": paragraph.title,
                                    "paragraph_idx": idx + 1,
                                    "total_paragraphs": total_paragraphs,
                                    "round": paragraph.reflection_count + 1,
                                    "run_id": run_id,
                                }
                            )
                        response = self._search_with_runtime_fallback(
                            query_text,
                            run_id=run_id,
                            progress_cb=progress_cb,
                            paragraph_title=paragraph.title,
                            paragraph_idx=idx,
                            total_paragraphs=total_paragraphs,
                            round_number=paragraph.reflection_count + 1,
                        )
                        reflection_result_batch = [
                            self._normalize_result_item(result.__dict__) for result in response.results
                        ]
                        reflection_batches.append(reflection_result_batch)
                        for result in response.results:
                            paragraph.search_history.append(
                                SearchItem(query=query_text, title=result.title, url=result.url, content=result.content)
                            )

                    ranked_reflection_results = self._merge_and_rank_results(
                        paragraph.title,
                        paragraph.content,
                        reflection_batches,
                    )
                    paragraph.evidence_items = self._build_evidence_items(ranked_reflection_results)
                    refl_text, refl_smap = self._invoke_node_run(
                        self.reflection_summary_node,
                        paragraph.title,
                        paragraph.content,
                        " | ".join(queries),
                        ranked_reflection_results,
                        paragraph.latest_summary,
                        language=language_used,
                        report_type=effective_report_type,
                        target_words=plan.target_words,
                        quality_mode=state.quality_mode,
                        evidence_type=plan.evidence_type,
                        original_query=(state.spec.original_query if state.spec else state.query),
                        effective_query=(state.spec.effective_query if state.spec else state.query),
                        premise_status=(state.spec.premise_status if state.spec else "valid"),
                    )
                    with source_lock:
                        paragraph.latest_summary, paragraph.source_map = self._assign_global_source_ids(
                            refl_text,
                            refl_smap,
                            state,
                        )

                    paragraph.reflection_count += 1
                    if paragraph.latest_summary:
                        write_log(
                            "query",
                            f"Summary round {paragraph.reflection_count + 1}: {paragraph.latest_summary[:300]}...",
                            run_id=run_id,
                        )
                        if progress_cb:
                            progress_cb(
                                {
                                    "stage": "summary",
                                    "message": f"Summary round {paragraph.reflection_count + 1} ready",
                                    "paragraph": paragraph.title,
                                    "paragraph_idx": idx + 1,
                                    "total_paragraphs": total_paragraphs,
                                    "round": paragraph.reflection_count + 1,
                                    "run_id": run_id,
                                }
                            )
            except Exception as exc:
                return self._section_fallback_result(
                    paragraph=paragraph,
                    idx=idx,
                    total_paragraphs=total_paragraphs,
                    run_id=run_id,
                    progress_cb=progress_cb,
                    reason=str(exc),
                )

    def _section_fallback_result(
        self,
        paragraph: ParagraphState,
        idx: int,
        total_paragraphs: int,
        run_id: str,
        progress_cb,
        reason: str,
    ) -> Dict[str, Any]:
        detail = (reason or "Unknown processing failure").strip()[:120]
        write_log("query", f"ERROR processing paragraph '{paragraph.title}': {detail}", run_id=run_id)
        if progress_cb:
            progress_cb(
                {
                    "stage": "error",
                    "message": f"Section fallback for paragraph {idx + 1}: {detail[:50]}",
                    "paragraph": paragraph.title,
                    "paragraph_idx": idx + 1,
                    "total_paragraphs": total_paragraphs,
                    "run_id": run_id,
                }
            )
        paragraph.fallback_reason = detail
        paragraph.latest_summary = self._build_section_fallback_summary(paragraph.title, detail)
        return {
            "paragraph_idx": idx,
            "paragraph": paragraph,
            "blocked": False,
            "critic_result": None,
            "exhausted": False,
            "fallback": True,
        }

    @staticmethod
    def _build_section_fallback_summary(title: str, reason: str) -> str:
        return (
            "Evidence insufficient for this section.\n\n"
            f"- Section: {title}\n"
            f"- Fallback reason: {reason}\n"
            "- Recommended next step: rerun this section with broader or more reliable source coverage."
        )

    def save_report(self, report: str, output_dir: str) -> str:
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = getattr(self, "last_run_id", "run")
        path = os.path.join(output_dir, f"query_report_{ts}_{run_id}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)
        return path

    def _build_run_id(self, query: str) -> str:
        ts = datetime.now().strftime("%H%M%S")
        return f"{slugify(query)}_{ts}"

    @staticmethod
    def _strip_stale_sources(report: str) -> str:
        """Remove any LLM-generated Sources section before the real one is appended."""
        pattern = re.compile(
            r"\n##\s+(?:Sources|来源|来源索引|ソース|ソース索引|懂埭|末奈旦)\s*\n.*?(?=\n##\s+|\Z)",
            re.DOTALL,
        )
        report = pattern.sub("\n", report)
        for leaked in (
            'Sources appended automatically per protocol.',
            'sources are appended automatically',
        ):
            report = report.replace(leaked, '')
        return report.rstrip()

    @staticmethod
    def _assign_global_source_ids(
        text: str,
        local_source_map: Dict[str, Dict[str, str]],
        state: ReportState,
    ) -> Tuple[str, Dict[str, Dict[str, str]]]:
        """Promote paragraph-local S-IDs to report-global IDs immediately."""
        if not local_source_map:
            return text, {}

        rewritten = text or ""
        paragraph_source_map: Dict[str, Dict[str, str]] = {}
        replacements: List[Tuple[str, str]] = []

        for local_id in sorted(local_source_map.keys(), key=lambda key: int(key[1:])):
            global_id = f"S{state.next_source_index}"
            state.next_source_index += 1
            source_info = dict(local_source_map[local_id])
            state.global_source_map[global_id] = source_info
            paragraph_source_map[global_id] = source_info
            replacements.append((local_id, global_id))

        for local_id, global_id in sorted(replacements, key=lambda item: int(item[0][1:]), reverse=True):
            rewritten = rewritten.replace(f"[{local_id}]", f"[{global_id}]")

        return rewritten, paragraph_source_map

    def _normalize_result_item(self, item: Dict[str, str]) -> Dict[str, str]:
        normalized = dict(item or {})
        host = self._extract_host(normalized.get("url") or "")
        normalized["host"] = host
        normalized["source_type"] = self._classify_source_type(normalized.get("url") or "", normalized.get("title") or "")
        return normalized

    def _classify_source_type(self, url: str, title: str) -> str:
        host = self._extract_host(url)
        lowered_title = (title or "").lower()
        if not host:
            return "unknown"
        if any(marker in host for marker in _PRIMARY_SOURCE_HINTS):
            return "primary"
        if any(token in lowered_title for token in ("transcript", "official", "filing", "release notes")):
            return "primary"
        return "secondary"

    def _build_evidence_items(self, results: List[Dict[str, str]]) -> List[EvidenceItem]:
        evidence_items: List[EvidenceItem] = []
        for idx, item in enumerate(results, start=1):
            evidence_items.append(
                EvidenceItem(
                    source_id=f"S{idx}",
                    title=str(item.get("title") or "").strip(),
                    url=str(item.get("url") or "").strip(),
                    content=str(item.get("content") or "").strip(),
                    source_type=str(item.get("source_type") or "unknown").strip() or "unknown",
                    host=str(item.get("host") or "").strip(),
                )
            )
        return evidence_items

    @staticmethod
    def _strip_orphan_refs(report: str, global_source_map: Dict[str, Dict[str, str]]) -> str:
        """Remove [S#] references from the report that are not in the global source map."""
        valid_ids = set(global_source_map.keys())
        def _replace(match: re.Match) -> str:
            sid = f"S{match.group(1)}"
            return match.group(0) if sid in valid_ids else ""
        return re.sub(r'\[S(\d+)\]', _replace, report)

    @staticmethod
    def _append_sources_from_map(
        report: str,
        global_source_map: Dict[str, Dict[str, str]],
        language: str,
    ) -> str:
        """Append a numbered Sources section using the global source map."""
        heading = {
            "Chinese (Simplified)": "## 来源",
            "Japanese": "## ソース",
        }.get(language, "## Sources")
        empty_line = {
            "Chinese (Simplified)": "- （暂无来源记录）",
            "Japanese": "- （ソース記録なし）",
        }.get(language, "- (no sources recorded)")

        lines = ["", heading, ""]
        if global_source_map:
            for sid in sorted(global_source_map.keys(), key=lambda k: int(k[1:])):
                info = global_source_map[sid]
                title = (info.get("title") or "Untitled").strip()
                url = (info.get("url") or "").strip()
                if QueryAgent._is_placeholder_source_title(title):
                    continue
                source_type = str(info.get("source_type") or "").strip()
                prefix = f"[{source_type}] " if source_type else ""
                entry = f"- [{sid}] {prefix}{title}"
                if url:
                    entry += f" -- {url}"
                lines.append(entry)
        if len(lines) == 3:
            lines.append(empty_line)
        return report.rstrip() + "\n" + "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _is_placeholder_source_title(title: str) -> bool:
        lowered = (title or "").strip().lower()
        return bool(
            re.match(r"^(volcano engine|tavily|exa|bocha|zhipu).*(result for|search result)", lowered)
        )

    def _build_gate_blocked_report(
        self,
        query: str,
        paragraph: ParagraphState,
        critic_result: CriticResult,
        language: str,
        exhausted: bool,
        state: ReportState,
    ) -> str:
        summary = (paragraph.latest_summary or "Evidence insufficient.").strip()
        lines = [
            "# Research Gate Notice",
            "",
            "## Report Status",
            f"- query: {query}",
            f"- paragraph: {paragraph.title}",
            f"- gate_decision: {critic_result.gate_decision}",
            f"- overall_score: {critic_result.overall_score}/5",
        ]
        if exhausted:
            lines.append("- note: max reflections reached before PASS.")
        lines.extend(["", "## Blocking Issues"])
        for issue in critic_result.blocking_issues or ["Evidence quality remains below release threshold."]:
            lines.append(f"- {issue}")
        lines.extend(["", "## Suggested Follow-up Queries"])
        for suggestion in critic_result.suggested_queries or ["Collect additional primary sources before re-running."]:
            lines.append(f"- {suggestion}")
        lines.extend(
            [
                "",
                "## Next Step",
                "- Re-run after collecting stronger primary or official evidence for the blocked section.",
                "",
                "## Current Best-Effort Summary",
                self._truncate_text(summary, 1200),
            ]
        )
        report = "\n".join(lines).strip()
        report = self._strip_stale_sources(report)
        report = self._strip_orphan_refs(report, state.global_source_map)
        state.delivery_status = "limited"
        state.gate_decision = critic_result.gate_decision
        state.blocking_issues = list(critic_result.blocking_issues)
        return self._append_sources_from_map(report, state.global_source_map, language)

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        cleaned = (text or "").strip()
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[: max(0, max_chars - 1)].rstrip() + "…"

    def _expand_query_pack(self, plan: Dict[str, object], fallback: str) -> List[str]:
        queries: List[str] = []
        raw_queries = plan.get("search_queries") if isinstance(plan, dict) else None
        if isinstance(raw_queries, list):
            for item in raw_queries:
                if isinstance(item, dict):
                    value = str(item.get("query") or "").strip()
                else:
                    value = str(item or "").strip()
                if value and value not in queries:
                    queries.append(value)
        single = str(plan.get("search_query") or "").strip() if isinstance(plan, dict) else ""
        if single and single not in queries:
            queries.append(single)
        if not queries:
            queries.append(fallback)
        return queries[:3]

    def _ensure_recency_query(self, queries: List[str], title: str, report_type: str = "industry_brief") -> List[str]:
        cleaned = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
        if report_type == "claim_audit":
            return cleaned[:3]
        has_recency = any(
            ("90 days" in q.lower()) or ("last 3 months" in q.lower()) or ("recent" in q.lower())
            for q in cleaned
        )
        if has_recency:
            return cleaned[:3]
        current_year = datetime.utcnow().year
        cleaned.insert(0, f"{title} latest 90 days {current_year}")
        return cleaned[:3]

    def _merge_and_rank_results(
        self,
        paragraph_title: str,
        paragraph_content: str,
        batches: List[List[Dict[str, str]]],
    ) -> List[Dict[str, str]]:
        merged: List[Dict[str, str]] = []
        for batch in batches:
            for item in batch:
                if isinstance(item, dict):
                    merged.append(item)

        deduped: Dict[str, Dict[str, str]] = {}
        for item in merged:
            key = self._result_key(item)
            if key in deduped:
                old = deduped[key]
                if len((item.get("content") or "")) > len((old.get("content") or "")):
                    deduped[key] = item
            else:
                deduped[key] = item

        ranked = sorted(
            deduped.values(),
            key=lambda x: self._result_score(x, paragraph_title, paragraph_content),
            reverse=True,
        )
        return ranked[: max(1, self.settings.max_results)]

    def _result_key(self, item: Dict[str, str]) -> str:
        url = (item.get("url") or "").strip().lower()
        if url:
            return f"url:{url}"
        title = re.sub(r"\s+", " ", (item.get("title") or "").strip().lower())
        return f"title:{title}"

    def _result_score(self, item: Dict[str, str], paragraph_title: str, paragraph_content: str) -> float:
        title = (item.get("title") or "").lower()
        content = (item.get("content") or "").lower()
        text = f"{title} {content}"

        terms = self._extract_terms(f"{paragraph_title} {paragraph_content}")
        overlap = sum(1 for term in terms if term in text)

        source_boost = 0.0
        host = self._extract_host(item.get("url") or "")
        if any(hint in host for hint in _PRIORITY_SOURCE_HOSTS):
            source_boost = 2.0

        recency_boost = 0.0
        current_year = datetime.utcnow().year
        if str(current_year) in text:
            recency_boost += 1.0
        if str(current_year - 1) in text:
            recency_boost += 0.4

        return float(overlap) + source_boost + recency_boost

    def _extract_terms(self, text: str) -> List[str]:
        raw = re.findall(r"[a-zA-Z0-9_-]{4,}", text.lower())
        seen = set()
        terms: List[str] = []
        for token in raw:
            if token in seen:
                continue
            seen.add(token)
            terms.append(token)
        return terms[:30]

    def _extract_host(self, url: str) -> str:
        try:
            return (urlparse(url).hostname or "").lower()
        except Exception:
            return ""

    def _detect_year_range(self, results: List[Dict[str, str]]):
        years: List[int] = []
        for item in results:
            blob = f"{item.get('title', '')} {item.get('content', '')}"
            for token in re.findall(r"\b20\d{2}\b", blob):
                try:
                    year = int(token)
                except ValueError:
                    continue
                if 2000 <= year <= 2100:
                    years.append(year)
        if not years:
            return None
        return (min(years), max(years))
