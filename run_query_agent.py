"""CLI runner for ArcBrief QueryAgent."""

import argparse

from foreign_query_agent import QueryAgent, Settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, help="Research query")
    parser.add_argument("--output-dir", default="outputs", help="Output directory")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode")
    args = parser.parse_args()

    settings = Settings(output_dir=args.output_dir)
    if args.mock:
        settings.mock_mode = True

    agent = QueryAgent(settings)
    report = agent.research(args.query)
    path = agent.save_report(report, args.output_dir)
    print(f"Report saved: {path}")


if __name__ == "__main__":
    main()

