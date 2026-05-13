#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.45"]
# ///
"""Capture a Playwright storage_state.json for a demo recording.

Usage:
    uv run helpers/capture_auth.py <start_url> [--out PATH] [--viewport WxH]

Defaults match scripts/record_demo.py:
    --viewport 1440x900    (record_demo's default)
    --out auth.json        (in the current directory)

The user logs in interactively (handles OAuth, 2FA, captchas — anything
the site demands). When they close the browser window, the script writes
storage_state to <PATH> with mode 0600 and prints next-step hints.

Why a dedicated helper: capturing in regular Chrome and recording in
Playwright Chromium can produce different browser fingerprints that some
sites use to invalidate sessions. By capturing through this script we
match the recorder's Chromium settings.
"""
import argparse
import os
import stat
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright


def parse_viewport(spec: str) -> dict:
    try:
        w, h = spec.split("x")
        return {"width": int(w), "height": int(h)}
    except Exception:
        raise SystemExit(f"Bad --viewport {spec!r}: expected WIDTHxHEIGHT, e.g. 1440x900")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("start_url", help="URL to open initially (your login page or the site root)")
    parser.add_argument("--out", default="auth.json",
                        help="Output path for storage_state JSON (default: ./auth.json)")
    parser.add_argument("--viewport", default="1440x900",
                        help="Browser viewport WxH (default 1440x900, matching record_demo.py)")
    args = parser.parse_args()

    viewport = parse_viewport(args.viewport)
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # cmux NODE_OPTIONS workaround — same as record_demo.py
    os.environ.pop("NODE_OPTIONS", None)

    print(f"Launching Chromium (viewport {viewport['width']}x{viewport['height']})…",
          file=sys.stderr)
    print(f"Navigate to your login flow, complete it, then CLOSE the browser window to save.\n",
          file=sys.stderr)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(viewport=viewport)
        page = context.new_page()
        try:
            page.goto(args.start_url, wait_until="load", timeout=60_000)
        except Exception as e:
            sys.exit(f"\n✗ Could not load {args.start_url!r}: {e}")

        # Wait for the user to close the page / window. Playwright fires `close`
        # whether they close just the tab (context stays alive) or the whole
        # browser window (context dies). In both cases we proceed to storage_state
        # save below; if the browser is gone, that call raises and we exit cleanly.
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass

        # Create a sibling 0600 temp file BEFORE writing — so credentials never
        # exist on disk with default permissions.
        fd, tmp = tempfile.mkstemp(dir=str(out_path.parent), prefix=".auth_", suffix=".tmp.json")
        os.close(fd)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)   # 0600 before any data lands
        try:
            context.storage_state(path=tmp)
            os.rename(tmp, out_path)                  # atomic on POSIX
        except Exception as e:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            sys.exit(
                f"\n✗ Could not save storage_state to {out_path}: {e}\n"
                f"  This usually means you closed the browser before login completed."
            )
        finally:
            try:
                browser.close()
            except Exception:
                pass
    print(f"\n✓ Saved {out_path} (mode 0600)", file=sys.stderr)
    print(f"\nNext step: add to your demo_config.yaml:", file=sys.stderr)
    print(f"  session:", file=sys.stderr)
    print(f"    storage_state: \"{out_path}\"", file=sys.stderr)


if __name__ == "__main__":
    main()
