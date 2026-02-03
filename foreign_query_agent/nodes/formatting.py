"""Formatting node."""

from typing import List, Dict
from .base import BaseNode
from ..prompts.prompts import FORMAT_PROMPT


class FormattingNode(BaseNode):
    def run(self, paragraphs: List[Dict[str, str]]) -> str:
        payload = "\n".join([f"## {p['title']}\n{p['content']}" for p in paragraphs])
        raw = self.llm.invoke(FORMAT_PROMPT, payload)
        if raw.strip().startswith("#"):
            return raw.strip()
        return "# Report\n\n" + raw.strip()

