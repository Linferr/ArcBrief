"""Offline regression diagnostics for Deep Research report quality."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence
from urllib.parse import urlparse


_PRIMARY_SOURCE_SUFFIXES: Sequence[str] = (
    "openai.com",
    "anthropic.com",
    "google.com",
    "googleblog.com",
    "deepmind.com",
    "meta.com",
    "microsoft.com",
    "github.com",
)

_DATE_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b"),
    re.compile(
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},\s*20\d{2}\b",
        flags=re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class CanonicalQueryCase:
    key: str
    query: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class ReportSignals:
    section_titles: List[str]
    section_count: int
    word_count: int
    source_count: int
    primary_source_count: int
    has_sources_section: bool
    has_risks_section: bool
    evidence_insufficient_mentions: int
    absolute_date_mentions: int


CANONICAL_QUERY_CASES: Dict[str, CanonicalQueryCase] = {
    "anthropic_recent": CanonicalQueryCase(
        key="anthropic_recent",
        query="anthropic最近发展与舆情",
        aliases=("anthropic", "anthropic_recent"),
    ),
    "chatgpt54_updates": CanonicalQueryCase(
        key="chatgpt54_updates",
        query="chatgpt5.4更新的特点以及优化",
        aliases=("chatgpt54", "chatgpt5.4", "chatgpt-5.4"),
    ),
    "openai_defense": CanonicalQueryCase(
        key="openai_defense",
        query="openai和美国国防部门合作进展",
        aliases=("openai", "dod", "defense"),
    ),
}


def _normalize_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _extract_unique_urls(report_content: str) -> List[str]:
    urls = re.findall(r"https?://[^\s)>\"]+", report_content or "")
    seen = set()
    ordered: List[str] = []
    for raw in urls:
        cleaned = raw.rstrip(".,;:")
        if cleaned not in seen:
            seen.add(cleaned)
            ordered.append(cleaned)
    return ordered


def _estimate_source_count(report_content: str) -> int:
    if not report_content:
        return 0

    lines = report_content.splitlines()
    in_sources = False
    source_lines: List[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^#{1,6}\s*sources?\b", line, flags=re.IGNORECASE):
            in_sources = True
            continue
        if in_sources and line.startswith("#"):
            break
        if in_sources and re.match(r"^(-|\*|\d+\.)\s+", line):
            source_lines.append(re.sub(r"^(-|\*|\d+\.)\s+", "", line).strip().lower())

    if source_lines:
        return len({s for s in source_lines if s})
    return len(_extract_unique_urls(report_content))


def _count_primary_sources(urls: Iterable[str]) -> int:
    domains = set()
    for url in urls:
        hostname = (urlparse(url).hostname or "").lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]
        if any(hostname.endswith(suffix) for suffix in _PRIMARY_SOURCE_SUFFIXES):
            domains.add(url)
    return len(domains)


def _count_absolute_dates(text: str) -> int:
    hits = 0
    for pattern in _DATE_PATTERNS:
        hits += len(pattern.findall(text or ""))
    return hits


def extract_report_signals(report_content: str) -> ReportSignals:
    section_titles = re.findall(r"^##\s+(.+?)\s*$", report_content or "", flags=re.MULTILINE)
    urls = _extract_unique_urls(report_content or "")
    lowered_titles = [title.lower() for title in section_titles]
    return ReportSignals(
        section_titles=section_titles,
        section_count=len(section_titles),
        word_count=len(re.findall(r"\S+", report_content or "")),
        source_count=_estimate_source_count(report_content or ""),
        primary_source_count=_count_primary_sources(urls),
        has_sources_section=any("sources" == title.strip().lower() for title in section_titles),
        has_risks_section=any("risk" in title or "contrarian" in title for title in lowered_titles),
        evidence_insufficient_mentions=len(
            re.findall(r"evidence insufficient", report_content or "", flags=re.IGNORECASE)
        ),
        absolute_date_mentions=_count_absolute_dates(report_content or ""),
    )


def resolve_canonical_query_case(query: str) -> CanonicalQueryCase:
    normalized_query = _normalize_token(query)
    for case in CANONICAL_QUERY_CASES.values():
        if normalized_query in {_normalize_token(case.key), _normalize_token(case.query)}:
            return case
        if normalized_query in {_normalize_token(alias) for alias in case.aliases}:
            return case
    raise KeyError(f"Unknown canonical query: {query}")


def find_latest_report(output_dir: Path, case: CanonicalQueryCase) -> Path:
    if not output_dir.exists():
        raise FileNotFoundError(f"Output directory not found: {output_dir}")

    candidates: List[Path] = []
    normalized_aliases = tuple(_normalize_token(alias) for alias in (case.key, case.query, *case.aliases))
    for path in output_dir.glob("*.md"):
        normalized_name = _normalize_token(path.stem)
        if any(alias and alias in normalized_name for alias in normalized_aliases):
            candidates.append(path)

    if not candidates:
        raise FileNotFoundError(f"No report found for {case.query} under {output_dir}")
    return sorted(candidates, key=lambda item: item.name)[-1]


def load_app_config_snapshot(db_path: Path | None) -> Dict[str, str]:
    if db_path is None or not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT key, value FROM app_config").fetchall()
        return {str(key): str(value) for key, value in rows}
    finally:
        conn.close()


def _missing_sections(baseline_titles: Sequence[str], current_titles: Sequence[str]) -> List[str]:
    current_set = {title.strip().lower() for title in current_titles}
    missing = []
    for title in baseline_titles:
        normalized = title.strip().lower()
        if normalized == "sources":
            continue
        if normalized not in current_set:
            missing.append(title)
    return missing


def compare_reports(baseline: ReportSignals, current: ReportSignals) -> Dict[str, object]:
    return {
        "section_count_delta": current.section_count - baseline.section_count,
        "source_count_delta": current.source_count - baseline.source_count,
        "primary_source_delta": current.primary_source_count - baseline.primary_source_count,
        "evidence_insufficient_delta": (
            current.evidence_insufficient_mentions - baseline.evidence_insufficient_mentions
        ),
        "absolute_date_mentions_delta": current.absolute_date_mentions - baseline.absolute_date_mentions,
        "missing_sections": _missing_sections(baseline.section_titles, current.section_titles),
    }


def parse_git_log_candidates(raw: str) -> List[Dict[str, str]]:
    commits: List[Dict[str, str]] = []
    for line in (raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"^([0-9a-f]{7,40})\s+(.+)$", stripped)
        if not match:
            continue
        commits.append({"sha": match.group(1), "message": match.group(2)})
    return commits


def collect_git_log_candidates(repo_root: Path | None, limit: int = 12) -> List[Dict[str, str]]:
    if repo_root is None:
        return []
    repo_root = repo_root.resolve()
    if not repo_root.exists():
        return []

    command = [
        "git",
        "-c",
        f"safe.directory={repo_root.as_posix()}",
        "-C",
        str(repo_root),
        "log",
        "--oneline",
        f"-n{max(1, limit)}",
        "--",
        "backend/main.py",
        "foreign_query_agent/agent.py",
        "foreign_query_agent/prompts/prompts.py",
        "discord_bot.py",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return parse_git_log_candidates(result.stdout)


def build_root_cause_candidates(
    comparison: Dict[str, object], current_config: Dict[str, str]
) -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []
    source_drop = int(comparison["source_count_delta"]) < 0 or int(comparison["primary_source_delta"]) < 0
    structure_drop = bool(comparison["missing_sections"]) or int(comparison["section_count_delta"]) < 0

    if source_drop and structure_drop:
        candidates.append(
            {
                "category": "multi_factor",
                "confidence": "medium",
                "reason": "Both sourcing depth and report structure regressed; inspect prompt, model, and provider together.",
            }
        )
    if source_drop:
        provider = current_config.get("search_provider", "unknown")
        candidates.append(
            {
                "category": "provider",
                "confidence": "medium",
                "reason": f"Source coverage regressed under current search provider '{provider}'. Verify retrieval quality and fallback behavior.",
            }
        )
    if structure_drop:
        candidates.append(
            {
                "category": "prompt",
                "confidence": "medium",
                "reason": "Missing sections or thinner structure suggests prompt/runtime formatting drift.",
            }
        )
    if current_config.get("primary_model"):
        candidates.append(
            {
                "category": "model",
                "confidence": "low",
                "reason": (
                    f"Current primary model is '{current_config['primary_model']}'. "
                    "Compare against historical runs before ruling model drift out."
                ),
            }
        )
    if not candidates:
        candidates.append(
            {
                "category": "manual_review",
                "confidence": "low",
                "reason": "No deterministic regression signal was extracted. Manual review is required.",
            }
        )
    return candidates


def generate_regression_report(
    query: str,
    baseline_dir: Path,
    current_dir: Path,
    db_path: Path | None = None,
    repo_root: Path | None = None,
) -> Dict[str, object]:
    case = resolve_canonical_query_case(query)
    baseline_report_path = find_latest_report(baseline_dir, case)
    current_report_path = find_latest_report(current_dir, case)

    baseline_text = baseline_report_path.read_text(encoding="utf-8")
    current_text = current_report_path.read_text(encoding="utf-8")
    baseline_signals = extract_report_signals(baseline_text)
    current_signals = extract_report_signals(current_text)
    current_config = load_app_config_snapshot(db_path)
    comparison = compare_reports(baseline_signals, current_signals)
    git_candidates = collect_git_log_candidates(repo_root)
    diagnosis_status = "ready_for_review"
    next_action = "Review root cause candidates and continue with current rerun comparison."
    if baseline_report_path.resolve() == current_report_path.resolve():
        diagnosis_status = "needs_current_rerun"
        next_action = (
            "Collect a different current rerun sample before locking root cause. "
            "Current baseline and current report point to the same artifact."
        )

    return {
        "query": case.query,
        "baseline_report": str(baseline_report_path),
        "current_report": str(current_report_path),
        "baseline_signals": asdict(baseline_signals),
        "current_signals": asdict(current_signals),
        "comparison": comparison,
        "current_config": current_config,
        "diagnosis_status": diagnosis_status,
        "next_action": next_action,
        "candidate_commits": ["5351ca4", "edb9d94"],
        "git_log_candidates": git_candidates,
        "root_cause_candidates": build_root_cause_candidates(comparison, current_config),
        "manual_rubric": [
            "时间线准确性",
            "primary source 覆盖",
            "反方/风险覆盖",
            "结构完整性",
            "Evidence insufficient 使用是否合理",
        ],
    }


def build_markdown_summary(report: Dict[str, object]) -> str:
    lines = [
        f"# Regression Diagnosis | {report['query']}",
        "",
        "## Diagnosis Status",
        f"- status: `{report.get('diagnosis_status', 'unknown')}`",
        f"- next_action: {report.get('next_action', 'n/a')}",
        "",
        "## Artifacts",
        f"- baseline_report: `{report['baseline_report']}`",
        f"- current_report: `{report['current_report']}`",
        "",
        "## Comparison",
    ]
    for key, value in dict(report.get("comparison", {})).items():
        lines.append(f"- {key}: `{value}`")

    config = dict(report.get("current_config", {}))
    lines.extend(["", "## Current Config"])
    if config:
        for key, value in config.items():
            lines.append(f"- {key}: `{value}`")
    else:
        lines.append("- (no app_config snapshot)")

    lines.extend(["", "## Root Cause Candidates"])
    for item in report.get("root_cause_candidates", []):
        lines.append(
            f"- `{item.get('category', 'unknown')}` ({item.get('confidence', 'unknown')}): {item.get('reason', '')}"
        )

    lines.extend(["", "## Candidate Commits"])
    for sha in report.get("candidate_commits", []):
        lines.append(f"- `{sha}`")
    for item in report.get("git_log_candidates", []):
        lines.append(f"- `{item.get('sha', '')}` {item.get('message', '')}")

    lines.extend(["", "## Manual Rubric"])
    for item in report.get("manual_rubric", []):
        lines.append(f"- {item}")
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline Deep Research regression diagnostics")
    parser.add_argument("--query", required=True, help="Canonical query or query key")
    parser.add_argument("--baseline-dir", required=True, help="Directory holding historical reports")
    parser.add_argument("--current-dir", required=True, help="Directory holding current rerun reports")
    parser.add_argument("--db", default="arcbrief.db", help="Optional sqlite DB path for app_config snapshot")
    parser.add_argument("--repo-root", default=".", help="Optional repo root for git log inspection")
    parser.add_argument("--markdown-out", help="Optional path to write a markdown summary")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        db_path = None

    report = generate_regression_report(
        query=args.query,
        baseline_dir=Path(args.baseline_dir),
        current_dir=Path(args.current_dir),
        db_path=db_path,
        repo_root=Path(args.repo_root) if args.repo_root else None,
    )
    if args.markdown_out:
        markdown_path = Path(args.markdown_out)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(build_markdown_summary(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
