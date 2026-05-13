# Authenticated page exploration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture auth state in a new Phase 2a (moved from Phase 5) and add `helpers/explore_page.py` so Phase 2 site exploration can see authenticated pages.

**Architecture:** New 60-ish-line Playwright helper that one-shots a URL with storage_state loaded, writes screenshot + DOM + meta files. SKILL.md restructured so auth capture happens before exploration. Doc updates to reflect the new alignment invariant (capture/explore/record all share viewport).

**Tech Stack:** Python 3.12+, `uv` PEP 723 inline scripts, Playwright Python (sync API), `pytest`.

**Spec:** `docs/superpowers/specs/2026-05-12-explore-page-auth-design.md`

**Model discipline:** All implementer dispatches use Haiku (mechanical tasks with complete specs). All reviewer dispatches use Sonnet. Controller stays on Opus.

---

## File Touch List

- `helpers/explore_page.py` — NEW
- `tests/test_explore_page.py` — NEW (unit: slug derivation + missing-state error)
- `tests/test_explore_page_e2e.py` — NEW (integration with localhost cookie server)
- `SKILL.md` — restructure: Phase 2 → 2a + 2b; remove "Auth capture" from Phase 5
- `CLAUDE.md` — replace existing "Capture-record viewport match" bullet with expanded "Capture/explore/record viewport alignment"
- `docs/SCHEMAS.md` — expand the "Viewport match" paragraph to mention explore_page.py

---

### Task 1: `helpers/explore_page.py` + tests

**Recommended tier:** Haiku (mechanical helper, complete spec, isolated).

**Files:**
- Create: `helpers/explore_page.py`
- Create: `tests/test_explore_page.py`
- Create: `tests/test_explore_page_e2e.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_explore_page.py`:

```python
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

from explore_page import derive_slug  # noqa: E402


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
```

- [ ] **Step 2: Run the unit tests to verify they fail**

Run: `uv run tests/test_explore_page.py`

Expected: `ImportError: cannot import name 'derive_slug'` — six errors plus the missing-state subprocess test failing because the script doesn't exist yet.

- [ ] **Step 3: Write `helpers/explore_page.py`**

Create `helpers/explore_page.py`:

```python
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

from playwright.sync_api import sync_playwright


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


def parse_viewport(spec: str) -> dict:
    try:
        w, h = spec.split("x")
        return {"width": int(w), "height": int(h)}
    except (ValueError, AttributeError):
        raise SystemExit(f"Bad --viewport {spec!r}: expected WIDTHxHEIGHT, e.g. 1440x900")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("url")
    parser.add_argument("--storage-state", required=True,
                        help="Path to Playwright storage_state JSON (from helpers/capture_auth.py)")
    parser.add_argument("--out-dir", required=True,
                        help="Directory to write <slug>.png / .dom.html / .meta.json into")
    parser.add_argument("--slug", default=None,
                        help="Slug for the output filenames; defaults to derived from URL path")
    parser.add_argument("--viewport", default="1440x900")
    args = parser.parse_args()

    state_path = Path(args.storage_state).expanduser().resolve()
    if not state_path.exists():
        sys.exit(
            f"\n✗ storage_state file not found: {state_path}\n"
            f"  Capture it with: uv run helpers/capture_auth.py <start_url> "
            f"--out {state_path}"
        )

    viewport = parse_viewport(args.viewport)
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = args.slug or derive_slug(args.url)

    # cmux NODE_OPTIONS workaround — same as record_demo.py
    os.environ.pop("NODE_OPTIONS", None)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport=viewport, storage_state=str(state_path))
        page = context.new_page()
        try:
            response = page.goto(args.url, wait_until="networkidle", timeout=60_000)
        except Exception as e:
            browser.close()
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

        browser.close()

    print(f"✓ {slug}.png  {slug}.dom.html  {slug}.meta.json  in  {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run unit tests to verify they pass**

Run: `uv run tests/test_explore_page.py`

Expected: `7 passed` (6 slug tests + 1 missing-state subprocess test).

- [ ] **Step 5: Write the failing e2e test**

Create `tests/test_explore_page_e2e.py`:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest>=8"]
# ///
"""End-to-end test: explore_page.py loads storage_state and accesses gated content."""
import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent


class CookieGatedHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        cookie = self.headers.get("Cookie", "")
        if self.path == "/protected":
            if "auth=ok" in cookie:
                self._respond(200, "<html><body><h1>Protected content</h1></body></html>")
            else:
                self._respond(401, "<html><body>Login required</body></html>")
            return
        self._respond(200, "<html><body><h1>Home</h1></body></html>")

    def log_message(self, *args):  # quiet
        pass

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode())


@pytest.fixture
def gated_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), CookieGatedHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def test_explore_page_loads_storage_state(tmp_path, gated_server):
    base = gated_server
    host = base.replace("http://", "").split(":")[0]

    # Hand-craft auth.json with the gating cookie
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(json.dumps({
        "cookies": [{
            "name": "auth", "value": "ok",
            "domain": host, "path": "/",
            "expires": -1, "httpOnly": False,
            "secure": False, "sameSite": "Lax",
        }],
        "origins": []
    }))

    out_dir = tmp_path / "explore"
    script = PROJECT / "helpers" / "explore_page.py"
    proc = subprocess.run(
        ["uv", "run", str(script),
         f"{base}/protected",
         "--storage-state", str(auth_path),
         "--out-dir", str(out_dir),
         "--slug", "protected"],
        capture_output=True, text=True, timeout=120,
    )

    assert proc.returncode == 0, f"explore_page failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert (out_dir / "protected.png").exists()
    assert (out_dir / "protected.png").stat().st_size > 0
    dom = (out_dir / "protected.dom.html").read_text()
    assert "Protected content" in dom, f"DOM did not contain protected content:\n{dom[:500]}"
    meta = json.loads((out_dir / "protected.meta.json").read_text())
    assert meta["final_url"] == f"{base}/protected", meta
    assert meta["status"] == 200, meta


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
```

