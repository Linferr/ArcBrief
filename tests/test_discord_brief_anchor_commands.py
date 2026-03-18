from pathlib import Path


DISCORD_BOT = Path("discord_bot.py")


def test_discord_commands_accept_brief_id_and_use_payload_helpers():
    src = DISCORD_BOT.read_text(encoding="utf-8")

    assert 'brief_id="Optional brief anchor ID"' in src
    assert 'build_research_payload(query, language, brief_id=brief_id)' in src
    assert 'build_ask_payload(question, language, topic_id=topic_id, brief_id=brief_id)' in src
    assert 'build_analyze_payload(product, language, brief_id=brief_id)' in src


def test_brief_and_digest_commands_surface_mobile_brief_anchor_output():
    src = DISCORD_BOT.read_text(encoding="utf-8")

    assert "format_brief_mobile_message(brief)" in src
    assert "format_digest_mobile_message" in src
    assert 'api_get("/briefs/recent?limit=200")' in src
