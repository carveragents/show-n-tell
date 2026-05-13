#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest>=8", "pyyaml>=6"]
# ///
"""Unit tests for storage_state path resolution and missing-file error.

Run: uv run tests/test_storage_state.py
(or: uv run --with pytest pytest tests/test_storage_state.py -v)
"""
import os
import sys
from pathlib import Path

import pytest

# Make scripts/ importable
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from _lib import resolve_session_path  # noqa: E402


def test_relative_path_resolves_against_working_dir(tmp_path):
    wd = tmp_path / "wd"
    wd.mkdir()
    result = resolve_session_path("./auth.json", wd)
    assert result == (wd / "auth.json").resolve()


def test_absolute_path_used_as_is(tmp_path):
    abs_path = tmp_path / "auth.json"
    result = resolve_session_path(str(abs_path), tmp_path / "wd")
    assert result == abs_path


def test_tilde_expands_to_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    result = resolve_session_path("~/auth.json", tmp_path / "wd")
    assert result == (tmp_path / "auth.json").resolve()


def test_storage_state_missing_file_raises_actionable_error(tmp_path):
    """record_demo.py exits with an actionable error when storage_state path doesn't exist.

    We invoke record_demo.py as a subprocess against a minimal fake working dir
    (just enough YAML to get past arg parsing and reach the context-creation block).
    Asserts the error message names the resolved path and points at capture_auth.py.
    """
    import json
    import subprocess

    wd = tmp_path / "wd"
    wd.mkdir()
    (wd / "_voiceover").mkdir()
    (wd / "_voiceover" / "manifest.json").write_text(json.dumps({"beats": []}))
    (wd / "storyboard.yaml").write_text("beats: []\n")
    (wd / "branding.yaml").write_text("brand:\n  name: Test\n")
    (wd / "demo_config.yaml").write_text(
        "site:\n  base_url: http://localhost\n"
        "output:\n  filename: demo.mp4\n  working_dir: " + str(wd) + "\n"
        "recording:\n  viewport: {width: 1440, height: 900}\n  framerate: 25\n"
        "session:\n  storage_state: ./does-not-exist.json\n"
    )

    script = HERE.parent / "scripts" / "record_demo.py"
    proc = subprocess.run(
        ["uv", "run", str(script), "--working-dir", str(wd)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode != 0, f"Expected failure, got success. stdout: {proc.stdout!r}"
    combined = proc.stdout + proc.stderr
    assert "storage_state file not found" in combined, combined
    assert str(wd / "does-not-exist.json") in combined, combined
    assert "capture_auth.py" in combined, combined


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
