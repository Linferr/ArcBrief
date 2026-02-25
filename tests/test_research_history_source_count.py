import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import backend.main as m


def test_estimate_source_count_prefers_sources_section_bullets():
    report = """
# Final Report

## Sources
- https://a.example.com/post
- https://b.example.com/post
- https://a.example.com/post
"""
    assert m._estimate_source_count(report) == 2


def test_estimate_source_count_falls_back_to_unique_urls():
    report = "Signal from https://x.test/a and https://y.test/b and https://x.test/a"
    assert m._estimate_source_count(report) == 2

