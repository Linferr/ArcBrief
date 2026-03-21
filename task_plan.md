# Deep Research Refactor Task Plan

## Goal
- Upgrade `Deep Research` from a runnable research chain into a long-form, quality-first, evaluation-ready system with clearer planning contracts, stronger evidence handling, and richer telemetry.

## Phase Status
- [completed] P0: Stabilize core architecture
  - Removed duplicate `QueryAgent.research()` ambiguity.
  - Introduced `ResearchSpec`, `SectionPlan`, `EvidenceItem`, and `SectionAssessment`.
  - Made report execution carry explicit `report_type`, `report_shape`, `length_preset`, and `quality_mode`.
- [completed] P1: Planner and formatter contract refactor
  - Added `industry / company / person / policy` template routing.
  - Added structured section planning with evidence type, subquestions, pass criteria, and word budget.
  - Made formatter consume planned section contracts instead of coercing every report into a fixed four-section frame.
- [completed] P2: Section synthesis and evidence structure
  - Propagated `report_type`, evidence requirements, and word budgets into search, summary, and reflection nodes.
  - Added source typing and evidence item extraction.
  - Tightened gate-blocked output into a short limited report with blockers and next steps.
- [completed] P3: Eval / cost telemetry
  - Added LLM token accounting and estimated cost tracking.
  - Extended `RunRecord`, `status`, and `history` with report metadata, token/cost fields, word count, primary-source count, and section gate results.
  - Added `/api/product/metrics` for aggregate completion/gate/cost/provider views.
- [completed] P4: Regression and quality tests
  - Expanded planner, formatter, telemetry, source hygiene, product metrics, and regression baseline coverage.
  - Restored the regression baseline harness so `baseline == current` passes without false word-count failures.

## Deferred Follow-Ups
- [completed] P4b: Premise validation and `claim_audit` recovery path
  - Added a pre-planner premise validation stage to detect invalid/disputed claims before normal section research begins.
  - Added `claim_audit` as a first-class report type with official-status, rumor-origin, corrected-current-state, and practical-takeaway sections.
  - Extended runtime telemetry with premise / reframing / effective report type fields so corrected runs can be audited in status, history, and aggregate metrics.
- [pending] P5: Stronger section-level gate scoring
  - Add explicit per-section coverage scores beyond current qualitative gate fields.
- [pending] P6: Formal eval judge expansion
  - Extend baseline/eval harness beyond proxy metrics into judge-driven scoring.

## Constraints
- Preserve runtime search fallback behavior (`Volcano Engine` primary, fallback retained).
- Keep unrelated dirty frontend work untouched.
- Maintain backward compatibility on `run_plan()` / `run()` node interactions for existing tests and stubs.

## Acceptance Snapshot
- Backend deep research refactor is green on `pytest tests -q`.
- Planner/formatter contract is now unified.
- Eval/cost telemetry is exposed at both run level and aggregate level.
