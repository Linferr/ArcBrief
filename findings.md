# Deep Research Refactor Findings

## Current Architecture After Refactor
- `Deep Research` now runs against an explicit `ResearchSpec` rather than implicit prompt defaults.
- Section planning is first-class: each section can carry title, scope, evidence type, subquestions, pass criteria, and target words.
- Section execution remains parallel across sections, while each section preserves sequential `search -> summary -> critic/reflection` ordering.

## Key Technical Findings
- The pre-refactor duplicate `QueryAgent.research()` definitions were a real maintainability hazard; consolidating them removed ambiguity about the live execution path.
- Planner/template routing already had the seeds of type-awareness, but formatting was undoing that work by forcing a shared four-section shape. Fixing formatter contract consumption was the highest-ROI structural change.
- Search/summary prompts were biased toward AI tooling/actionability language. Passing `report_type`, evidence needs, and word budgets into the nodes materially improves non-AI topic fit without requiring fully dynamic planning yet.
- Source appendices needed hygiene: provider placeholder titles were leaking into final reports. Filtering placeholder sources and preserving `source_type` reduces citation noise.
- Limited-delivery reports needed to be shorter. A gate-blocked report is now a constrained handoff with blockers and follow-up paths rather than a sprawling best-effort long report.

## Telemetry Findings
- Run-level telemetry is now rich enough to support cost and quality iteration:
  - `report_type`
  - `planning_template`
  - `word_count`
  - `prompt_tokens`
  - `completion_tokens`
  - `estimated_cost_usd`
  - `primary_source_count`
  - `section_gate_results`
- Aggregate telemetry via `/api/product/metrics` is sufficient for first-pass operational analysis:
  - task completion rate
  - gate pass rate
  - limited delivery rate
  - average duration
  - average / total estimated cost
  - primary source coverage rate
  - by-provider and by-report-type breakdowns

## Formal Eval Findings
- The fixed-query baseline harness is useful, but synthetic baseline fixtures exposed a false-positive failure mode when `min_word_count` was interpreted as a hard floor even if the baseline sample itself was shorter.
- The harness now stores `baseline_word_count` and evaluates the effective minimum against the baseline sample, which keeps the regression contract strict for real runs while allowing baseline-equals-current parity tests to pass.

## Remaining Gaps
- The biggest remaining quality gap for false-premise queries is no longer outright rejection; it is now report depth and evidence calibration within the new `claim_audit` path.
- `PremiseCheckNode` fixes the highest-cost failure mode by reframing invalid/disputed queries before planner/search expansion, but the heuristic layer is still intentionally narrow and should later be backed by stronger judge-style validation.
- `claim_audit` improves safety by forcing official-status-first retrieval and by filtering obviously fake derivative queries (for example, fabricated OpenAI version suffixes), but section-level minimum evidence thresholds are still mostly prompt-driven rather than hard-scored.
- Status/history/product metrics now expose `premise_status`, `query_reframed`, `original_query`, `effective_query`, and requested/effective report-type splits, which makes false-premise corrections observable instead of implicit.
- Section gate results still capture coarse pass/revise/reject semantics rather than hard coverage scores.
- Source quality is improved but not yet a full claim-evidence verification layer.
- Formal eval still relies on proxy metrics rather than judge-based scoring for accuracy/completeness.
