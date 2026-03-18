"""Main QueryAgent implementation."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .config import Settings
from .llm import LLMClient, LLMConfig, MockLLM
from .state import CriticResult, ParagraphState, ReportState, SearchItem
from .nodes.formatting import FormattingNode
from .nodes.host import HostNode
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
        self.search_node = SearchPlanNode(self.llm)
        self.summary_node = SummaryNode(self.llm)
        self.reflection_node = ReflectionNode(self.llm)
        self.reflection_summary_node = ReflectionSummaryNode(self.llm)
        self.formatting_node = FormattingNode(self.llm)
        self.host_node = HostNode(self.llm)

    def research(self, query: str, progress_cb=None, language: str = "English (US)") -> str:
        language_used = language if language in {"English (US)", "Chinese (Simplified)", "Japanese"} else "English (US)"
        state = ReportState(query=query)
        run_id = self._build_run_id(query)
        outline = self.structure_node.run(query, language=language_used)[: self.settings.max_paragraphs]
        if progress_cb:
            progress_cb({"stage": "outline", "message": "Outline generated", "run_id": run_id})

        for item in outline:
            paragraph = ParagraphState(title=item["title"], content=item["content"])
            state.paragraphs.append(paragraph)

        total_paragraphs = len(state.paragraphs)
        for idx, paragraph in enumerate(state.paragraphs):
            try:
                write_log("query", f"SearchPlan: {paragraph.title}", run_id=run_id)
                plan = self.search_node.run(
                    paragraph.title,
                    paragraph.content,
                    language=language_used,
                    recency_mode=self.settings.research_recency_mode,
                )
                queries = self._ensure_recency_query(
                    self._expand_query_pack(plan, fallback=f"{paragraph.title} latest {datetime.utcnow().year}"),
                    paragraph.title,
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
                    response = self.tool.search(search_query, max_results=self.settings.max_results)
                    batch = [r.__dict__ for r in response.results]
                    batches.append(batch)
                    for r in response.results:
                        paragraph.search_history.append(
                            SearchItem(query=search_query, title=r.title, url=r.url, content=r.content)
                        )

                ranked_results = self._merge_and_rank_results(paragraph.title, paragraph.content, batches)
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

                summary_text, summary_smap = self.summary_node.run(
                    paragraph.title,
                    paragraph.content,
                    " | ".join(queries),
                    ranked_results,
                    language=language_used,
                )
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
                    host_feedback = self.host_node.run(
                        paragraph.title,
                        paragraph.content,
                        paragraph.latest_summary,
                        language=language_used,
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
                    write_log(
                        "host",
                        f"Suggested search: {'; '.join(critic_result.suggested_queries)}",
                        run_id=run_id,
                    )
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

                    if critic_result.gate_decision == "PASS":
                        break

                    if critic_result.gate_decision == "REJECT":
                        final_report = self._build_gate_blocked_report(
                            query=state.query,
                            paragraph=paragraph,
                            critic_result=critic_result,
                            language=language_used,
                            exhausted=False,
                            state=state,
                        )
                        write_log("query", "Final report blocked by critic gate", run_id=run_id)
                        if progress_cb:
                            progress_cb(
                                {
                                    "stage": "final",
                                    "message": "Report blocked by critic gate",
                                    "run_id": run_id,
                                }
                            )
                        state.final_report = final_report
                        state.touch()
                        self.last_state = state
                        self.last_run_id = run_id
                        return final_report

                    if paragraph.reflection_count >= self.settings.max_reflections:
                        final_report = self._build_gate_blocked_report(
                            query=state.query,
                            paragraph=paragraph,
                            critic_result=critic_result,
                            language=language_used,
                            exhausted=True,
                            state=state,
                        )
                        write_log("query", "Final report blocked after max reflections", run_id=run_id)
                        if progress_cb:
                            progress_cb(
                                {
                                    "stage": "final",
                                    "message": "Report blocked after max reflections",
                                    "run_id": run_id,
                                }
                            )
                        state.final_report = final_report
                        state.touch()
                        self.last_state = state
                        self.last_run_id = run_id
                        return final_report

                    suggested_queries = list(critic_result.suggested_queries)
                    if suggested_queries:
                        queries = [q for q in suggested_queries[:3] if isinstance(q, str) and q.strip()]
                    else:
                        reflect = self.reflection_node.run(
                            paragraph.title,
                            paragraph.content,
                            paragraph.latest_summary,
                            language=language_used,
                            recency_mode=self.settings.research_recency_mode,
                        )
                        queries = self._expand_query_pack(
                            reflect,
                            fallback=f"{paragraph.title} updates {datetime.utcnow().year}",
                        )
                    queries = self._ensure_recency_query(queries, paragraph.title)

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
                        response = self.tool.search(query_text, max_results=self.settings.max_results)
                        batch = [r.__dict__ for r in response.results]
                        reflection_batches.append(batch)
                        for r in response.results:
                            paragraph.search_history.append(
                                SearchItem(query=query_text, title=r.title, url=r.url, content=r.content)
                            )

                    ranked_reflection_results = self._merge_and_rank_results(
                        paragraph.title,
                        paragraph.content,
                        reflection_batches,
                    )

                    refl_text, refl_smap = self.reflection_summary_node.run(
                        paragraph.title,
                        paragraph.content,
                        " | ".join(queries),
                        ranked_reflection_results,
                        paragraph.latest_summary,
                        language=language_used,
                    )
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
            except Exception as e:
                write_log("query", f"ERROR processing paragraph '{paragraph.title}': {e}", run_id=run_id)
                if progress_cb:
                    progress_cb(
                        {
                            "stage": "error",
                            "message": f"Skipped paragraph {idx + 1}: {str(e)[:50]}",
                            "paragraph": paragraph.title,
                            "paragraph_idx": idx + 1,
                            "total_paragraphs": total_paragraphs,
                            "run_id": run_id,
                        }
                    )
                paragraph.latest_summary = f"Evidence insufficient for this section due to processing error: {str(e)[:100]}"
                continue

        final_report = self.formatting_node.run(
            [{"title": p.title, "content": p.latest_summary} for p in state.paragraphs],
            language=language_used,
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
        state.touch()
        self.last_state = state
        self.last_run_id = run_id
        return final_report

    def research(self, query: str, progress_cb=None, language: str = "English (US)") -> str:
        language_used = language if language in {"English (US)", "Chinese (Simplified)", "Japanese"} else "English (US)"
        state = ReportState(query=query)
        run_id = self._build_run_id(query)
        planning_template = (
            self.structure_node.select_template(query)
            if hasattr(self.structure_node, "select_template")
            else "industry_brief"
        )
        state.planning_template = planning_template
        if hasattr(self.structure_node, "run_with_template"):
            outline = self.structure_node.run_with_template(
                query,
                template_key=planning_template,
                language=language_used,
            )[: self.settings.max_paragraphs]
        else:
            outline = self.structure_node.run(query, language=language_used)[: self.settings.max_paragraphs]
        if progress_cb:
            progress_cb(
                {
                    "stage": "outline",
                    "message": f"Outline generated ({planning_template})",
                    "run_id": run_id,
                }
            )

        for item in outline:
            state.paragraphs.append(ParagraphState(title=item["title"], content=item["content"]))

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
            state.touch()
            self.last_state = state
            self.last_run_id = run_id
            return final_report

        final_report = self.formatting_node.run(
            [{"title": paragraph.title, "content": paragraph.latest_summary} for paragraph in state.paragraphs],
            language=language_used,
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
                write_log("query", f"SearchPlan: {paragraph.title}", run_id=run_id)
                plan = self.search_node.run(
                    paragraph.title,
                    paragraph.content,
                    language=language_used,
                    recency_mode=self.settings.research_recency_mode,
                )
                queries = self._ensure_recency_query(
                    self._expand_query_pack(plan, fallback=f"{paragraph.title} latest {datetime.utcnow().year}"),
                    paragraph.title,
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
                    batches.append([result.__dict__ for result in response.results])
                    for result in response.results:
                        paragraph.search_history.append(
                            SearchItem(query=search_query, title=result.title, url=result.url, content=result.content)
                        )

                ranked_results = self._merge_and_rank_results(paragraph.title, paragraph.content, batches)
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

                summary_text, summary_smap = self.summary_node.run(
                    paragraph.title,
                    paragraph.content,
                    " | ".join(queries),
                    ranked_results,
                    language=language_used,
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
                    host_feedback = self.host_node.run(
                        paragraph.title,
                        paragraph.content,
                        paragraph.latest_summary,
                        language=language_used,
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
                        reflect = self.reflection_node.run(
                            paragraph.title,
                            paragraph.content,
                            paragraph.latest_summary,
                            language=language_used,
                            recency_mode=self.settings.research_recency_mode,
                        )
                        queries = self._expand_query_pack(
                            reflect,
                            fallback=f"{paragraph.title} updates {datetime.utcnow().year}",
                        )
                    queries = self._ensure_recency_query(queries, paragraph.title)

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
                        reflection_batches.append([result.__dict__ for result in response.results])
                        for result in response.results:
                            paragraph.search_history.append(
                                SearchItem(query=query_text, title=result.title, url=result.url, content=result.content)
                            )

                    ranked_reflection_results = self._merge_and_rank_results(
                        paragraph.title,
                        paragraph.content,
                        reflection_batches,
                    )
                    refl_text, refl_smap = self.reflection_summary_node.run(
                        paragraph.title,
                        paragraph.content,
                        " | ".join(queries),
                        ranked_reflection_results,
                        paragraph.latest_summary,
                        language=language_used,
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
                entry = f"- [{sid}] {title}"
                if url:
                    entry += f" -- {url}"
                lines.append(entry)
        else:
            lines.append(empty_line)
        return report.rstrip() + "\n" + "\n".join(lines).rstrip() + "\n"

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
        lines.extend(["", "## Current Best-Effort Summary", summary, "", "## Suggested Follow-up Queries"])
        for suggestion in critic_result.suggested_queries or ["Collect additional primary sources before re-running."]:
            lines.append(f"- {suggestion}")
        report = "\n".join(lines).strip()
        report = self._strip_stale_sources(report)
        report = self._strip_orphan_refs(report, state.global_source_map)
        state.delivery_status = "limited"
        state.gate_decision = critic_result.gate_decision
        state.blocking_issues = list(critic_result.blocking_issues)
        return self._append_sources_from_map(report, state.global_source_map, language)

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

    def _ensure_recency_query(self, queries: List[str], title: str) -> List[str]:
        cleaned = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
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