- [ ] **Step 6: Run the e2e test to verify it passes**

Run: `uv run tests/test_explore_page_e2e.py`

Expected: `1 passed` in ~5-15 seconds.

- [ ] **Step 7: Commit**

Write `/tmp/commit_msg_explore_page.txt`:

```
helpers: add explore_page.py for authenticated site exploration

One-shot Playwright helper that takes a URL + storage_state and writes
a screenshot + DOM + meta JSON. Lets the skill see authenticated pages
during Phase 2 exploration, not just during recording.

Tests:
- Unit: slug derivation (6 cases) + missing-state actionable error
- E2E: localhost cookie-gated server, hand-crafted auth.json, asserts
  the helper reaches /protected (status 200, DOM contains marker text)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Commit:
```bash
git add helpers/explore_page.py tests/test_explore_page.py tests/test_explore_page_e2e.py
git commit -F /tmp/commit_msg_explore_page.txt
```

---

### Task 2: SKILL.md restructure — Phase 2a + branching Phase 2

**Recommended tier:** Haiku (mechanical text restructuring, exact content provided).

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: Move the "Auth capture" sub-step from Phase 5 to a new Phase 2a**

In `SKILL.md`, find the existing "Auth capture (OAuth / SSO / magic-link only)" sub-section in Phase 5 (added in commit 574928d, located between Phase 5's main body and Phase 6 heading). DELETE that entire sub-section.

Then BETWEEN Phase 1 and the existing Phase 2 heading (which is currently `## Phase 2 — Site exploration`), INSERT this new Phase 2a:

```markdown
## Phase 2a — Auth capture (OAuth only)

Skip this phase entirely if Phase 1 question 7 settled on "no auth" or "form-based". For OAuth / SSO / magic-link / passkey, capture an authenticated session NOW, before site exploration — Phase 2b needs it to view authenticated pages.

```bash
mkdir -p ~/demo-videos/<demo-slug>/
uv run helpers/capture_auth.py <login_or_start_url> \
  --out ~/demo-videos/<demo-slug>/auth.json \
  --viewport <recording.viewport from demo_config.yaml; default 1440x900>
```

Run this via the Bash tool with `timeout: 600000` (10 minutes — the max). The script opens a headed Chromium window. Tell the user in plain words:

> "I'm opening a browser window for you to log in. Complete the login (Google, Microsoft, etc., handle 2FA), navigate to the page you want recording to start from, then close the browser window. I'll save the session and continue automatically."

The script writes `auth.json` with mode 0600 atomically. If the user takes longer than 10 minutes (rare, but possible with phone-based 2FA in another room), the Bash timeout fires — just re-run the same command.

`--viewport` MUST match `recording.viewport` in `demo_config.yaml`. Some sites fingerprint viewport size; mismatch can invalidate the captured session at record time or explore time.

If Playwright's Chromium isn't installed yet (fresh skill clone), the script surfaces an actionable error. Run `uv run --with playwright playwright install chromium` once.
```

(Note the doubled backticks in `\`\`\`bash` and `\`\`\`` are part of the file content. Preserve them.)

- [ ] **Step 2: Update Phase 2's heading and branching**

Find `## Phase 2 — Site exploration` (was line 35; new line depends on Phase 2a insertion). Replace this header AND the paragraph immediately after it with:

