"""Small helpers for Discord bot API error handling."""

from __future__ import annotations

import json
from typing import Any


def build_api_error_message(method: str, path: str, status: int, body_text: str) -> str:
    detail = ""
    raw = (body_text or "").strip()
    if raw:
        try:
            parsed: Any = json.loads(raw)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            detail = str(parsed.get("message") or parsed.get("detail") or parsed.get("error_code") or "").strip()
        if not detail:
            detail = raw[:220]
    suffix = f": {detail}" if detail else ""
    return f"{method} {path} failed: {status}{suffix}"
