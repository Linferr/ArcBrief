from pathlib import Path


NEWS_FEED_PANEL = Path("frontend/app/components/NewsFeedPanel.tsx")


def test_recent_briefs_uses_48h_window_query():
    src = NEWS_FEED_PANEL.read_text(encoding="utf-8")
    assert "/briefs/${topicId}/history?limit=30&since_hours=48" in src

