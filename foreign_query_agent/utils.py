"""Utility helpers for JSON cleanup."""

import json
import re
from typing import Any, Dict


def clean_json_tags(text: str) -> str:
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    text = re.sub(r"```", "", text)
    return text.strip()


def remove_reasoning(text: str) -> str:
    # Trim to first JSON token
    for i, ch in enumerate(text):
        if ch in "[{":
            return text[i:].strip()
    return text.strip()


def parse_json_fallback(text: str, default: Any) -> Any:
    cleaned = clean_json_tags(remove_reasoning(text))
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # try extract object
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        # try array
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return default


def ensure_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def slugify(text: str, max_len: int = 48) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\\s_-]", "", text).strip().lower()
    cleaned = re.sub(r"[\\s_-]+", "-", cleaned)
    if not cleaned:
        return "query"
    return cleaned[:max_len]

