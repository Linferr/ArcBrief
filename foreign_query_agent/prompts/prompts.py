"""Prompt library for the foreign query agent."""

from datetime import datetime
from typing import Optional


_LANGUAGE_HINTS = {
    "English (US)": "Write all generated content in English (US).",
    "Chinese (Simplified)": "Write all generated content in Simplified Chinese.",
    "Japanese": "Write all generated content in Japanese.",
}


def language_instruction(language: Optional[str]) -> str:
    chosen = (language or "").strip()
    return _LANGUAGE_HINTS.get(chosen, _LANGUAGE_HINTS["English (US)"])


def recency_instruction(mode: Optional[str]) -> str:
    normalized = (mode or "").strip() or "recent_12m_with_90d_anchor"
    now = datetime.utcnow().strftime("%Y-%m-%d")
    if normalized == "recent_12m_with_90d_anchor":
        return (
            f"Recency mode: recent_12m_with_90d_anchor. Current date: {now}. "
            "At least one search query must target the last 90 days. "
            "Prefer evidence from the last 12 months unless the user asks for historical context."
        )
    return f"Recency mode: {normalized}. Current date: {now}."


REPORT_STRUCTURE_PROMPT = """
You are a research planner.
Build an outline focused on: (a) latest viewpoints, (b) actionable techniques/workflows,
(c) concrete tools/config templates, (d) risks and counterarguments.
Return a JSON array with items: {"title": "", "content": ""}
Only output valid JSON.
"""

FIRST_SEARCH_PROMPT = """
You are a research retrieval strategist.
Generate a search query package, not a single broad query.
Hard requirements:
1) Include one query anchored to the most recent 90 days.
2) Prioritize first-hand sources for technical figures: X/Twitter posts, GitHub repos/README,
   long-form blogs, podcasts/interviews, and direct talks.
3) Prioritize practical extraction: templates, config files, concrete workflows, toolchains,
   and specific action steps.
4) Inject modern AI workflow terms when relevant: Vibe Coding, Agentic Engineering, RLVR, Claws.
Return JSON:
{
  "search_queries": [
    {"intent": "latest_viewpoints", "query": "..."},
    {"intent": "actionable_tactics", "query": "..."},
    {"intent": "risks_counterpoints", "query": "..."}
  ],
  "search_tool": "basic_search",
  "reasoning": "..."
}
Only output valid JSON.
"""

REFLECTION_PROMPT = """
You are a critical research analyst.
Evaluate the current paragraph summary and decide if more search is needed.
Framework:
1) RECENCY GAP: does the summary miss updates from the most recent 90 days?
2) SOURCE GAP: are first-hand sources (X/GitHub/talks/podcasts) missing?
3) ACTIONABILITY GAP: does the output include concrete templates/workflows/tools?
4) COUNTEREVIDENCE GAP: are risks or opposing views missing?
Return JSON with an additional search package:
{
  "search_queries": [
    {"intent": "latest_gap", "query": "..."},
    {"intent": "source_gap", "query": "..."},
    {"intent": "actionability_gap", "query": "..."}
  ],
  "search_tool": "basic_search",
  "reasoning": "..."
}
If no more search is needed, return an empty list for search_queries.
Only output valid JSON.
"""

SUMMARY_PROMPT = """
You are a research writer.
Summarize search results into a dense and practical section.
Hard requirements:
1) Include concrete actions, templates, files, tools, or workflows where possible.
2) Avoid biography-style narration unless it directly supports practical conclusions.
3) Every key claim must include source anchors like [S1], [S2].
Return JSON: {"paragraph_latest_state": "..."}
Only output valid JSON.
"""

REFLECTION_SUMMARY_PROMPT = """
You are a research writer.
Improve the previous paragraph with new evidence.
Hard requirements:
1) Upgrade recency and practical specificity.
2) Add counterpoints/risks when present in evidence.
3) Keep source anchors like [S1], [S2].
Return JSON: {"updated_paragraph_latest_state": "..."}
Only output valid JSON.
"""

FORMAT_PROMPT = """
You are an editor.
Format the final report in Markdown with these sections in order:
1) Latest Viewpoints
2) Actionable Tactics
3) Toolchain and Config Templates
4) Risks and Counterexamples
5) Source-Cited Conclusions
Rules:
- Keep it practical and evidence-driven.
- Keep source anchors from paragraph content.
- Every major conclusion should have source anchors such as [S1] or [S2].
- If evidence is weak, explicitly write "Evidence insufficient" instead of making generic claims.
- Do not output JSON.
Return plain Markdown only.
"""
