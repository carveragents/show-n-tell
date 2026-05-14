#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.45"]
# ///
"""Take an authenticated snapshot of a URL.

Usage:
  uv run helpers/explore_page.py <url> \
    --storage-state PATH \
    --out-dir DIR \
    [--slug NAME] \
    [--viewport WxH]

Writes three files into <out-dir>:
  <slug>.png         — viewport screenshot (1440x900 by default)
  <slug>.dom.html    — full DOM at networkidle
  <slug>.meta.json   — {url_requested, final_url, title, status}

Headless. Uses storage_state for authentication. Mirrors record_demo.py's
context settings so the captured session isn't invalidated by browser
fingerprinting (see CLAUDE.md "Capture/explore/record viewport alignment").
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


def derive_slug(url: str) -> str:
    """Sanitize URL path into a filesystem-safe slug.

    Rules:
      - root path "/" → "home"
      - strip query, fragment, leading/trailing slashes
      - replace any non-[a-z0-9] char with "_"
      - lowercase
    """
    path = urlparse(url).path
    path = path.strip("/")
    if not path:
        return "home"
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_").lower()
    return slug or "home"


def _sanitize_user_slug(slug: str) -> str:
    """Apply derive_slug's character class to a user-supplied slug.

    Prevents path-traversal via `--slug ../escape` or `--slug /etc/passwd`.
    """
    return re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_").lower() or "home"


def parse_viewport(spec: str) -> dict:
    try:
        w, h = spec.split("x")
        return {"width": int(w), "height": int(h)}
    except (ValueError, AttributeError):
        raise SystemExit(f"Bad --viewport {spec!r}: expected WIDTHxHEIGHT, e.g. 1440x900")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("url")
    parser.add_argument("--storage-state", required=False, default=None,
                        help="Path to Playwright storage_state JSON (from helpers/capture_auth.py). "
                             "Omit for public pages that require no authentication.")
    parser.add_argument("--out-dir", required=True,
                        help="Directory to write <slug>.png / .dom.html / .meta.json into")
    parser.add_argument("--slug", default=None,
                        help="Slug for the output filenames; defaults to derived from URL path")
    parser.add_argument("--viewport", default="1440x900")
    args = parser.parse_args()

    if args.storage_state is not None:
        state_path = Path(args.storage_state).expanduser().resolve()
        if not state_path.exists():
            sys.exit(
                f"\n✗ storage_state file not found: {state_path}\n"
                f"  Capture it with: uv run helpers/capture_auth.py <start_url> "
                f"--out {state_path}"
            )
    else:
        state_path = None

    viewport = parse_viewport(args.viewport)
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = _sanitize_user_slug(args.slug) if args.slug else derive_slug(args.url)

    # cmux NODE_OPTIONS workaround — same as record_demo.py
    os.environ.pop("NODE_OPTIONS", None)

    # Import playwright only when needed (allows unit tests to import derive_slug)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx_kwargs = {"viewport": viewport}
            if state_path is not None:
                ctx_kwargs["storage_state"] = str(state_path)
            context = browser.new_context(**ctx_kwargs)
            page = context.new_page()
            try:
                response = page.goto(args.url, wait_until="networkidle", timeout=60_000)
            except Exception as e:
                sys.exit(f"\n✗ Could not load {args.url!r}: {e}")

            status = response.status if response is not None else None
            final_url = page.url
            title = page.title()
            dom = page.content()

            png_path = out_dir / f"{slug}.png"
            dom_path = out_dir / f"{slug}.dom.html"
            meta_path = out_dir / f"{slug}.meta.json"

            page.screenshot(path=str(png_path), full_page=False)
            dom_path.write_text(dom)
            meta_path.write_text(json.dumps({
                "url_requested": args.url,
                "final_url": final_url,
                "title": title,
                "status": status,
            }, indent=2))
        finally:
            browser.close()

    print(f"✓ {slug}.png  {slug}.dom.html  {slug}.meta.json  in  {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
