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
    "company_analysis": (
        "Build an outline focused on:\n"
        "(a) Strategic context and why the company matters now.\n"
        "(b) Product, business model, and monetization signals.\n"
        "(c) Competitive position, distribution, and execution leverage.\n"
        "(d) Risks, counter-evidence, and unresolved watchpoints."
    ),
    "policy_analysis": (
        "Build an outline focused on:\n"
        "(a) Policy summary and scope - what changed, who is covered, and where the boundaries sit.\n"
        "(b) Enforcement, stakeholders, and implementation path - how the rule will be executed in practice.\n"
        "(c) Practical impact and compliance actions - what teams need to change immediately.\n"
        "(d) Risks, opposition, and second-order effects - unintended consequences, resistance, and unresolved ambiguities."
    ),
    "claim_audit": (
        "Build an outline focused on:\n"
        "(a) Official status check - verify whether the claim is real using official or first-hand evidence.\n"
        "(b) Where the claim came from - rumor origin, confusion source, or misinterpretation path.\n"
        "(c) What is actually true now - the real current product, API, policy, or timeline facts.\n"
        "(d) Practical takeaways - what a user should do after the claim is corrected."
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
    "company_analysis": [
        {"title": "Strategic Context", "content": "Why the company matters now and which external forces shape the analysis."},
        {"title": "Product, Revenue, and Operating Model", "content": "What the company sells, how it monetizes, and what operating signals matter most."},
        {"title": "Competitive Position and Execution", "content": "Relative advantages, distribution, partners, and execution leverage."},
        {"title": "Risks, Counter-Evidence, and Watchpoints", "content": "What could break the thesis, which criticisms matter, and what to monitor next."},
    ],
    "policy_analysis": [
        {"title": "Policy Summary and Scope", "content": "What the policy says, what changed, and who is covered."},
        {"title": "Enforcement and Stakeholders", "content": "Who enforces it, who is affected, and how implementation will work."},
        {"title": "Practical Impact and Compliance Actions", "content": "Concrete operational changes required for affected teams."},
        {"title": "Risks, Opposition, and Open Questions", "content": "Unintended consequences, criticism, and unresolved ambiguities."},
    ],
    "claim_audit": [
        {
            "title": "Official Status Check",
            "content": "Verify whether the named version, event, or claim is real in official channels.",
        },
        {
            "title": "Where The Claim Came From",
            "content": "Trace rumor origin, naming confusion, or secondary-source amplification.",
        },
        {
            "title": "What Is Actually True Now",
            "content": "Summarize the real current facts, releases, or timeline that users should rely on instead.",
        },
        {
            "title": "Practical Takeaways",
            "content": "Translate the corrected understanding into immediate user or builder actions.",
        },
    ],
}


def section_word_budget(length_preset: str, sections: int) -> int:
    normalized = (length_preset or "").strip().lower() or "long"
    total_budget = {
        "short": 900,
        "medium": 1400,
        "long": 1900,
    }.get(normalized, 1900)
    safe_sections = max(1, sections)
    return max(220, int(total_budget / safe_sections))


def default_section_contract(template_key: str, length_preset: str = "long") -> List[Dict[str, object]]:
    defaults = default_outline_for_template(template_key)
    target_words = section_word_budget(length_preset, len(defaults))
    contracts: List[Dict[str, object]] = []
    for item in defaults:
        lowered_title = str(item.get("title") or "").lower()
        evidence_type = "mixed"
        if "risk" in lowered_title or "criticism" in lowered_title or "watchpoint" in lowered_title:
            evidence_type = "contrarian"
        elif "policy" in lowered_title or "enforcement" in lowered_title or "compliance" in lowered_title:
            evidence_type = "official"
        elif "official status" in lowered_title or "actually true" in lowered_title:
            evidence_type = "official"
        elif "claim came from" in lowered_title:
            evidence_type = "contrarian"
        elif "product" in lowered_title or "revenue" in lowered_title or "competitive" in lowered_title:
            evidence_type = "market"
        contracts.append(
            {
                "title": item["title"],
                "content": item["content"],
                "evidence_type": evidence_type,
                "target_words": target_words,
                "pass_criteria": "Cite credible evidence, surface contradictions, and avoid unsupported claims.",
                "subquestions": [],
            }
        )
    return contracts


