import os
import sqlite3
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.research_quality_regression import (
    CANONICAL_QUERY_CASES,
    build_markdown_summary,
    extract_report_signals,
    find_latest_report,
    generate_regression_report,
    parse_git_log_candidates,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_db(path: Path, fields: dict[str, str]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE app_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT INTO app_config(key, value) VALUES(?, ?)",
            list(fields.items()),
        )
        conn.commit()
    finally:
        conn.close()


def test_extract_report_signals_captures_quality_markers():
    report = """
## Latest Viewpoints
OpenAI published an update on 2026-03-01: https://openai.com/index/launch

## Risks & Contrarian Views
- Evidence insufficient for one disputed claim.

## Sources
- https://openai.com/index/launch
- https://www.anthropic.com/news/safety
"""

    signals = extract_report_signals(report)

    assert signals.section_titles == ["Latest Viewpoints", "Risks & Contrarian Views", "Sources"]
    assert signals.section_count == 3
    assert signals.source_count == 2
    assert signals.primary_source_count == 2
    assert signals.has_sources_section is True
    assert signals.has_risks_section is True
    assert signals.evidence_insufficient_mentions == 1
    assert signals.absolute_date_mentions >= 1


def test_find_latest_report_uses_canonical_aliases(tmp_path: Path):
    output_dir = tmp_path / "outputs"
    _write(output_dir / "query_report_20260305_234952_anthropic_233742.md", "# old")
    _write(output_dir / "query_report_20260306_002637_anthropic_001803.md", "# new")
    _write(output_dir / "query_report_20260305_230454_openai_225249.md", "# other")

    path = find_latest_report(output_dir, CANONICAL_QUERY_CASES["anthropic_recent"])

    assert path.name == "query_report_20260306_002637_anthropic_001803.md"


def test_generate_regression_report_builds_comparison_and_root_cause_candidates(tmp_path: Path):
    baseline_dir = tmp_path / "baseline"
    current_dir = tmp_path / "current"
    db_path = tmp_path / "arcbrief.db"

    baseline_report = """
## Latest Viewpoints
Timeline verified on 2026-03-01 with https://openai.com/research/a

## Actionable Tactics
- Use the official release notes.

## Toolchain and Config Templates
- Example config from https://docs.anthropic.com/docs/example

## Risks & Contrarian Views
- Include opposing evidence.

## Sources
- https://openai.com/research/a
- https://docs.anthropic.com/docs/example
- https://www.anthropic.com/news/launch
"""

    current_report = """
## Latest Viewpoints
Claim sourced from a third-party recap.

## Risks & Contrarian Views
- Evidence insufficient.
- Evidence insufficient.

## Sources
- https://example.com/recap
"""

    _write(
        baseline_dir / "query_report_20260305_234952_anthropic_233742.md",
        baseline_report,
    )
    _write(
        current_dir / "query_report_20260317_140000_anthropic_140000.md",
        current_report,
    )
    _make_db(
        db_path,
        {
            "primary_model": "Qwen3 MAX",
            "search_provider": "Volcano Engine",
        },
    )

    result = generate_regression_report(
        query="anthropic最近发展与舆情",
        baseline_dir=baseline_dir,
        current_dir=current_dir,
        db_path=db_path,
    )

    assert result["query"] == "anthropic最近发展与舆情"
    assert result["baseline_report"].endswith("query_report_20260305_234952_anthropic_233742.md")
    assert result["current_report"].endswith("query_report_20260317_140000_anthropic_140000.md")
    assert result["current_config"]["primary_model"] == "Qwen3 MAX"
    assert result["current_config"]["search_provider"] == "Volcano Engine"
    assert result["comparison"]["source_count_delta"] == -2
    assert result["comparison"]["primary_source_delta"] == -3
    assert result["comparison"]["evidence_insufficient_delta"] == 2
    assert result["comparison"]["missing_sections"] == [
        "Actionable Tactics",
        "Toolchain and Config Templates",
    ]
    categories = [item["category"] for item in result["root_cause_candidates"]]
    assert "provider" in categories
    assert "prompt" in categories
    assert result["candidate_commits"] == ["5351ca4", "edb9d94"]


def test_generate_regression_report_marks_same_sample_as_needing_rerun(tmp_path: Path):
    report_dir = tmp_path / "outputs"
    db_path = tmp_path / "arcbrief.db"

    _write(
        report_dir / "query_report_20260306_002637_anthropic_001803.md",
        """
## Latest Viewpoints
- Evidence insufficient.

## Sources
- https://example.com
""",
    )
    _make_db(
        db_path,
        {
            "primary_model": "Qwen3 MAX",
            "search_provider": "Volcano Engine",
        },
    )

    result = generate_regression_report(
        query="anthropic最近发展与舆情",
        baseline_dir=report_dir,
        current_dir=report_dir,
        db_path=db_path,
    )

    assert result["diagnosis_status"] == "needs_current_rerun"
    assert result["baseline_report"] == result["current_report"]
    assert "different current rerun sample" in result["next_action"]


def test_parse_git_log_candidates_extracts_sha_and_message():
    raw = """
5351ca4 Phase 3A: security hardening, provider strategy, i18n pipeline, and research UI updates
edb9d94 phase4: expand discord bot mobile workflows
"""

    commits = parse_git_log_candidates(raw)

    assert commits == [
        {
            "sha": "5351ca4",
            "message": "Phase 3A: security hardening, provider strategy, i18n pipeline, and research UI updates",
        },
        {
            "sha": "edb9d94",
            "message": "phase4: expand discord bot mobile workflows",
        },
    ]


def test_build_markdown_summary_renders_key_diagnosis_sections(tmp_path: Path):
    baseline_dir = tmp_path / "baseline"
    current_dir = tmp_path / "current"

    _write(
        baseline_dir / "query_report_20260305_234952_anthropic_233742.md",
        """
## Latest Viewpoints
Timeline verified on 2026-03-01 with https://openai.com/research/a

## Actionable Tactics
- Use the official release notes.

## Sources
- https://openai.com/research/a
- https://www.anthropic.com/news/launch
""",
    )
    _write(
        current_dir / "query_report_20260317_140000_anthropic_140000.md",
        """
## Latest Viewpoints
Claim sourced from a third-party recap.

## Risks & Contrarian Views
- Evidence insufficient.

## Sources
- https://example.com/recap
""",
    )

    report = generate_regression_report(
        query="anthropic最近发展与舆情",
        baseline_dir=baseline_dir,
        current_dir=current_dir,
        db_path=None,
    )
    markdown = build_markdown_summary(report)

    assert "## Diagnosis Status" in markdown
    assert "## Comparison" in markdown
    assert "## Root Cause Candidates" in markdown
    assert "source_count_delta" in markdown
    assert "provider" in markdown or "prompt" in markdown
