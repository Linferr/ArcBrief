"""CLI wrapper for offline Deep Research regression diagnostics."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.research_quality_regression import main


if __name__ == "__main__":
    main()
