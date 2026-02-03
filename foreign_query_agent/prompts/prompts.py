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
You are a research assistant. Reflect on the current paragraph summary and decide if more search is needed.
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

