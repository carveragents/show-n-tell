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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
