"""Static checks for Deep Research layout structure."""

from pathlib import Path


RESEARCH_PANEL = Path("frontend/app/components/ResearchPanel.tsx")


def test_research_layout_uses_main_and_rail_columns():
    src = RESEARCH_PANEL.read_text(encoding="utf-8")
    assert 'className="research-layout"' in src
    assert 'className="research-main"' in src
    assert 'className="research-rail"' in src


def test_pipeline_and_report_order_is_main_first():
    src = RESEARCH_PANEL.read_text(encoding="utf-8")
    input_idx = src.index('className="research-input-section"')
    pipeline_idx = src.index('className="card pipeline-reading-card"')
    report_idx = src.index('className="card report-card"')
    assert input_idx < pipeline_idx < report_idx


def test_recent_runs_is_rendered_in_right_rail():
    src = RESEARCH_PANEL.read_text(encoding="utf-8")
    rail_idx = src.index('className="research-rail"')
    recent_card_idx = src.index('className="card recent-runs-collapsible"')
    assert rail_idx < recent_card_idx

