import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.constants import APP_CONFIG_DEFAULTS
from foreign_query_agent.config import Settings


def test_default_search_provider_is_volcano_engine(monkeypatch):
    monkeypatch.delenv("ARCBRIEF_SEARCH_PROVIDER", raising=False)

    settings = Settings()

    assert APP_CONFIG_DEFAULTS["search_provider"] == "Volcano Engine"
    assert settings.search_provider == "Volcano Engine"
