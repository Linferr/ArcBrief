"""Fixed-query regression baseline harness for Deep Research."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .research_quality_regression import (
    CANONICAL_QUERY_CASES,
    extract_report_signals,
    find_latest_report,
    resolve_canonical_query_case,
)


def _default_expectations(signals: Dict[str, Any]) -> Dict[str, Any]:
    required_sections = [title for title in signals.get("section_titles", []) if title.strip().lower() not in {"sources", "来源"}]
    return {
        "min_section_count": max(1, int(signals.get("section_count", 0)) - 1),
        "required_sections": required_sections,
        "min_source_count": max(0, int(signals.get("source_count", 0))),
        "min_primary_source_count": max(0, int(signals.get("primary_source_count", 0))),
        "max_evidence_insufficient_mentions": int(signals.get("evidence_insufficient_mentions", 0)) + 1,
    }


def build_baseline_manifest(output_dir: Path) -> Dict[str, Any]:
    cases: List[Dict[str, Any]] = []
    for case in CANONICAL_QUERY_CASES.values():
        report_path = find_latest_report(output_dir, case)
        signals = asdict(extract_report_signals(report_path.read_text(encoding="utf-8")))
        cases.append(
            {
                "key": case.key,
                "query": case.query,
                "baseline_report": report_path.as_posix(),
                "expectations": _default_expectations(signals),
            }
        )
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "cases": cases,
    }


def save_baseline_manifest(output_dir: Path, manifest_path: Path) -> Dict[str, Any]:
    manifest = build_baseline_manifest(output_dir)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def load_baseline_manifest(manifest_path: Path) -> Dict[str, Any]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _missing_required_sections(required_sections: List[str], current_sections: List[str]) -> List[str]:
    current_normalized = {title.strip().lower() for title in current_sections}
    return [title for title in required_sections if title.strip().lower() not in current_normalized]


def evaluate_baseline_manifest(manifest: Dict[str, Any], current_dir: Path) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    all_passed = True
    for case_entry in manifest.get("cases", []):
        case = resolve_canonical_query_case(case_entry["key"])
        current_report = find_latest_report(current_dir, case)
        current_signals = asdict(extract_report_signals(current_report.read_text(encoding="utf-8")))
        expectations = dict(case_entry.get("expectations", {}))
        failures: List[str] = []

        if int(current_signals.get("section_count", 0)) < int(expectations.get("min_section_count", 0)):
            failures.append("section_count_below_baseline")
        missing_sections = _missing_required_sections(
            list(expectations.get("required_sections", [])),
            list(current_signals.get("section_titles", [])),
        )
        if missing_sections:
            failures.append(f"missing_sections:{', '.join(missing_sections)}")
        if int(current_signals.get("source_count", 0)) < int(expectations.get("min_source_count", 0)):
            failures.append("source_count_below_baseline")
        if int(current_signals.get("primary_source_count", 0)) < int(expectations.get("min_primary_source_count", 0)):
            failures.append("primary_source_count_below_baseline")
        if int(current_signals.get("evidence_insufficient_mentions", 0)) > int(expectations.get("max_evidence_insufficient_mentions", 999)):
            failures.append("evidence_insufficient_above_tolerance")

        case_passed = len(failures) == 0
        all_passed = all_passed and case_passed
        results.append(
            {
                "key": case.key,
                "query": case.query,
                "baseline_report": case_entry["baseline_report"],
                "current_report": current_report.as_posix(),
                "passed": case_passed,
                "failures": failures,
                "current_signals": current_signals,
                "expectations": expectations,
            }
        )
    return {
        "evaluated_at": datetime.utcnow().isoformat(),
        "passed": all_passed,
        "case_count": len(results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fixed-query regression baseline harness")
    parser.add_argument("--output-dir", help="Directory used to generate the baseline manifest")
    parser.add_argument("--manifest", required=True, help="Path to the baseline manifest JSON")
    parser.add_argument("--current-dir", help="Directory containing current reports for evaluation")
    parser.add_argument("--write-manifest", action="store_true", help="Generate or refresh the baseline manifest")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if args.write_manifest:
        if not args.output_dir:
            raise SystemExit("--output-dir is required when --write-manifest is used")
        manifest = save_baseline_manifest(Path(args.output_dir), manifest_path)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    if not args.current_dir:
        raise SystemExit("--current-dir is required when evaluating a baseline manifest")
    manifest = load_baseline_manifest(manifest_path)
    report = evaluate_baseline_manifest(manifest, Path(args.current_dir))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
