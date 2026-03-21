# Deep Research Refactor Progress

## 2026-03-21

### Initialization
- Initialized file-based planning for the Deep Research refactor.
- Confirmed the repo contained unrelated dirty frontend files and kept backend refactor work isolated from those edits.
- Attempted the required superpowers bootstrap command; it failed locally with an OS-level access-denied error, so no bootstrap-derived instructions were available.

### P0: Architecture Stabilization
- Consolidated `QueryAgent.research()` into a single active implementation.
- Added shared internal contracts in `foreign_query_agent/state.py`:
  - `ResearchSpec`
  - `SectionPlan`
  - `EvidenceItem`
  - `SectionAssessment`
- Propagated `report_type`, `report_shape`, `length_preset`, and `quality_mode` through research state.

### P1: Planner / Formatter Contract Alignment
- Reworked `ReportStructureNode` to support structured planning and explicit template selection for:
  - `industry_brief`
  - `company_analysis`
  - `person_profile`
  - `policy_analysis`
- Added section contracts with evidence requirements, subquestions, pass criteria, and target words.
- Replaced the formatting path so final report composition follows planned sections instead of forcing every output into a fixed four-section template.

### P2: Prompt / Synthesis / Evidence Tightening
- Updated research prompts to be less AI-tooling-centric and more compatible with `company / person / policy` topics.
- Passed report-type and evidence metadata into search, summary, and reflection nodes.
- Added source typing and evidence item extraction for section-level synthesis.
- Filtered provider-placeholder citations from source appendices.
- Shortened gate-blocked reports into concise limited-delivery handoffs.

### P3: Eval / Cost Telemetry
- Added token/cost accounting to the LLM client layer.
- Set Qwen (`qwen3-max`) as the default LLM model in config.
- Extended run records, status payloads, and history payloads with:
  - report metadata
  - word count
  - token usage
  - estimated cost
  - primary-source count
  - section gate results
- Added aggregate product metrics endpoint `/api/product/metrics`.

### P4: Regression / Test Harness
- Expanded tests for:
  - planner template routing
  - formatter contract preservation
  - source appendix hygiene
  - token/cost metrics summary
  - aggregate product metrics
  - Qwen-first provider/model defaults
- Extended the fixed-query baseline harness with `baseline_word_count` and rubric fields.
- Fixed a false-positive regression case where synthetic baseline fixtures were failing on word-count floors even when `baseline == current`.

### Verification
- Targeted regression + quality harness:
  - `pytest tests/test_research_regression_baseline.py tests/test_research_quality_regression.py -q`
  - `10 passed`
- Targeted planner / telemetry / source hygiene suite:
  - `pytest tests/test_report_structure_templates.py tests/test_research_actionable_output.py tests/test_metrics_summary_api.py tests/test_product_metrics_api.py tests/test_default_search_provider.py tests/test_research_global_source_ids.py tests/test_research_recency_and_sources.py -q`
  - `18 passed`
- Full backend suite:
  - `pytest tests -q`
  - `167 passed, 4 warnings`

### Current Status
- Deep Research refactor plan is implemented to the level requested in this phase.
- Remaining work is follow-on enhancement rather than stabilization:
  - harder section coverage scoring
  - richer claim-evidence validation
  - judge-based formal eval

### P4b: Premise Validation + Claim Audit Recovery
- Added `PremiseCheckNode` ahead of planner execution so invalid/disputed user premises can be reframed before section planning.
- Added `claim_audit` as a first-class long-form report type and wired planner defaults for:
  - `Official Status Check`
  - `Where The Claim Came From`
  - `What Is Actually True Now`
  - `Practical Takeaways`
- Updated search planning so `claim_audit` runs official-status-first retrieval and filters clearly fabricated derivative queries such as fake OpenAI version suffixes.
- Updated summary / host flows to consume `premise_status`, `original_query`, `effective_query`, and `report_type_effective`.
- Extended run/status/history/product telemetry with:
  - `premise_status`
  - `query_reframed`
  - `original_query`
  - `effective_query`
  - `report_type_requested`
  - `report_type_effective`
  - `official_source_count`

### Verification (Premise / Claim Audit Batch)
- Targeted premise + claim audit + telemetry suite:
  - `pytest tests/test_premise_check_node.py tests/test_claim_audit_runtime.py tests/test_report_structure_templates.py tests/test_metrics_summary_api.py tests/test_product_metrics_api.py -q`
  - `12 passed`
- Full backend suite:
  - `pytest tests -q`
  - `171 passed, 4 warnings`
