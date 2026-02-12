"""PDF export via WeasyPrint (Markdown -> HTML -> PDF).

References BettaFish pdf_renderer.py pattern.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Dict


def _prepare_pango_env() -> None:
    """Windows: detect GTK3-Runtime and add DLL directory for Pango/WeasyPrint."""
    if platform.system() != "Windows":
        return

    gtk_paths = [
        r"C:\Program Files\GTK3-Runtime Win64\bin",
        r"C:\msys64\mingw64\bin",
        os.path.expandvars(r"%LOCALAPPDATA%\gtk-runtime\bin"),
    ]

    for p in gtk_paths:
        if os.path.isdir(p):
            try:
                os.add_dll_directory(p)
            except (OSError, AttributeError):
                pass
            if p not in os.environ.get("PATH", ""):
                os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")
            break


_prepare_pango_env()

try:
    import markdown  # noqa: E402
    from weasyprint import HTML  # noqa: E402
    from weasyprint.text.fonts import FontConfiguration  # noqa: E402
    _HAS_WEASYPRINT = True
except ImportError:
    _HAS_WEASYPRINT = False


_PDF_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Merriweather:wght@400;700&family=JetBrains+Mono:wght@400&display=swap');

@page {
    size: A4;
    margin: 2.2cm 2cm 2.5cm 2cm;

    @top-left {
        content: "ArcBrief";
        font-family: 'Inter', sans-serif;
        font-size: 8pt;
        color: #1a365d;
        font-weight: 600;
    }
    @top-right {
        content: string(doc-date);
        font-family: 'Inter', sans-serif;
        font-size: 8pt;
        color: #666;
    }
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-family: 'Inter', sans-serif;
        font-size: 8pt;
        color: #999;
    }
}

body {
    font-family: 'Merriweather', 'Georgia', serif;
    font-size: 10.5pt;
    line-height: 1.65;
    color: #1a1a1a;
}

.pdf-header {
    border-bottom: 3px solid #1a365d;
    padding-bottom: 12pt;
    margin-bottom: 18pt;
}

.pdf-brand {
    font-family: 'Inter', sans-serif;
    font-size: 10pt;
    font-weight: 600;
    color: #1a365d;
    letter-spacing: 1.5pt;
    text-transform: uppercase;
    margin: 0 0 4pt 0;
}

.pdf-title {
    font-family: 'Merriweather', serif;
    font-size: 18pt;
    font-weight: 700;
    color: #1a1a1a;
    margin: 0 0 6pt 0;
    string-set: doc-date attr(data-date);
}

.pdf-meta {
    font-family: 'Inter', sans-serif;
    font-size: 8.5pt;
    color: #666;
    margin: 0;
}

h1 {
    font-family: 'Merriweather', serif;
    font-size: 16pt;
    font-weight: 700;
    color: #1a365d;
    margin-top: 18pt;
    margin-bottom: 8pt;
    page-break-after: avoid;
}

h2 {
    font-family: 'Merriweather', serif;
    font-size: 13pt;
    font-weight: 700;
    color: #2d4a7a;
    margin-top: 14pt;
    margin-bottom: 6pt;
    page-break-after: avoid;
}

h3 {
    font-family: 'Inter', sans-serif;
    font-size: 11pt;
    font-weight: 600;
    color: #333;
    margin-top: 10pt;
    margin-bottom: 4pt;
}

p {
    margin: 0 0 8pt 0;
    orphans: 3;
    widows: 3;
}

ul, ol {
    margin: 4pt 0 8pt 0;
    padding-left: 18pt;
}

li {
    margin-bottom: 3pt;
}

blockquote {
    border-left: 3px solid #d4a853;
    padding-left: 12pt;
    margin: 8pt 0;
    color: #555;
    font-size: 9.5pt;
    font-family: 'Inter', sans-serif;
}

code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9pt;
    background: #f5f0e8;
    padding: 1pt 3pt;
    border-radius: 2pt;
}

hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 14pt 0;
}

strong {
    font-weight: 700;
}

a {
    color: #1a365d;
    text-decoration: none;
}
"""


