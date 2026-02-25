"""Encoding guard tests for docs and env templates."""

from pathlib import Path


UTF8_TARGET_FILES = [
    Path("README.md"),
    Path("docs/phase3-doc/specification.md"),
    Path("docs/phase3-doc/tasks.md"),
    Path("docs/phase3-doc/progress.md"),
]


def test_docs_are_utf8_strict_and_clean():
    for path in UTF8_TARGET_FILES:
        text = path.read_bytes().decode("utf-8")
        assert "\ufffd" not in text, f"replacement character found in {path}"


def test_env_example_is_ascii_only():
    raw = Path(".env.example").read_bytes()
    # ASCII-only policy avoids future locale/codepage mojibake in this file.
    raw.decode("ascii")
    text = raw.decode("utf-8")
    assert "\ufffd" not in text, "replacement character found in .env.example"
