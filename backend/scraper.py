"""URL fetching and text extraction helpers for /api/tldr."""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import ipaddress
import re
from urllib.parse import urlparse

import requests


USER_AGENT = (
    "Mozilla/5.0 (compatible; ArcBriefTLDR/1.0; "
    "+https://arcbrief.local)"
)
MAX_HTML_CHARS = 2_000_000


@dataclass
class ScrapedDocument:
    url: str
    final_url: str
    title: str
    content: str
    source_domain: str


def validate_public_http_url(url: str) -> str:
    value = (url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be a public http/https URL.")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname or hostname == "localhost" or hostname.endswith(".local"):
        raise ValueError("URL must be a public http/https URL.")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return value

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise ValueError("URL must be a public http/https URL.")
    return value


def _extract_title(html: str, fallback: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if not match:
        return fallback
    title = _clean_text(match.group(1))
    return title or fallback


def _clean_text(text: str) -> str:
    value = unescape(text or "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _html_to_text(html: str) -> str:
    value = re.sub(r"(?is)<(script|style|noscript|svg).*?>.*?</\\1>", " ", html)
    value = re.sub(r"(?i)</(p|div|article|section|li|h1|h2|h3|h4|h5|h6|br)>", "\n", value)
    value = re.sub(r"(?is)<[^>]+>", " ", value)
    value = unescape(value)
    lines = [_clean_text(line) for line in value.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def fetch_tldr_document(url: str, timeout_seconds: int = 15) -> ScrapedDocument:
    safe_url = validate_public_http_url(url)
    response = requests.get(
        safe_url,
        timeout=timeout_seconds,
        headers={"User-Agent": USER_AGENT},
        allow_redirects=True,
    )
    response.raise_for_status()

    content_type = (response.headers.get("Content-Type") or "").lower()
    if content_type and not any(kind in content_type for kind in ("text/html", "text/plain", "application/xhtml+xml")):
        raise ValueError(f"Unsupported content type: {content_type}")

    html = response.text[:MAX_HTML_CHARS]
    final_url = response.url or safe_url
    source_domain = (urlparse(final_url).hostname or urlparse(safe_url).hostname or "").lower()
    title = _extract_title(html, source_domain or "Untitled page")
    content = _html_to_text(html)
    if len(content) < 120:
        raise ValueError("Fetched page did not contain enough readable body text.")

    return ScrapedDocument(
        url=safe_url,
        final_url=final_url,
        title=title,
        content=content,
        source_domain=source_domain,
    )