def _md_to_html(md_text: str, title: str, meta: Dict[str, str]) -> str:
    """Convert Markdown to a full HTML document with PDF-friendly styling."""
    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc"],
        output_format="html5",
    )

    date_str = meta.get("date", "")
    item_count = meta.get("item_count", "")
    meta_parts = [p for p in [date_str, f"{item_count} articles" if item_count else ""] if p]
    meta_line = " | ".join(meta_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>{_PDF_CSS}</style>
</head>
<body>
<div class="pdf-header">
  <p class="pdf-brand">ArcBrief</p>
  <h1 class="pdf-title" data-date="{date_str}">{title}</h1>
  <p class="pdf-meta">{meta_line}</p>
</div>
{html_body}
</body>
</html>"""


def _strip_markdown_for_pdf(md_text: str) -> str:
    """Convert markdown to readable plain text for fallback PDF mode."""
    text = md_text.replace("\r\n", "\n")
    text = text.replace("```", "")
    text = text.replace("**", "")
    text = text.replace("__", "")
    text = text.replace("`", "")
    text = text.replace("### ", "")
    text = text.replace("## ", "")
    text = text.replace("# ", "")
    return text.strip()


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_lines(text: str, max_chars: int = 92) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        p = paragraph.strip()
        if not p:
            lines.append("")
            continue
        while len(p) > max_chars:
            split_at = p.rfind(" ", 0, max_chars)
            if split_at <= 0:
                split_at = max_chars
            lines.append(p[:split_at].rstrip())
            p = p[split_at:].lstrip()
        lines.append(p)
    return lines


def _render_basic_pdf(md_text: str, title: str, meta: Dict[str, str]) -> bytes:
    """Dependency-free PDF fallback using built-in PDF primitives."""
    date_line = meta.get("date", "")
    body_lines = [f"ArcBrief - {title}", date_line, ""] + _wrap_lines(_strip_markdown_for_pdf(md_text))
    lines_per_page = 48
    pages = [body_lines[i : i + lines_per_page] for i in range(0, len(body_lines), lines_per_page)] or [[]]

    objects: list[bytes] = []
    # 1: Catalog (references pages object 2)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")

    # Placeholder for pages object index 2, fill later.
    objects.append(b"<< /Type /Pages /Kids [] /Count 0 >>")

    page_obj_ids: list[int] = []
    content_obj_ids: list[int] = []

    # Reserve page/content objects.
    for _ in pages:
        page_obj_ids.append(len(objects) + 1)
        objects.append(b"")
        content_obj_ids.append(len(objects) + 1)
        objects.append(b"")

    font_obj_id = len(objects) + 1
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for idx, page_lines in enumerate(pages):
        content_parts = ["BT", "/F1 11 Tf", "50 790 Td", "14 TL"]
        for line in page_lines:
            escaped = _escape_pdf_text(line)
            content_parts.append(f"({escaped}) Tj")
            content_parts.append("T*")
        content_parts.append("ET")
        stream = "\n".join(content_parts).encode("latin-1", errors="replace")
        content_obj = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )
        objects[content_obj_ids[idx] - 1] = content_obj

        page_obj = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_obj_id} 0 R >> >> "
            f"/Contents {content_obj_ids[idx]} 0 R >>"
        ).encode("ascii")
        objects[page_obj_ids[idx] - 1] = page_obj

    kids = " ".join(f"{obj_id} 0 R" for obj_id in page_obj_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_obj_ids)} >>".encode("ascii")

    # Build PDF body and xref.
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    out.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(out)


def render_pdf(md_text: str, title: str, meta: Dict[str, str]) -> bytes:
    """Render Markdown content to PDF bytes via WeasyPrint.

    Args:
        md_text: Markdown source text.
        title: Document title shown in header.
        meta: Dict with optional keys: date, item_count, run_id.

    Returns:
        PDF file content as bytes.

    Raises:
        RuntimeError: If weasyprint/markdown are not installed.
    """
    if not _HAS_WEASYPRINT:
        return _render_basic_pdf(md_text, title, meta)
    html_str = _md_to_html(md_text, title, meta)
    font_config = FontConfiguration()
    return HTML(
        string=html_str,
        base_url=str(Path.cwd()),
    ).write_pdf(
        font_config=font_config,
        presentational_hints=True,
    )
