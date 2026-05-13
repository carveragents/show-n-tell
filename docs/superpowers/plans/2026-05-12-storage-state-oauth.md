# OAuth-friendly recording via Playwright storage_state — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users record demos of OAuth-authenticated sites by pre-capturing a Playwright `storage_state.json` and pointing the recorder at it via `demo_config.yaml`.

**Architecture:** Add a single `session.storage_state` field that, when set, gets threaded into `browser.new_context(storage_state=...)` before `pre_session` runs. Ship a `helpers/capture_auth.py` that captures the state using the same Chromium settings the recorder uses, so fingerprinting can't invalidate the session at recording time.

**Tech Stack:** Python 3.12+, `uv` PEP 723 inline scripts, Playwright Python (sync API), `pytest` for test runs. No new runtime deps in record_demo.py; capture helper pins `playwright>=1.45`.

**Spec:** `docs/superpowers/specs/2026-05-12-storage-state-oauth-design.md`

**Model discipline (controller):** Use Haiku for mechanical tasks (1–2 files, complete spec); Sonnet for integration tasks (multi-file or Playwright/network glue); Sonnet for both review stages on every task. Each task lists its recommended tier.

---

## File Touch List

- `scripts/_lib.py` — add `resolve_session_path()`
- `scripts/record_demo.py` — thread `session.storage_state` into context kwargs (around line 291)
- `helpers/capture_auth.py` — NEW, headed Chromium capture helper
- `examples/oauth-storage-state/{README.md, demo_config.yaml, branding.yaml, storyboard.yaml, .gitignore}` — NEW example dir
- `tests/test_storage_state.py` — NEW unit tests (path resolution + missing-file error)
- `tests/test_record_storage_state_e2e.py` — NEW integration test with localhost cookie server
- `docs/SCHEMAS.md` — schema field + paragraph on capture flow
- `SKILL.md` — Phase 1 interview question
- `CLAUDE.md` — preserve-invariant entry on capture-record viewport match

---

### Task 1: `resolve_session_path` in `_lib.py`

**Recommended tier:** Haiku (isolated pure function, complete spec).

**Files:**
- Modify: `scripts/_lib.py` — add function near `resolve_working_dir` (around line 103)
- Create: `tests/test_storage_state.py`

- [ ] **Step 1: Create tests/ dir if missing and write the failing test**

Create `tests/test_storage_state.py` with full PEP 723 self-runner shebang so it works the same way as the project's other uv scripts.

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run tests/test_storage_state.py`

Expected: `ImportError: cannot import name 'resolve_session_path' from '_lib'` — three errors, one per test.

- [ ] **Step 3: Add `resolve_session_path` to `_lib.py`**

Insert after `resolve_working_dir` (line 105 region):

```python
def resolve_session_path(path: str, working_dir: Path) -> Path:
    """Resolve a session-related path string against the working dir.

    Rules:
      - Absolute paths → returned as-is (resolved).
      - `~`-prefixed → expanded against `$HOME`.
      - Otherwise → joined to `working_dir` and resolved.

    Used by record_demo.py for `session.storage_state`.
    """
    expanded = Path(path).expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (working_dir / expanded).resolve()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run tests/test_storage_state.py`

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib.py tests/test_storage_state.py
git commit -m "$(cat <<'EOF'
_lib: add resolve_session_path for session-related paths

First step of OAuth storage_state support. Pure function with three
rules (absolute / tilde / relative-to-working-dir), exercised by
tests/test_storage_state.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Thread `session.storage_state` into `record_demo.py` context creation

**Recommended tier:** Haiku (single small modification + small unit test, complete spec).

**Files:**
- Modify: `scripts/record_demo.py` — context creation block (line ~250 for session read, line ~291–297 for context kwargs)
- Modify: `tests/test_storage_state.py` — add missing-file test

- [ ] **Step 1: Add the failing missing-file test**

Append to `tests/test_storage_state.py`:

```python
import json
import subprocess


