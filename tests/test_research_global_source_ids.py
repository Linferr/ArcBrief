"""Research source ID normalization tests."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from foreign_query_agent.agent import QueryAgent
from foreign_query_agent.state import ReportState


def test_assign_global_source_ids_rewrites_local_ids_without_collision():
    state = ReportState(query="mcp latest")

    first_text, first_map = QueryAgent._assign_global_source_ids(
        "First claim [S1] and second claim [S2].",
        {
            "S1": {"title": "A", "url": "https://a.test"},
            "S2": {"title": "B", "url": "https://b.test"},
        },
        state,
    )
    second_text, second_map = QueryAgent._assign_global_source_ids(
        "Reflection keeps local [S1] only.",
        {"S1": {"title": "C", "url": "https://c.test"}},
        state,
    )

    assert first_text == "First claim [S1] and second claim [S2]."
    assert second_text == "Reflection keeps local [S3] only."
    assert sorted(first_map.keys()) == ["S1", "S2"]
    assert sorted(second_map.keys()) == ["S3"]
    assert state.global_source_map["S1"]["url"] == "https://a.test"
    assert state.global_source_map["S2"]["url"] == "https://b.test"
    assert state.global_source_map["S3"]["url"] == "https://c.test"


def test_append_sources_uses_global_source_map_once():
    report = "# Report\n\n## Latest Viewpoints\nBody [S1] [S2]\n\n## Sources\n- stale"
    final = QueryAgent._append_sources_from_map(
        QueryAgent._strip_stale_sources(report),
        {
            "S1": {"title": "A", "url": "https://a.test"},
            "S2": {"title": "B", "url": "https://b.test"},
        },
        "English (US)",
    )

    assert final.count("## Sources") == 1
    assert "- [S1] A -- https://a.test" in final
    assert "- [S2] B -- https://b.test" in final
