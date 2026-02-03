"""Minimal log writer using BettaFish-style format."""

from pathlib import Path
from datetime import datetime


LOG_DIR = Path(__file__).resolve().parents[1] / "logs"


def _ensure_run_dir(run_id: str) -> Path:
    run_dir = LOG_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_log(source: str, content: str, run_id: str = "latest") -> None:
    run_dir = _ensure_run_dir(run_id)
    log_file = run_dir / f"{source}.log"
    timestamp = datetime.now().strftime("%H:%M:%S")
    clean = (content or "").replace("\n", "\\n").replace("\r", "")
    with log_file.open("a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{source.upper()}] {clean}\n")

