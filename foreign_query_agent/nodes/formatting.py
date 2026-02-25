"""Formatting node."""

from typing import Dict, List

from .base import BaseNode
from ..prompts.prompts import FORMAT_PROMPT, language_instruction


def _required_sections(language: str) -> List[str]:
    if language == "Chinese (Simplified)":
        return ["最新观点", "实操技巧", "工具链与配置模板", "风险与反例", "来源"]
    if language == "Japanese":
        return ["最新の見解", "実践テクニック", "ツールチェーンと設定テンプレート", "リスクと反例", "ソース"]
    return [
        "Latest Viewpoints",
        "Actionable Tactics",
        "Toolchain and Config Templates",
        "Risks and Counterexamples",
        "Sources",
    ]


def _ensure_sections(report: str, language: str) -> str:
    text = (report or "").strip()
    if not text.startswith("#"):
        text = "# Report\n\n" + text
    for section in _required_sections(language):
        if f"## {section}" not in text:
            text += f"\n\n## {section}\n- Evidence insufficient."
    return text.strip()


class FormattingNode(BaseNode):
    def run(self, paragraphs: List[Dict[str, str]], language: str = "English (US)") -> str:
        payload = "\n".join([f"## {p['title']}\n{p['content']}" for p in paragraphs])
        system_prompt = f"{FORMAT_PROMPT}\n{language_instruction(language)}"
        raw = self.llm.invoke(system_prompt, payload)
        return _ensure_sections(raw, language)