```markdown
## Phase 2b — Site exploration

If Phase 2a ran (auth.json exists), use `helpers/explore_page.py` to view authenticated pages — the Playwright MCP can't load storage_state and would just see login walls. For non-auth demos, the Playwright MCP is fine and more interactive; use it as before.

**For authenticated pages:**

```bash
mkdir -p ~/demo-videos/<demo-slug>/_explore/
uv run helpers/explore_page.py https://target.example.com/dashboard \
  --storage-state ~/demo-videos/<demo-slug>/auth.json \
  --out-dir ~/demo-videos/<demo-slug>/_explore/
```

This writes three files per page into `_explore/`: `<slug>.png` (screenshot), `<slug>.dom.html` (DOM for selector picking), `<slug>.meta.json` ({url_requested, final_url, title, status}). Read the PNG with the Read tool to see the page; grep the DOM for selectors. If `final_url` in meta.json points at a login page, the session expired — re-run Phase 2a.

**For public pages** (landing page, marketing pages on any demo; everything on a no-auth demo) — use the Playwright MCP tools (`mcp__plugin_playwright_playwright__*`) as before:

- `browser_navigate` to the target URL, then to 2–5 pages the user's intent mentions.
- `browser_snapshot` or `browser_take_screenshot` to see each page's layout.
- Use `browser_evaluate` to read DOM for stable selectors (prefer semantic over `nth-of-type` where possible).
```

Then preserve the rest of Phase 2's original content (the "Note for each significant page" bullets and the "Don't exhaustively crawl" note) untouched.

- [ ] **Step 3: Update Phase 5's reference to auth.json**

