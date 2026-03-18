"""Prompt library for the foreign query agent."""

from datetime import datetime
from typing import Dict, List, Optional


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


_REPORT_STRUCTURE_TEMPLATE_INSTRUCTIONS: Dict[str, str] = {
    "industry_brief": (
        "Build an outline focused on:\n"
        "(a) Latest viewpoints - what has changed in the last 90 days and why it matters.\n"
        "(b) Actionable techniques/workflows - concrete steps a practitioner can execute today.\n"
        "(c) Concrete tools/config templates - specific repos, config files, CLI commands, or API calls.\n"
        "(d) Risks and contrarian views - opposing evidence, failure modes, and second-order consequences."
    ),
    "person_profile": (
        "Build an outline focused on:\n"
        "(a) Current role and strategic relevance - why this person matters now.\n"
        "(b) Recent moves, statements, and initiatives - what changed recently and how the person is positioning.\n"
        "(c) Operating style, network, and leverage - recurring patterns in decision-making, alliances, and influence.\n"
        "(d) Risks, criticism, and open questions - opposing views, blind spots, and unresolved concerns."
    ),
    "policy_analysis": (
        "Build an outline focused on:\n"
        "(a) Policy summary and scope - what changed, who is covered, and where the boundaries sit.\n"
        "(b) Enforcement, stakeholders, and implementation path - how the rule will be executed in practice.\n"
        "(c) Practical impact and compliance actions - what teams need to change immediately.\n"
        "(d) Risks, opposition, and second-order effects - unintended consequences, resistance, and unresolved ambiguities."
    ),
}


_REPORT_STRUCTURE_DEFAULTS: Dict[str, List[Dict[str, str]]] = {
    "industry_brief": [
        {"title": "Latest Viewpoints", "content": "What changed recently and why it matters."},
        {"title": "Actionable Tactics", "content": "Concrete steps, workflows, or operating tactics."},
        {"title": "Toolchain and Config Templates", "content": "Specific tools, files, settings, or commands to inspect."},
        {"title": "Risks & Contrarian Views", "content": "Opposing evidence, failure modes, and second-order effects."},
    ],
    "person_profile": [
        {"title": "Current Role and Strategic Relevance", "content": "Why this person matters now and what decisions they influence."},
        {"title": "Recent Moves and Public Signals", "content": "Recent statements, launches, alliances, or strategic shifts."},
        {"title": "Operating Style and Influence Network", "content": "Patterns in execution, allies, detractors, and leverage points."},
        {"title": "Risks, Criticism, and Open Questions", "content": "Credible criticism, reputational risk, and unresolved uncertainties."},
    ],
    "policy_analysis": [
        {"title": "Policy Summary and Scope", "content": "What the policy says, what changed, and who is covered."},
        {"title": "Enforcement and Stakeholders", "content": "Who enforces it, who is affected, and how implementation will work."},
        {"title": "Practical Impact and Compliance Actions", "content": "Concrete operational changes required for affected teams."},
        {"title": "Risks, Opposition, and Open Questions", "content": "Unintended consequences, criticism, and unresolved ambiguities."},
    ],
}


def report_structure_prompt(template_key: str) -> str:
    instructions = _REPORT_STRUCTURE_TEMPLATE_INSTRUCTIONS.get(
        template_key,
        _REPORT_STRUCTURE_TEMPLATE_INSTRUCTIONS["industry_brief"],
    )
    return (
        "You are a research planner operating as a senior intelligence analyst.\n"
        f"Template mode: {template_key}.\n"
        f"{instructions}\n"
        'Return a JSON array with items: {"title": "", "content": ""}\n'
        "Only output valid JSON."
    )


def default_outline_for_template(template_key: str) -> List[Dict[str, str]]:
    defaults = _REPORT_STRUCTURE_DEFAULTS.get(template_key, _REPORT_STRUCTURE_DEFAULTS["industry_brief"])
    return [dict(item) for item in defaults]


FIRST_SEARCH_PROMPT = """
You are a research retrieval strategist trained in OSINT methodology.
Generate a search query package, not a single broad query.
Hard requirements:
1) Include one query anchored to the most recent 90 days.
2) Prioritize first-hand sources: X/Twitter posts, GitHub repos/README,
   long-form blogs, podcasts/interviews, direct talks, and official documentation.
3) Prioritize practical extraction: templates, config files, concrete workflows, toolchains,
   and specific action steps.
4) Include a contrarian/skeptical query that seeks evidence AGAINST the prevailing narrative
   (failure reports, criticism, limitations, alternative approaches).
5) Inject modern AI workflow terms when relevant: Vibe Coding, Agentic Engineering, RLVR, Claws.
Return JSON:
{
  "search_queries": [
    {"intent": "latest_viewpoints", "query": "..."},
    {"intent": "actionable_tactics", "query": "..."},
    {"intent": "risks_counterpoints", "query": "..."},
    {"intent": "contrarian_evidence", "query": "..."}
  ],
  "search_tool": "basic_search",
  "reasoning": "..."
}
Only output valid JSON.
"""