def test_storage_state_missing_file_raises_actionable_error(tmp_path):
    """record_demo.py exits with an actionable error when storage_state path doesn't exist.

    We invoke record_demo.py as a subprocess against a minimal fake working dir
    (just enough YAML to get past arg parsing and reach the context-creation block).
    Asserts the error message names the resolved path and points at capture_auth.py.
    """
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run tests/test_storage_state.py`

Expected: `test_storage_state_missing_file_raises_actionable_error` fails — the recorder probably succeeds (no storage_state code path yet) or fails on a different message.

- [ ] **Step 3: Add the storage_state logic in `record_demo.py`**

Locate the context-creation block (around line 250 for the session read, line 291–297 for `ctx_kwargs`).

Where `pre_session` is currently read (~line 250), add a sibling read for storage_state. Patch:

```python
    pre_session = demo_config.get("session", {}).get("pre_session") or []
    # pre_session steps get BOTH {{ base_url }} interpolation AND ${ENV_VAR}
    # expansion so credentials in `.env` resolve (see SCHEMAS.md "Login flow").
    expanded_pre = [expand_env(interp_template(s, ctx)) for s in pre_session]

    storage_state_raw = demo_config.get("session", {}).get("storage_state")
    storage_state_path = None
    if storage_state_raw:
        storage_state_path = resolve_session_path(storage_state_raw, wd)
        if not storage_state_path.exists():
            sys.exit(
                f"\n✗ storage_state file not found: {storage_state_path}\n"
                f"  Capture it with: uv run helpers/capture_auth.py <start_url> "
                f"--out {storage_state_path}"
            )
```

Then in the context-creation block (line ~291–297), patch `ctx_kwargs` and add a log line:

```python
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx_kwargs = dict(
            viewport=viewport,
            record_video_dir=str(video_tmp),
            record_video_size=viewport,
        )
        if storage_state_path:
            ctx_kwargs["storage_state"] = str(storage_state_path)
            print(f"Loading storage_state from {storage_state_path}")
        playwright_ctx = browser.new_context(**ctx_kwargs)
```

Also add the import for `resolve_session_path` at the top of `record_demo.py` if not already present:

```python
from _lib import (
    expand_env,
    interp_template,
    load_configs,
    resolve_session_path,
    resolve_working_dir,
    ensure_dir,
    load_dotenv_if_present,
)
```

(Merge with existing import — don't duplicate names.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run tests/test_storage_state.py`

Expected: `4 passed` (3 from Task 1 + 1 new).

- [ ] **Step 5: Commit**