Phase 5 should still note that `auth.json` lives in the working dir, but no longer instruct running capture_auth.py (that's Phase 2a). Find the paragraph in Phase 5 that starts "Confirm `OPENAI_API_KEY` is available..." and replace its last sentence (about OAuth) so it reads:

```markdown
Confirm `OPENAI_API_KEY` is available (in the user's shell env or in `<working_dir>/.env`). If missing, ask the user to set it before running TTS. If form-based login is required, confirm any credential env-var names declared in `session.pre_session` are also set in `<working_dir>/.env`. If OAuth login is required, confirm `auth.json` is already present in the working dir from Phase 2a — if it's missing, re-run Phase 2a's capture step.
```

- [ ] **Step 4: Update Phase 1's question 7 cross-reference**

In Phase 1 question 7's OAuth branch, the current text says "during Phase 5 (see 'Auth capture' sub-step)". Update to point at Phase 2a:

Replace:
```markdown
   - **Yes, OAuth / SSO / magic-link / passkey** (Google, Microsoft, Okta, etc.) → use `session.storage_state`. The user does NOT run any commands. YOU launch `helpers/capture_auth.py` for them during Phase 5 (see "Auth capture" sub-step), and they only log in interactively in the browser window that opens. See `examples/oauth-storage-state/`.
```

With:
```markdown
   - **Yes, OAuth / SSO / magic-link / passkey** (Google, Microsoft, Okta, etc.) → use `session.storage_state`. The user does NOT run any commands. YOU launch `helpers/capture_auth.py` for them in Phase 2a, and they only log in interactively in the browser window that opens. The captured `auth.json` is then used for both Phase 2b exploration AND Phase 8 recording. See `examples/oauth-storage-state/`.
```

- [ ] **Step 5: Sanity-check phase ordering**

Run:
```bash
grep -n "^## Phase " SKILL.md
```

Expected order:
```
## Phase 1 — Interview
## Phase 2a — Auth capture (OAuth only)
## Phase 2b — Site exploration
## Phase 3 — Draft storyboard.yaml
## Phase 4 — Review in plain English
## Phase 5 — Working directory setup
## Phase 6 — Generate assets (badge)
## Phase 7 — TTS generation
## Phase 8 — Record
## Phase 9 — Mux + speed + brand + finalize
## Phase 10 — Verify ...
## Phase 11 — Hand off
```

- [ ] **Step 6: Commit**

Write `/tmp/commit_msg_skill_phase2a.txt`:

```
SKILL: split Phase 2 into 2a (auth capture) + 2b (exploration)

Auth state is now captured BEFORE site exploration, so the skill can
view authenticated pages during Phase 2b drafting — not just during
Phase 8 recording. Same single login moment for the user; just earlier.

- New Phase 2a "Auth capture (OAuth only)" — moved from Phase 5
- Phase 2 renamed to Phase 2b "Site exploration"; new branching at
  the top (auth pages via helpers/explore_page.py, public pages via
  Playwright MCP as before)
- Phase 5 no longer runs capture_auth.py; it just confirms auth.json
  exists from Phase 2a
- Phase 1 question 7 cross-reference updated to point at Phase 2a

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Commit:
```bash
git add SKILL.md
git commit -F /tmp/commit_msg_skill_phase2a.txt
```

---

### Task 3: CLAUDE.md + docs/SCHEMAS.md viewport-alignment update

**Recommended tier:** Haiku (mechanical doc edits, exact content provided).

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/SCHEMAS.md`

- [ ] **Step 1: Update `CLAUDE.md` viewport invariant**

In `CLAUDE.md`'s "Things you must preserve" list, REPLACE the existing bullet:

```markdown
- **Capture-record viewport match for `storage_state`.** `helpers/capture_auth.py` defaults to viewport 1440x900 — the recorder's default. If you change `recording.viewport` in a demo, pass the same `--viewport WxH` to capture_auth.py. Some sites fingerprint viewport size and will invalidate the captured session if it doesn't match at record time. The `examples/oauth-storage-state/README.md` documents this.
```

with the expanded:

```markdown
- **Capture/explore/record viewport alignment.** `helpers/capture_auth.py`, `helpers/explore_page.py`, and `scripts/record_demo.py` must all use the same viewport for a given demo. Default 1440x900 across all three. If a demo customizes `recording.viewport`, pass the same `--viewport WxH` to capture_auth.py AND explore_page.py. Some sites fingerprint viewport size between capture and use; mismatch invalidates the session.
```

- [ ] **Step 2: Update `docs/SCHEMAS.md` "Viewport match" paragraph**

In the `### \`session.storage_state\`` subsection (added in commit ea8ca56), find the "Viewport match" paragraph. REPLACE:

```markdown
**Viewport match.** `capture_auth.py` defaults to viewport 1440x900 (the
recorder default). If you customize `recording.viewport`, pass the same
size via `--viewport WxH` — some sites invalidate sessions when the
viewport changes.
```

with:

```markdown
**Viewport match.** `capture_auth.py` and `helpers/explore_page.py` both
default to viewport 1440x900 (the recorder default). If you customize
`recording.viewport`, pass the same size via `--viewport WxH` to BOTH —
some sites invalidate sessions when the viewport changes between capture,
explore, and record.
```

- [ ] **Step 3: Verify both files parse / display correctly**

Run:
```bash
grep -n "viewport alignment\|Viewport match" CLAUDE.md docs/SCHEMAS.md
```

Expected: one match in CLAUDE.md (the new bullet), one match in SCHEMAS.md (the updated paragraph).

- [ ] **Step 4: Commit**

Write `/tmp/commit_msg_viewport_align.txt`:

```
docs: extend viewport-alignment invariant to explore_page.py

Capture, explore, and record now all need matching viewports. Update
CLAUDE.md preserve invariant and SCHEMAS.md "Viewport match" paragraph
to reflect that helpers/explore_page.py joins the alignment requirement.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Commit:
```bash
git add CLAUDE.md docs/SCHEMAS.md
git commit -F /tmp/commit_msg_viewport_align.txt
```

---

## Verification (after all tasks complete)

1. `uv run tests/test_explore_page.py` — 7 passed (6 slug + 1 missing-state)
2. `uv run tests/test_explore_page_e2e.py` — 1 passed
3. `uv run tests/test_storage_state.py` — 4 passed (existing, unchanged)
4. `uv run tests/test_record_storage_state_e2e.py` — 1 passed (existing, unchanged)
5. `grep -n "^## Phase " SKILL.md` shows Phases 1 / 2a / 2b / 3-11 in order
6. `grep -n "Capture/explore/record" CLAUDE.md` shows the new invariant text
7. No remaining mentions of "Auth capture" in Phase 5 of SKILL.md

Then use `superpowers:finishing-a-development-branch`.

---

## Self-Review notes (controller)

**Spec coverage:**
- ✅ Phase 2a moves auth capture earlier → Task 2
- ✅ Phase 2b branches on auth presence → Task 2
- ✅ `helpers/explore_page.py` → Task 1
- ✅ Tests (unit + e2e) → Task 1
- ✅ CLAUDE.md alignment invariant updated → Task 3
- ✅ SCHEMAS.md viewport-match paragraph updated → Task 3
- ✅ Phase 5 cleanup (remove auth capture sub-step) → Task 2

**Type / name consistency:**
- `derive_slug(url: str) -> str` used identically in Tasks 1's unit test and helper.
- `--storage-state`, `--out-dir`, `--slug`, `--viewport` flag names consistent across helper, unit test, e2e test, SKILL.md.
- Phase 2a / 2b naming consistent across SKILL.md, Phase 1 cross-ref, and Phase 5 cross-ref.

**Placeholder scan:** none.