def report_structure_prompt(template_key: str) -> str:
    instructions = _REPORT_STRUCTURE_TEMPLATE_INSTRUCTIONS.get(
        template_key,
        _REPORT_STRUCTURE_TEMPLATE_INSTRUCTIONS["industry_brief"],
    )
    return (
        "You are a research planner operating as a senior intelligence analyst.\n"
        f"Template mode: {template_key}.\n"
        f"{instructions}\n"
        "Return JSON with this shape:\n"
        '{'
        '"report_type":"...",'
        '"sections":[{"title":"","content":"","evidence_type":"mixed|market|official|contrarian","target_words":260,"pass_criteria":"","subquestions":["..."]}]}'
        "\n"
        "Use 4-6 sections. Keep target_words realistic for a long-form analytical report."
        "\n"
        "Only output valid JSON."
    )


PREMISE_CHECK_PROMPT = """
You are a premise validation analyst.
Before full research begins, determine whether the user's query contains a factual premise
that should be validated first.

Classify as:
- valid: premise is plausible and can proceed as written
- disputed: premise is not clearly established and must be checked first
- invalid: premise is directly contradicted by official or first-hand evidence

If disputed or invalid:
- rewrite the query into a safer research objective that first verifies the claim
- recommend report_type = claim_audit
- propose 2-4 official queries that should be searched first

Return JSON:
{
  "premise_status": "valid|disputed|invalid",
  "reframed_query": "...",
  "recommended_report_type": "claim_audit|industry_brief|company_analysis|person_profile|policy_analysis|",
  "validation_notes": "...",
  "official_queries": ["...", "..."]
}
Only output valid JSON.
"""


def default_outline_for_template(template_key: str) -> List[Dict[str, str]]:
    defaults = _REPORT_STRUCTURE_DEFAULTS.get(template_key, _REPORT_STRUCTURE_DEFAULTS["industry_brief"])
    return [dict(item) for item in defaults]


FIRST_SEARCH_PROMPT = """
You are a research retrieval strategist trained in OSINT methodology.
Generate a search query package, not a single broad query.
Hard requirements:
1) Include one query anchored to the most recent 90 days.
2) Prioritize first-hand or official sources when available: official statements, docs,
   filings, transcripts, GitHub repos/README, direct talks, podcasts/interviews, and company/policy primary materials.
3) Prioritize evidence that helps answer the section contract, not broad background filler.
4) Include a contrarian/skeptical query that seeks evidence AGAINST the prevailing narrative
   (failure reports, criticism, limitations, alternative approaches).
5) When the topic is a company, include at least one query for business model, product, revenue,
   competition, or investor/operator signals.
6) If report_type is claim_audit, the first search round must verify official status before expanding.
   Do not generate queries that assume an unverified version name, release, or rumor is true.
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
4) Keep the section focused; do not sprawl beyond the requested scope or target length.
5) For each section, include: key claims, what evidence supports them, and what remains unresolved.
6) If report_type is claim_audit, distinguish:
   - verified_facts
   - rejected_claims
   - supporting_evidence
   - counterevidence
   - unknowns
   Do not present adjacent true facts as if they prove the original false claim.
7) Never use these words: groundbreaking, revolutionary, game-changing, cutting-edge,
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
Format the final report in Markdown using the provided section contract in the exact order supplied.
Do not invent a new structure and do not rename section headers.

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
- If report_type is claim_audit, treat the corrected/reframed query as the report objective.
  Do not reintroduce the original false claim as if it were true.
- Never use these words: groundbreaking, revolutionary, game-changing, cutting-edge,
  paradigm shift, transformative, unprecedented.
- Do not output JSON.
Return plain Markdown only.
"""