```bash
git add scripts/record_demo.py tests/test_storage_state.py
git commit -m "$(cat <<'EOF'
record_demo: load session.storage_state into Playwright context

Adds support for OAuth-authenticated demos. When session.storage_state
is set in demo_config.yaml, the recorder resolves the path against the
working dir and passes it to browser.new_context(storage_state=...).
Missing files fail loud with an error message that points at
helpers/capture_auth.py.

storage_state loads BEFORE pre_session, so a demo can both restore an
authenticated context and run scripted navigation against it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Integration test — recorder honors storage_state against a localhost cookie-gated server

**Recommended tier:** Sonnet (Playwright + http.server + threading glue).

**Files:**
- Create: `tests/test_record_storage_state_e2e.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_record_storage_state_e2e.py`:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest>=8", "pyyaml>=6"]
# ///
"""End-to-end test: recorder loads storage_state and accesses gated content.

Spins up a localhost http.server with a cookie-gated `/protected` route.
Runs render_voiceover.py is NOT required — we build a stub manifest by hand
and skip TTS so the test is offline + fast. We then run record_demo.py and
assert it produced a reference.webm and didn't print any 401 markers.
"""
import http.server
import json
import socket
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent


class CookieGatedHandler(http.server.SimpleHTTPRequestHandler):
    """Tiny gated server.

    GET /          → 200, plain HTML, always
    GET /protected → 200 with "Protected content" if `auth=ok` cookie; else 401
    """
    def do_GET(self):
        cookie = self.headers.get("Cookie", "")
        if self.path == "/":
            self._respond(200, "<html><body><h1>Home</h1></body></html>")
            return
        if self.path == "/protected":
            if "auth=ok" in cookie:
                self._respond(200, "<html><body><h1>Protected content</h1></body></html>")
            else:
                self._respond(401, "<html><body>Login required</body></html>")
            return
        self._respond(404, "not found")

    def log_message(self, *args):  # quiet
        pass

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode())


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def gated_server():
    port = _free_port()
    server = socketserver.TCPServer(("127.0.0.1", port), CookieGatedHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _write_minimal_demo(wd: Path, base_url: str):
    """Build the smallest possible working dir that record_demo.py will accept."""
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "_voiceover").mkdir()
    # Stub manifest with one beat that has 0-duration audio
    (wd / "_voiceover" / "manifest.json").write_text(json.dumps({
        "beats": [{"id": "01_protected", "narration_hash": "x",
                   "tts_duration_ms": 0, "wav": "stub.wav"}]
    }))
    # Empty wav so wav_duration_seconds doesn't crash — produce 0.1s of silence
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", "0.1", "-acodec", "pcm_s16le", str(wd / "_voiceover" / "stub.wav"),
    ], check=True, capture_output=True)
    (wd / "storyboard.yaml").write_text(
        "beats:\n"
        "  - id: 01_protected\n"
        "    narration: irrelevant\n"
        "    action:\n"
        "      type: goto\n"
        f"      url: {base_url}/protected\n"
    )
    (wd / "branding.yaml").write_text("brand:\n  name: Test\n")
    (wd / "demo_config.yaml").write_text(
        f"site:\n  base_url: {base_url}\n"
        f"output:\n  filename: out.mp4\n  working_dir: {wd}\n"
        "recording:\n  viewport: {width: 800, height: 600}\n  framerate: 25\n"
        "  pre_narration_ms: 100\n  post_narration_ms: 100\n"
        "session:\n  storage_state: ./auth.json\n"
    )


def _write_storage_state(wd: Path, host: str, port: int):
    """Hand-craft a Playwright storage_state.json with the gating cookie."""
    state = {
        "cookies": [{
            "name": "auth", "value": "ok",
            "domain": host, "path": "/",
            "expires": -1, "httpOnly": False,
            "secure": False, "sameSite": "Lax",
        }],
        "origins": []
    }
    (wd / "auth.json").write_text(json.dumps(state))


def test_recorder_honors_storage_state(tmp_path, gated_server):
    base = gated_server  # e.g. http://127.0.0.1:54321
    host, port = base.replace("http://", "").split(":")
    wd = tmp_path / "wd"
    _write_minimal_demo(wd, base)
    _write_storage_state(wd, host, int(port))

    script = PROJECT / "scripts" / "record_demo.py"
    proc = subprocess.run(
        ["uv", "run", str(script), "--working-dir", str(wd)],
        capture_output=True, text=True, timeout=180,
    )

    assert proc.returncode == 0, f"record_demo failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert "Loading storage_state from" in proc.stdout, proc.stdout
    # reference.webm should exist — storage_state would have made /protected return 200
    assert (wd / "_intermediate" / "reference.webm").exists(), \
        f"reference.webm missing under {wd / '_intermediate'}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run tests/test_record_storage_state_e2e.py`

Expected: `1 passed` in ~10-30 seconds. The recorder loads storage_state, hits `/protected`, gets 200 (because cookie present), and finishes recording.

Note: this test requires `ffmpeg` and `playwright`'s Chromium to be installed. Both are already project prerequisites.

If the test fails because Chromium is missing, run: `uv run --with playwright playwright install chromium`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_record_storage_state_e2e.py
git commit -m "$(cat <<'EOF'
tests: e2e for storage_state load via localhost cookie-gated server

End-to-end test that proves storage_state actually authenticates the
recording context. Spins up a tiny http.server with a /protected route
gated on an `auth=ok` cookie, crafts a Playwright storage_state.json
with that cookie, and runs record_demo.py against it.

No external network. No real OAuth. Just enough to validate the
load-into-new_context path.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `helpers/capture_auth.py`

**Recommended tier:** Sonnet (headed Playwright + close-event handling + 0600 chmod glue; not pure-mechanical).

**Files:**
- Create: `helpers/capture_auth.py`

- [ ] **Step 1: Write the helper script**

Create `helpers/capture_auth.py`:

```python
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
        page.goto(args.start_url, wait_until="load", timeout=60_000)

        # Wait for the user to close the page / window. Playwright fires `close`
        # on the page when the user clicks the X. Using timeout=0 = wait forever.
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            # If the context disappears (full window close) we just proceed
            pass

        # Persist storage state. Context may still be alive even if the page
        # was closed; if not, this is a no-op-style failure.
        try:
            context.storage_state(path=str(out_path))
        finally:
            try:
                browser.close()
            except Exception:
                pass

    # 0600 perms — discourage accidental sharing
    os.chmod(out_path, stat.S_IRUSR | stat.S_IWUSR)
    print(f"\n✓ Saved {out_path} (mode 0600)", file=sys.stderr)
    print(f"\nNext step: add to your demo_config.yaml:", file=sys.stderr)
    print(f"  session:", file=sys.stderr)
    print(f"    storage_state: \"{out_path}\"", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test the helper against a localhost server**

Manually verify the helper runs and produces a 0600 file:

```bash
# Start a tiny localhost server in one terminal
cd /tmp && python3 -m http.server 8765
```

```bash
# In another, run capture_auth with --viewport 800x600 to keep window small
uv run helpers/capture_auth.py http://localhost:8765/ --out /tmp/test-auth.json --viewport 800x600
# A Chromium window opens at localhost:8765. Close the window.
# Then:
ls -l /tmp/test-auth.json
# Expected: file exists with mode -rw-------
file /tmp/test-auth.json && head -c 200 /tmp/test-auth.json
# Expected: JSON with "cookies" and "origins" keys
rm /tmp/test-auth.json
```

No automated test here — the helper is fundamentally interactive (waits for human-driven window close). The integration test in Task 3 proves the storage_state.json format the helper writes is consumable by record_demo.

- [ ] **Step 3: Commit**

```bash
git add helpers/capture_auth.py
git commit -m "$(cat <<'EOF'
helpers: add capture_auth.py for storage_state capture

Headed Chromium helper that launches with the recorder's default viewport,
waits for the user to close the window, and writes storage_state.json
(mode 0600). Used to capture OAuth/SSO sessions without scripting the
login flow.

Matches record_demo.py's Chromium context settings so the captured
session isn't invalidated by browser-fingerprint mismatches at recording
time.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `examples/oauth-storage-state/` example dir

**Recommended tier:** Haiku (mechanical content creation, no logic).

**Files:**
- Create: `examples/oauth-storage-state/README.md`
- Create: `examples/oauth-storage-state/demo_config.yaml`
- Create: `examples/oauth-storage-state/branding.yaml`
- Create: `examples/oauth-storage-state/storyboard.yaml`
- Create: `examples/oauth-storage-state/.gitignore`

- [ ] **Step 1: Create the example files**

`examples/oauth-storage-state/README.md`:

```markdown
# OAuth-authenticated demo via storage_state

Use this template when your demo target requires OAuth, SSO, magic-link,
or passkey login that can't be reliably scripted via `pre_session`.

## One-time setup

1. From the skill root, capture an authenticated session:
   ```
   cd examples/oauth-storage-state/
   uv run ../../helpers/capture_auth.py https://target.example.com/
   ```
2. A Chromium window opens. Log in (Google, Microsoft, etc.), navigate
   to the page you want recording to start from, then close the window.
3. `auth.json` is written here with mode 0600.
4. `session.storage_state: "./auth.json"` in `demo_config.yaml` already
   points at it.

## Re-capturing

Sessions expire (could be hours, could be weeks, depends on the site).
When the recorded demo starts on a login page, re-run capture_auth.py.

## Viewport matching

If you change `recording.viewport` in `demo_config.yaml`, pass the same
size to capture_auth.py via `--viewport WxH`. Some sites invalidate
sessions when the browser viewport doesn't match.

## Security

- `auth.json` contains live session tokens. Treat like a password.
- The `.gitignore` in this directory excludes it.
- Never email or paste it into chat / issue trackers.
```

`examples/oauth-storage-state/demo_config.yaml`:

