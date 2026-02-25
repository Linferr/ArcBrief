"""Static checks for simplified 3-node pipeline UI."""

from pathlib import Path


RESEARCH_PANEL = Path("frontend/app/components/ResearchPanel.tsx")


def test_pipeline_copy_contains_three_core_nodes():
    src = RESEARCH_PANEL.read_text(encoding="utf-8")
    assert "decompositionTitle" in src
    assert "iterativeTitle" in src
    assert "synthesisTitle" in src


def test_pipeline_noise_labels_removed():
    src = RESEARCH_PANEL.read_text(encoding="utf-8")
    assert "Status:" not in src
    assert "Stage:" not in src
    assert "Provider:" not in src
    assert "Fallback:" not in src
    assert "Evidence window:" not in src

