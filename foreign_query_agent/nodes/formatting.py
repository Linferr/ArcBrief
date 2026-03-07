"""Formatting node."""

from typing import Dict, List

from .base import BaseNode
from ..prompts.prompts import FORMAT_PROMPT, language_instruction


def _required_sections(language: str) -> List[str]:
    """Sections that _ensure_sections will force-add if missing.

    NOTE: "Sources" is intentionally excluded — it is appended by
    agent._append_sources_from_map() which builds the real source list
    from the global source map.  Including it here would create a
    duplicate "## Sources" block.
    """
    if language == "Chinese (Simplified)":
        return ["最新观点", "实操技巧", "工具链与配置模板", "风险与反共识观点"]
    if language == "Japanese":
        return ["最新の見解", "実践テクニック", "ツールチェーンと設定テンプレート", "リスクと反論"]
    return [
        "Latest Viewpoints",
        "Actionable Tactics",
        "Toolchain and Config Templates",
        "Risks & Contrarian Views",
    ]


def _ensure_sections(report: str, language: str) -> str:
    """Ensure the report contains all required sections.

    Uses two guards to avoid duplicate sections:
    1. If 4+ ``## `` headers already exist, do not append any.
    2. Fuzzy containment check: a required section is considered present
       if its name (lowered) appears anywhere within an existing ``## `` line.
    """
    text = (report or "").strip()
    if not text.startswith("#"):
        text = "# Report\n\n" + text

    existing_h2 = [
        line.strip() for line in text.split("\n") if line.strip().startswith("## ")
    ]

    if len(existing_h2) >= 4:
        return text.strip()

    required = _required_sections(language)
    for section in required:
        found = any(section.lower() in h2.lower() for h2 in existing_h2)
        if not found:
            text += f"\n\n## {section}\n- Evidence insufficient."
    return text.strip()


class FormattingNode(BaseNode):
    def run(self, paragraphs: List[Dict[str, str]], language: str = "English (US)") -> str:
        payload = "\n".join([f"## {p['title']}\n{p['content']}" for p in paragraphs])
        system_prompt = f"{FORMAT_PROMPT}\n{language_instruction(language)}"
        raw = self.llm.invoke(system_prompt, payload)
        return _ensure_sections(raw, language)