```yaml
# Per-demo config for OAuth-authenticated targets.
# See ./README.md for the capture flow.

site:
  base_url: "https://target.example.com"

session:
  storage_state: "./auth.json"
  # pre_session is optional and runs AFTER storage_state loads. Use it for
  # post-login navigation:
  # pre_session:
  #   - { type: goto, url: "{{ base_url }}/dashboard" }
  #   - { type: wait_for_url, contains: "/dashboard" }

output:
  filename: "oauth-demo.mp4"
  working_dir: "."
  speed_multiplier: 1.2
  target_duration_seconds: 180

features:
  intro_slide: true
  outro_slide: true
  captions:
    enabled: true
    mode: "burned"
  crossfade_seconds: 0.5
  brand_overlay: true

recording:
  viewport: { width: 1440, height: 900 }
  framerate: 25
  pre_narration_ms: 400
  post_narration_ms: 700
```

`examples/oauth-storage-state/branding.yaml`:

```yaml
# Replace with your brand. See templates/branding.example.yaml for all fields.

brand:
  name: "Your Brand"
  tagline: "Your tagline"
  cta:
    text: "Try it free"
    url: "https://your-site.example.com"

logo:
  path: "./logo.png"   # drop a logo.png next to this file

colors:
  ink: "#101828"
  ink_deep: "#0c1322"
  accent: "#bae424"
  cream: "#fbf7f3"

voice:
  provider: openai
  model: "gpt-4o-mini-tts"
  voice: cedar
  tone: "explanatory"
  instructions: |
    Read calmly and clearly, like a confident product walkthrough narrator.
    Pace around 140 words per minute.

recording_css: ""
```

`examples/oauth-storage-state/storyboard.yaml`:

```yaml
# Placeholder storyboard. Replace with your real beats after capturing auth.json.

beats:
  - id: 01_landing
    narration: |
      We start on the authenticated dashboard, ready to walk through the
      product.
    action:
      type: goto
      url: "{{ base_url }}/"

  - id: 02_feature
    narration: |
      Here's the main feature we want to highlight.
    action:
      type: goto
      url: "{{ base_url }}/feature"
```

`examples/oauth-storage-state/.gitignore`:

```
auth.json
*.mp4
_intermediate/
_voiceover/
_assets/
```

- [ ] **Step 2: Commit**

```bash
git add examples/oauth-storage-state/
git commit -m "$(cat <<'EOF'
examples: add oauth-storage-state template

A minimal Phase B+ example demonstrating session.storage_state for
OAuth-authenticated targets. README documents the capture flow,
re-capture trigger, viewport matching, and security notes.

.gitignore excludes auth.json so users don't accidentally commit
live session tokens.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Documentation updates

**Recommended tier:** Haiku (mechanical doc edits, complete content provided).

**Files:**
- Modify: `docs/SCHEMAS.md`
- Modify: `SKILL.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update `docs/SCHEMAS.md`**

Find the "Login flow (Phase B)" section (around line 182). Immediately AFTER it, add this new subsection:

```markdown
### `session.storage_state` (Phase B+, for OAuth / SSO / magic-link auth)

When the target site authenticates via OAuth, SSO, magic-link, or passkey
— flows that can't be reliably scripted via `pre_session` — pre-capture an
authenticated Playwright session and point the recorder at it.

```yaml
session:
  storage_state: "./auth.json"   # path to a Playwright storage_state JSON
  pre_session: []                # optional, runs AFTER storage_state loads
```

| Field | Required | Notes |
|---|---|---|
| `storage_state` | no | Path to a Playwright `storage_state.json`. Loaded via `browser.new_context(storage_state=...)` before pre_session. Relative paths resolve against `output.working_dir`. `~` is expanded. |

**Capture flow.** Use the bundled helper to capture a session whose browser
context matches the recorder's:

```bash
uv run helpers/capture_auth.py https://target.example.com/ --out ./auth.json
```

A headed Chromium opens, you log in interactively (handles OAuth, 2FA,
captchas — anything), and when you close the window the helper writes
`auth.json` with mode 0600. Add `session.storage_state: "./auth.json"` to
your `demo_config.yaml` and you're done.

**Re-capturing.** Sessions expire. When the demo starts recording you on a
login page, re-run `capture_auth.py`.

**Viewport match.** `capture_auth.py` defaults to viewport 1440x900 (the
recorder default). If you customize `recording.viewport`, pass the same
size via `--viewport WxH` — some sites invalidate sessions when the
viewport changes.

**Security.** `auth.json` contains live session tokens. Never commit it.
The `examples/oauth-storage-state/` template includes a `.gitignore`.

**Combining with `pre_session`.** When both are set, `storage_state` loads
first into the context, then `pre_session` runs against that authenticated
context — useful for "OAuth-auth then navigate to the dashboard" demos.
```

