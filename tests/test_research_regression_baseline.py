import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.research_regression_baseline import (
    build_baseline_manifest,
    evaluate_baseline_manifest,
    save_baseline_manifest,
)


def _write_report(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_build_baseline_manifest_from_output_dir(tmp_path):
    output_dir = tmp_path / "outputs"
    _write_report(
        output_dir / "query_report_20260306_002637_anthropic_001803.md",
        "# Report\n\n## Latest Viewpoints\nSignal\n\n## Risks & Contrarian Views\nRisk\n\n## Sources\n- https://www.anthropic.com/news/a\n",
    )
    _write_report(
        output_dir / "query_report_20260306_212500_chatgpt54_205919.md",
        "# Report\n\n## 最新观点\nSignal\n\n## 风险与反共识观点\nRisk\n\n## 来源\n- https://openai.com/index/a\n",
    )
    _write_report(
        output_dir / "query_report_20260305_230454_openai_225249.md",
        "# Report\n\n## Latest Viewpoints\nSignal\n\n## Risks & Contrarian Views\nRisk\n\n## Sources\n- https://openai.com/index/a\n",
    )

    manifest = build_baseline_manifest(output_dir)
    assert len(manifest["cases"]) == 3
    anthropic = next(item for item in manifest["cases"] if item["key"] == "anthropic_recent")
    assert anthropic["expectations"]["min_section_count"] >= 1
    assert anthropic["expectations"]["min_source_count"] == 1
    assert anthropic["expectations"]["min_word_count"] >= 50


def test_evaluate_baseline_manifest_passes_when_current_matches(tmp_path):
    output_dir = tmp_path / "outputs"
    report_body = "# Report\n\n## Latest Viewpoints\nSignal\n\n## Risks & Contrarian Views\nRisk\n\n## Sources\n- https://www.anthropic.com/news/a\n"
    _write_report(output_dir / "query_report_20260306_002637_anthropic_001803.md", report_body)
    _write_report(output_dir / "query_report_20260306_212500_chatgpt54_205919.md", "# Report\n\n## 最新观点\nSignal\n\n## 风险与反共识观点\nRisk\n\n## 来源\n- https://openai.com/index/a\n")
    _write_report(output_dir / "query_report_20260305_230454_openai_225249.md", "# Report\n\n## Latest Viewpoints\nSignal\n\n## Risks & Contrarian Views\nRisk\n\n## Sources\n- https://openai.com/index/a\n")

    manifest = build_baseline_manifest(output_dir)
    report = evaluate_baseline_manifest(manifest, output_dir)
    assert report["passed"] is True
    assert all(item["passed"] for item in report["results"])
    assert all("rubric" in item for item in report["results"])


def test_evaluate_baseline_manifest_detects_regression(tmp_path):
    baseline_dir = tmp_path / "baseline"
    current_dir = tmp_path / "current"
    _write_report(
        baseline_dir / "query_report_20260306_002637_anthropic_001803.md",
        "# Report\n\n## Latest Viewpoints\nSignal\n\n## Risks & Contrarian Views\nRisk\n\n## Sources\n- https://www.anthropic.com/news/a\n",
    )
    _write_report(
        baseline_dir / "query_report_20260306_212500_chatgpt54_205919.md",
        "# Report\n\n## 最新观点\nSignal\n\n## 风险与反共识观点\nRisk\n\n## 来源\n- https://openai.com/index/a\n",
    )
    _write_report(
        baseline_dir / "query_report_20260305_230454_openai_225249.md",
        "# Report\n\n## Latest Viewpoints\nSignal\n\n## Risks & Contrarian Views\nRisk\n\n## Sources\n- https://openai.com/index/a\n",
    )

    manifest = build_baseline_manifest(baseline_dir)
    _write_report(current_dir / "query_report_20260306_999999_anthropic_999999.md", "# Report\n\n## Latest Viewpoints\nSignal only\n")
    _write_report(current_dir / "query_report_20260306_999998_chatgpt54_999998.md", "# Report\n\n## 最新观点\nSignal\n")
    _write_report(current_dir / "query_report_20260306_999997_openai_999997.md", "# Report\n\n## Latest Viewpoints\nSignal\n")

    report = evaluate_baseline_manifest(manifest, current_dir)
    anthropic = next(item for item in report["results"] if item["key"] == "anthropic_recent")
    assert report["passed"] is False
    assert anthropic["passed"] is False
    assert any(failure.startswith("missing_sections:") for failure in anthropic["failures"])


def test_save_baseline_manifest_writes_json(tmp_path):
    output_dir = tmp_path / "outputs"
    _write_report(output_dir / "query_report_20260306_002637_anthropic_001803.md", "# Report\n\n## Latest Viewpoints\nSignal\n\n## Risks & Contrarian Views\nRisk\n\n## Sources\n- https://www.anthropic.com/news/a\n")
    _write_report(output_dir / "query_report_20260306_212500_chatgpt54_205919.md", "# Report\n\n## 最新观点\nSignal\n\n## 风险与反共识观点\nRisk\n\n## 来源\n- https://openai.com/index/a\n")
    _write_report(output_dir / "query_report_20260305_230454_openai_225249.md", "# Report\n\n## Latest Viewpoints\nSignal\n\n## Risks & Contrarian Views\nRisk\n\n## Sources\n- https://openai.com/index/a\n")

    manifest_path = tmp_path / "baseline.json"
    manifest = save_baseline_manifest(output_dir, manifest_path)
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert loaded["cases"][0]["baseline_report"]
    assert manifest["cases"][0]["baseline_report"]
