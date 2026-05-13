#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest>=8"]
# ///
"""Unit tests for explore_page.py — slug derivation and missing-state error."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "helpers"))

from explore_page import derive_slug, _sanitize_user_slug  # noqa: E402


def test_root_path_slugs_as_home():
    assert derive_slug("https://example.com/") == "home"


def test_simple_path_slugs():
    assert derive_slug("https://example.com/dashboard") == "dashboard"


def test_nested_path_slugs_with_underscores():
    assert derive_slug("https://example.com/dashboard/account") == "dashboard_account"


def test_query_string_stripped():
    assert derive_slug("https://example.com/foo?x=1&y=2") == "foo"


def test_trailing_slash_ignored():
    assert derive_slug("https://example.com/foo/") == "foo"


def test_dot_replaced_with_underscore():
    assert derive_slug("https://example.com/foo/bar.html") == "foo_bar_html"


def test_user_slug_with_traversal_is_sanitized():
    """Path-traversal characters in --slug are sanitized to keep outputs under out-dir."""
    assert _sanitize_user_slug("../escape") == "escape"
    assert _sanitize_user_slug("/etc/passwd") == "etc_passwd"
    assert _sanitize_user_slug("normal-name_123") == "normal_name_123"
    assert _sanitize_user_slug("../") == "home"  # empty after sanitize → home


def test_missing_storage_state_exits_with_actionable_error(tmp_path):
    """explore_page.py exits non-zero with a helpful error pointing at capture_auth.py."""
    script = HERE.parent / "helpers" / "explore_page.py"
    bad_state = tmp_path / "no-such.json"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    proc = subprocess.run(
        ["uv", "run", str(script),
         "https://example.com/",
         "--storage-state", str(bad_state),
         "--out-dir", str(out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode != 0, proc.stdout
    combined = proc.stdout + proc.stderr
    assert "storage_state file not found" in combined, combined
    assert str(bad_state) in combined, combined
    assert "capture_auth.py" in combined, combined


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
