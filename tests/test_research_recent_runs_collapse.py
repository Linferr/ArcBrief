"""Static checks for Recent Runs collapse and progressive loading."""

from pathlib import Path


RESEARCH_PANEL = Path("frontend/app/components/ResearchPanel.tsx")


def test_recent_runs_collapsed_count_is_three():
    src = RESEARCH_PANEL.read_text(encoding="utf-8")
    assert "const RECENT_COLLAPSED_COUNT = 3;" in src
    assert "history.slice(0, RECENT_COLLAPSED_COUNT)" in src


def test_recent_runs_expand_and_load_more_controls_exist():
    src = RESEARCH_PANEL.read_text(encoding="utf-8")
    assert "const [recentExpanded, setRecentExpanded] = useState(false);" in src
    assert "const hasMoreHistory = recentExpanded && history.length < historyTotal;" in src
    assert "const loadMoreHistory = () => {" in src
    assert "{recentExpanded ? copy.collapse : copy.expand}" in src
    assert '<div className="recent-runs-footer">' in src
    assert "{hasMoreHistory && (" in src
    assert "source-meta ui-font" in src