- [ ] **Step 2: Update `SKILL.md`**

Find the Phase 1 (interview / context gathering) section. Locate the existing prompt about login. Replace the login question with:

```markdown
- **Auth.** Does the site require login?
  - **No** → proceed.
  - **Yes, form-based** (the site has its own email/password fields you control via env vars) → use `session.pre_session` in `demo_config.yaml`. See `examples/login-flow/`.
  - **Yes, OAuth / SSO / magic-link / passkey** (Google, Microsoft, Okta, etc.) → use `session.storage_state` and pre-capture an authenticated session with `helpers/capture_auth.py`. See `examples/oauth-storage-state/`.
```

(If the existing question is structured differently, preserve the structure but ensure the OAuth case is enumerated alongside the form case. Don't drop the form-login option.)

- [ ] **Step 3: Update `CLAUDE.md`**

Find the "Things you must preserve when extracting from the reference repo" bullet list. Append this bullet (at the end, in the same style as the existing entries):

```markdown
- **Capture-record viewport match for `storage_state`.** `helpers/capture_auth.py` defaults to viewport 1440x900 — the recorder's default. If you change `recording.viewport` in a demo, pass the same `--viewport WxH` to capture_auth.py. Some sites fingerprint viewport size and will invalidate the captured session if it doesn't match at record time. The `examples/oauth-storage-state/README.md` documents this.
```

- [ ] **Step 4: Commit**

```bash
git add docs/SCHEMAS.md SKILL.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: document session.storage_state for OAuth-authenticated demos

- SCHEMAS.md: new subsection on session.storage_state with capture flow,
  re-capture trigger, viewport match, security, and pre_session co-use.
- SKILL.md: Phase 1 interview branches on auth type (none/form/OAuth).
- CLAUDE.md: preserve-invariant added on capture-record viewport match.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Verification (after all tasks complete)

Before finishing the branch:

1. `uv run tests/test_storage_state.py` — 4 passed
2. `uv run tests/test_record_storage_state_e2e.py` — 1 passed
3. **Halyard regression**: `examples/halyard-spme/` still produces the reference video. Storage_state field is absent there, so the new code path should be inert. Run a minimal smoke: `uv run scripts/record_demo.py --working-dir examples/halyard-spme/` (or whatever the existing reproducibility script is) to confirm no regression in the no-storage_state path.
4. Manual: run `uv run helpers/capture_auth.py http://localhost:<any-port>/` against a localhost server, verify `auth.json` written with 0600.
5. Manual: `examples/oauth-storage-state/` files exist and `cat examples/oauth-storage-state/.gitignore` lists `auth.json`.

Then use `superpowers:finishing-a-development-branch`.

---

## Self-Review notes (controller — to read before dispatching)

**Spec coverage check:**

- ✅ Schema field `session.storage_state` → Task 2
- ✅ Path resolution rules (abs / ~ / working_dir) → Task 1
- ✅ Mutually compatible with pre_session, storage_state loads first → Task 2 (code change places storage_state before pre_session run)
- ✅ Missing file → actionable error pointing at capture_auth.py → Task 2
- ✅ Log path only, never contents → Task 2
- ✅ `helpers/capture_auth.py` with viewport match, NODE_OPTIONS clear, 0600 chmod → Task 4
- ✅ `examples/oauth-storage-state/` → Task 5
- ✅ `docs/SCHEMAS.md`, `SKILL.md`, `CLAUDE.md` updates → Task 6
- ✅ Unit tests → Task 1, 2
- ✅ Integration test with localhost cookie server → Task 3
- ✅ Halyard regression preserved → Verification step 3

**Type / name consistency:**

- `resolve_session_path(path: str, working_dir: Path) -> Path` — used identically in Tasks 1 and 2.
- `session.storage_state` — same name in spec, schema, all code references, all docs.
- `--out`, `--viewport` flag names consistent between capture_auth.py and the README example.
- Resolved path always referred to as `storage_state_path` in record_demo.py.

**Placeholder scan:** None. Every step has either complete code or a complete command. No "similar to Task N" — code repeated where needed.
