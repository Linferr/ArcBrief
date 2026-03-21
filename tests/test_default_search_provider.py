import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import backend.main as main
from backend.constants import APP_CONFIG_DEFAULTS
from foreign_query_agent.config import Settings


def test_default_search_provider_is_volcano_engine(monkeypatch):
    monkeypatch.delenv("ARCBRIEF_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("FQ_LLM_MODEL", raising=False)

    settings = Settings()

    assert APP_CONFIG_DEFAULTS["search_provider"] == "Volcano Engine"
    assert settings.search_provider == "Volcano Engine"
    assert settings.llm_model == "qwen3-max"


def test_model_candidates_are_qwen_first():
    candidates = main._build_model_candidates("qwen3-max")

    assert candidates[0] == "qwen3-max"
    assert "gpt-4o-mini" in candidates
