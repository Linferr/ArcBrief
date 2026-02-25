"""Static checks for SettingsPanel connector options and helper text."""

from pathlib import Path


SETTINGS_PANEL = Path("frontend/app/components/SettingsPanel.tsx")


def test_search_provider_options_are_updated():
    src = SETTINGS_PANEL.read_text(encoding="utf-8")
    assert "<option>Tavily Search API</option>" in src
    assert "<option>Bocha Search</option>" in src
    assert "<option>Zhipu Web Search</option>" in src
    assert "<option>Volcano Engine</option>" in src
    assert "<option>Exa Search</option>" in src


def test_primary_llm_model_has_helper_text():
    src = SETTINGS_PANEL.read_text(encoding="utf-8")
    assert "Primary LLM Model" in src
    assert "Backend model for all AI tasks. Requires matching API key." in src
