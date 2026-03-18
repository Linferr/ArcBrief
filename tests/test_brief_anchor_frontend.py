from pathlib import Path


PAGE = Path("frontend/app/page.tsx")
NEWS_FEED = Path("frontend/app/components/NewsFeedPanel.tsx")
RESEARCH_PANEL = Path("frontend/app/components/ResearchPanel.tsx")
ARCHIVES_PANEL = Path("frontend/app/components/ArchivesPanel.tsx")


def test_page_threads_pending_brief_anchor_into_research_panel():
    src = PAGE.read_text(encoding="utf-8")
    assert "pendingResearchBriefId" in src
    assert "pendingBriefId={pendingResearchBriefId}" in src
    assert "setPendingResearchBriefId(briefId ?? null)" in src


def test_research_panel_posts_brief_anchor_and_surfaces_active_anchor():
    src = RESEARCH_PANEL.read_text(encoding="utf-8")
    assert "briefAnchorId" in src
    assert "brief_id: briefAnchorId ?? undefined" in src
    assert "Brief anchor active:" in src
    assert "Clear Anchor" in src


def test_news_and_archive_panels_expose_research_this_brief_actions():
    news_src = NEWS_FEED.read_text(encoding="utf-8")
    archive_src = ARCHIVES_PANEL.read_text(encoding="utf-8")

    assert "Research This Brief" in news_src
    assert "selectedBrief.id" in news_src
    assert "buildBriefFollowupQuery" in news_src

    assert "Research This Brief" in archive_src
    assert "selectedBrief.id" in archive_src
    assert "buildArchiveFollowupQuery" in archive_src