REFLECTION_PROMPT = """
You are a critical research analyst performing gap analysis.
Evaluate the current paragraph summary and decide if more search is needed.
Framework - check each gap type:
1) RECENCY GAP: does the summary miss updates from the most recent 90 days?
2) SOURCE GAP: are first-hand sources (X/GitHub/talks/podcasts) missing?
3) ACTIONABILITY GAP: does the output include concrete templates/workflows/tools?
4) COUNTEREVIDENCE GAP: are risks or opposing views missing?
5) CONFIDENCE GAP: are any claims stated with high certainty but backed by only one source?
   If so, seek corroboration or conflicting evidence.
6) CONTRADICTION GAP: do any sources conflict with each other? If so, seek a third source
   to help resolve the disagreement.
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
You are a senior research analyst writing an intelligence brief.
Summarize search results into a dense, analytical section.

Analysis framework:
- FIRST PRINCIPLES: identify root causes and structural drivers, not just surface events.
- CROSS-VERIFICATION: when multiple sources cover the same claim, note agreement or divergence.
  If sources conflict, write: "Sources diverge: [S1] asserts X while [S2] argues Y."
- STAKEHOLDER LENS: note who benefits and who is disadvantaged by the developments described.
- CONFIDENCE CALIBRATION: for significant claims backed by only one source, add [LOW CONFIDENCE].
  For claims backed by 3+ independent sources, add [HIGH CONFIDENCE].

Hard requirements:
1) Include concrete actions, templates, files, tools, or workflows where possible.
2) Avoid biography-style narration unless it directly supports practical conclusions.
3) Every key claim must include source anchors like [S1], [S2].
4) Never use these words: groundbreaking, revolutionary, game-changing, cutting-edge,
   paradigm shift, transformative, unprecedented. Use precise, measured language instead.

Tone: academic analyst - precise, evidence-driven, measured. Prefer "X indicates" over "X is amazing."
Return JSON: {"paragraph_latest_state": "..."}
Only output valid JSON.
"""


REFLECTION_SUMMARY_PROMPT = """
You are a senior research analyst refining an intelligence brief with new evidence.
Improve the previous paragraph by integrating new search results.

Hard requirements:
1) Upgrade recency and practical specificity with the new evidence.
2) Add counterpoints/risks when present in evidence.
3) RESOLVE CONTRADICTIONS: if the new evidence contradicts the existing summary,
   present both positions with their respective sources rather than silently replacing.
4) CALIBRATE CONFIDENCE: upgrade claims from [LOW CONFIDENCE] to [MEDIUM/HIGH CONFIDENCE]
   if the new evidence corroborates them, or downgrade if it contradicts.
5) Keep source anchors like [S1], [S2].
6) Never use these words: groundbreaking, revolutionary, game-changing, cutting-edge,
   paradigm shift, transformative, unprecedented.

Tone: academic analyst - precise, evidence-driven, measured.
Return JSON: {"updated_paragraph_latest_state": "..."}
Only output valid JSON.
"""


FORMAT_PROMPT = """
You are a senior editor producing an intelligence-grade research report.
Format the final report in Markdown with these sections in order:
1) Latest Viewpoints
2) Actionable Tactics
3) Toolchain and Config Templates
4) Risks & Contrarian Views

Output ONLY the four sections listed above. Do not add any additional sections.

Structural formatting rules:
- Use bullet point lists for each distinct piece of evidence or claim.
- **Bold** key terms (entity names, technologies, organizations) on first mention.
- Maximum 2-3 sentences per paragraph, then switch to a bulleted list.
- Use ### subsection headers within large sections to group related topics
  (e.g. "### Specific Technology" under "## Latest Viewpoints").
- For code, config, or CLI content in "Toolchain and Config Templates", use fenced code blocks.

Content rules:
- Tone: academic analyst - precise, evidence-driven, measured.
- Keep source anchors from paragraph content (e.g. [S1], [S2]).
- For significant claims, include a confidence marker: [HIGH CONFIDENCE], [MEDIUM CONFIDENCE],
  or [LOW CONFIDENCE] based on the number and quality of supporting sources.
- When sources conflict, present both positions explicitly:
  "[S1] asserts X, while [S2] argues Y."
- If evidence is weak, explicitly write "Evidence insufficient" instead of making generic claims.
- Never use these words: groundbreaking, revolutionary, game-changing, cutting-edge,
  paradigm shift, transformative, unprecedented.
- Do not output JSON.
Return plain Markdown only.
"""
