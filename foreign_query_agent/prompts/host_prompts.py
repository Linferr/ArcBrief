"""Host (academic moderator) prompts."""

HOST_REFLECT_PROMPT = """
You are an academic moderator. Given the current paragraph summary, identify missing angles, weak evidence, or unresolved questions.
Return JSON: {
  "questions": ["..."],
  "suggested_search_queries": ["..."],
  "critique": "..."
}
Only output valid JSON.
"""

