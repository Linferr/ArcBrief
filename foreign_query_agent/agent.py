"""Main QueryAgent implementation."""

import os
from datetime import datetime
from typing import List, Dict

from .config import Settings
from .llm import LLMClient, LLMConfig, MockLLM
from .state import ReportState, ParagraphState, SearchItem
from .nodes.report_structure import ReportStructureNode
from .nodes.search_plan import SearchPlanNode
from .nodes.summary import SummaryNode, ReflectionSummaryNode
from .nodes.reflection import ReflectionNode
from .nodes.formatting import FormattingNode
from .nodes.host import HostNode
from .logger import write_log
from .utils import slugify
from .tools.tavily_tool import TavilySearchTool
from .tools.mock_tool import MockSearchTool


class QueryAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_state = None
        if settings.mock_mode:
            self.llm = MockLLM()
            self.tool = MockSearchTool()
        else:
            llm_config = LLMConfig(
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                base_url=settings.llm_base_url,
            )
            self.llm = LLMClient(llm_config)
            self.tool = TavilySearchTool(api_key=settings.tavily_api_key)

        self.structure_node = ReportStructureNode(self.llm)
        self.search_node = SearchPlanNode(self.llm)
        self.summary_node = SummaryNode(self.llm)
        self.reflection_node = ReflectionNode(self.llm)
        self.reflection_summary_node = ReflectionSummaryNode(self.llm)
        self.formatting_node = FormattingNode(self.llm)
        self.host_node = HostNode(self.llm)

    def research(self, query: str, progress_cb=None) -> str:
        state = ReportState(query=query)
        run_id = self._build_run_id(query)
        outline = self.structure_node.run(query)[: self.settings.max_paragraphs]
        if progress_cb:
            progress_cb({"stage": "outline", "message": "Outline generated", "run_id": run_id})

        for item in outline:
            paragraph = ParagraphState(title=item["title"], content=item["content"])
            state.paragraphs.append(paragraph)

        total_paragraphs = len(state.paragraphs)
        for idx, paragraph in enumerate(state.paragraphs):
          try:
            write_log("query", f"SearchPlan: {paragraph.title}", run_id=run_id)
            plan = self.search_node.run(paragraph.title, paragraph.content)
            write_log("query", f"Search: {plan['search_query']}", run_id=run_id)
            if progress_cb:
                progress_cb({
                    "stage": "search",
                    "message": f"Search: {plan['search_query']}",
                    "paragraph": paragraph.title,
                    "paragraph_idx": idx + 1,
                    "total_paragraphs": total_paragraphs,
                    "run_id": run_id,
                })
            response = self.tool.search(plan["search_query"], max_results=self.settings.max_results)
            for r in response.results:
                paragraph.search_history.append(
                    SearchItem(query=response.query, title=r.title, url=r.url, content=r.content)
                )
            paragraph.latest_summary = self.summary_node.run(
                paragraph.title,
                paragraph.content,
                response.query,
                [r.__dict__ for r in response.results],
            )
            if paragraph.latest_summary:
                write_log("query", f"Summary round 1: {paragraph.latest_summary[:300]}...", run_id=run_id)
                if progress_cb:
                    progress_cb({
                        "stage": "summary",
                        "message": "Summary round 1 ready",
                        "paragraph": paragraph.title,
                        "paragraph_idx": idx + 1,
                        "total_paragraphs": total_paragraphs,
                        "round": 1,
                        "run_id": run_id,
                    })

            # host-guided reflection loop
            for _ in range(self.settings.max_reflections):
                host_feedback = self.host_node.run(
                    paragraph.title, paragraph.content, paragraph.latest_summary
                )
                paragraph.host_critiques.append(
                    {
                        "critique": host_feedback.get("critique", ""),
                        "questions": "; ".join(host_feedback.get("questions", [])),
                        "suggested_search": "; ".join(host_feedback.get("suggested_search_queries", [])),
                    }
                )
                write_log("host", f"Critique: {host_feedback.get('critique', '')}", run_id=run_id)
                write_log("host", f"Questions: {'; '.join(host_feedback.get('questions', []))}", run_id=run_id)
                write_log("host", f"Suggested search: {'; '.join(host_feedback.get('suggested_search_queries', []))}", run_id=run_id)
                if progress_cb:
                    progress_cb({
                        "stage": "host",
                        "message": host_feedback.get("critique", ""),
                        "paragraph": paragraph.title,
                        "paragraph_idx": idx + 1,
                        "total_paragraphs": total_paragraphs,
                        "round": paragraph.reflection_count + 1,
                        "run_id": run_id,
                    })
                suggested_queries = host_feedback.get("suggested_search_queries", [])

                # If host suggests queries, prefer them; otherwise use reflection node.
                if suggested_queries:
                    query_text = suggested_queries[0]
                    write_log("query", f"Reflection search: {query_text}", run_id=run_id)
                    if progress_cb:
                        progress_cb({
                            "stage": "reflection",
                            "message": f"Reflection search: {query_text}",
                            "paragraph": paragraph.title,
                            "paragraph_idx": idx + 1,
                            "total_paragraphs": total_paragraphs,
                            "round": paragraph.reflection_count + 1,
                            "run_id": run_id,
                        })
                    response = self.tool.search(query_text, max_results=self.settings.max_results)
                    paragraph.latest_summary = self.reflection_summary_node.run(
                        paragraph.title,
                        paragraph.content,
                        response.query,
                        [r.__dict__ for r in response.results],
                        paragraph.latest_summary,
                    )
                else:
                    reflect = self.reflection_node.run(
                        paragraph.title, paragraph.content, paragraph.latest_summary
                    )
                    write_log("query", f"Reflection search: {reflect['search_query']}", run_id=run_id)
                    if progress_cb:
                        progress_cb({
                            "stage": "reflection",
                            "message": f"Reflection search: {reflect['search_query']}",
                            "paragraph": paragraph.title,
                            "paragraph_idx": idx + 1,
                            "total_paragraphs": total_paragraphs,
                            "round": paragraph.reflection_count + 1,
                            "run_id": run_id,
                        })
                    response = self.tool.search(reflect["search_query"], max_results=self.settings.max_results)
                    paragraph.latest_summary = self.reflection_summary_node.run(
                        paragraph.title,
                        paragraph.content,
                        response.query,
                        [r.__dict__ for r in response.results],
                        paragraph.latest_summary,
                    )

                paragraph.reflection_count += 1
                if paragraph.latest_summary:
                    write_log(
                        "query",
                        f"Summary round {paragraph.reflection_count + 1}: {paragraph.latest_summary[:300]}...",
                        run_id=run_id,
                    )
                    if progress_cb:
                        progress_cb({
                            "stage": "summary",
                            "message": f"Summary round {paragraph.reflection_count + 1} ready",
                            "paragraph": paragraph.title,
                            "paragraph_idx": idx + 1,
                            "total_paragraphs": total_paragraphs,
                            "round": paragraph.reflection_count + 1,
                            "run_id": run_id,
                        })
          except Exception as e:
            # Log error and continue with next paragraph
            write_log("query", f"ERROR processing paragraph '{paragraph.title}': {e}", run_id=run_id)
            if progress_cb:
                progress_cb({
                    "stage": "error",
                    "message": f"跳过段落 {idx + 1}: {str(e)[:50]}",
                    "paragraph": paragraph.title,
                    "paragraph_idx": idx + 1,
                    "total_paragraphs": total_paragraphs,
                    "run_id": run_id,
                })
            paragraph.latest_summary = f"[处理失败: {str(e)[:100]}]"
            continue

        final_report = self.formatting_node.run(
            [{"title": p.title, "content": p.latest_summary} for p in state.paragraphs]
        )
        final_report = self._append_sources(final_report, state.paragraphs)
        write_log("query", "Final report generated", run_id=run_id)
        if progress_cb:
            progress_cb({"stage": "final", "message": "报告格式化完成", "run_id": run_id})
        state.final_report = final_report
        state.touch()
        self.last_state = state
        self.last_run_id = run_id
        return final_report

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

    def _append_sources(self, report: str, paragraphs: List[ParagraphState]) -> str:
        lines = ["", "## Sources", ""]
        seen = set()
        for paragraph in paragraphs:
            for item in paragraph.search_history:
                key = (item.title, item.url)
                if key in seen:
                    continue
                seen.add(key)
                title = item.title.strip() or "Untitled"
                url = item.url.strip() or ""
                if url:
                    lines.append(f"- {title} — {url}")
                else:
                    lines.append(f"- {title}")
        if len(lines) == 3:
            lines.append("- (no sources recorded)")
        return report.rstrip() + "\n" + "\n".join(lines).rstrip() + "\n"

