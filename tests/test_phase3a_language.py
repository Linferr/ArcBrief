"""Tests for language normalization and instruction helpers (Phase 3A)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import _normalize_language
from foreign_query_agent.prompts.prompts import language_instruction


def test_normalize_known():
    assert _normalize_language("Chinese (Simplified)") == "Chinese (Simplified)"
    assert _normalize_language("Japanese") == "Japanese"
    assert _normalize_language("English (US)") == "English (US)"


def test_normalize_unknown_defaults_to_english():
    assert _normalize_language(None) == "English (US)"
    assert _normalize_language("") == "English (US)"
    assert _normalize_language("fr") == "English (US)"
    assert _normalize_language("  ") == "English (US)"


def test_language_instruction_known():
    assert "Chinese" in language_instruction("Chinese (Simplified)")
    assert "Japanese" in language_instruction("Japanese")
    assert "English" in language_instruction("English (US)")


def test_language_instruction_fallback():
    assert "English" in language_instruction(None)
    assert "English" in language_instruction("unknown")
