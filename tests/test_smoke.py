"""Smoke test for mock mode."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from foreign_query_agent import QueryAgent, Settings


def main() -> None:
    settings = Settings(output_dir=os.path.join(ROOT, "_test_outputs"))
    settings.mock_mode = True
    agent = QueryAgent(settings)
    report = agent.research("test topic")
    assert report.strip(), "report should not be empty"
    assert "## Sources" in report, "sources section should be present"
    path = agent.save_report(report, settings.output_dir)
    assert os.path.exists(path), "report file should exist"
    print("OK: mock smoke test passed")


if __name__ == "__main__":
    main()

