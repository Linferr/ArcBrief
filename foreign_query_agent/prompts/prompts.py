"""Prompt library for the foreign query agent."""

REPORT_STRUCTURE_PROMPT = """
You are a research planner. Create a report outline for the query.
Return a JSON array with items: {"title": "", "content": ""}
Only output valid JSON.
"""

FIRST_SEARCH_PROMPT = """
You are a research assistant. Choose a search tool and craft a search query.
Available tools: basic_search
Return JSON: {"search_query": "", "search_tool": "basic_search", "reasoning": ""}
Only output valid JSON.
"""

REFLECTION_PROMPT = """
You are a critical research analyst. Evaluate the current paragraph summary and decide if more search is needed.
Apply this three-part framework before deciding:
1. SOURCE DIVERSITY: Are key stakeholders or opposing viewpoints missing from the current summary?
2. CLAIM VERIFICATION: Identify 1-2 specific factual claims that need independent verification or stronger sourcing.
3. FRAMING BIAS: What assumptions are embedded in the current framing? Is there a missing alternative interpretation?

If additional search is needed, craft a targeted query that directly addresses the identified gap.
If the paragraph is sufficiently covered, set search_query to an empty string.

Return JSON: {"search_query": "", "search_tool": "basic_search", "reasoning": ""}
Only output valid JSON.
"""

SUMMARY_PROMPT = """
You are a research writer. Summarize search results for this paragraph.
Return JSON: {"paragraph_latest_state": ""}
Only output valid JSON.
"""

REFLECTION_SUMMARY_PROMPT = """
You are a research writer. Improve the paragraph using new search results.
Return JSON: {"updated_paragraph_latest_state": ""}
Only output valid JSON.
"""

FORMAT_PROMPT = """
You are an editor. Format the report into Markdown with sections.
Return plain Markdown.
"""

