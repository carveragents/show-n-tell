# OAuth-friendly recording via Playwright `storage_state`

**Status:** Approved 2026-05-12
**Author:** Claude (Opus 4.7) with achint
**Phase:** B+ (enhancement to existing Phase B auth story)

## Problem

The skill's only auth mechanism today is `session.pre_session` — a list of `goto` / `fill` / `click` / `wait_for_url` actions that scripts a form login at recording time. This works for first-party form logins, but fails for OAuth / SSO flows in two common cases:

1. **Third-party identity providers** (Google, Microsoft, Apple). The user does not control these — they can't add a test-login backdoor. Real OAuth flows trigger 2FA, device verification, captchas, and bot-detection on Playwright. Scripting them is brittle and frequently account-locks the user.

2. **Magic-link / passkey auth.** The credential is not a static string; it's a per-attempt token. There is no `value` to put in a YAML `fill` step.

A workable design today exists in Playwright itself: `storage_state.json` captures an authenticated context's cookies + localStorage. You log in once interactively, save the state, and reuse it across runs until the session expires.

## Goal

Let users record demos of sites where they authenticate via OAuth, by pre-capturing a Playwright `storage_state.json` and pointing the recorder at it. Provide a capture helper that uses the same Chromium context as recording, so the auth state is not invalidated by browser-fingerprint mismatches.

## Non-goals

- Automating real Google / Microsoft / SSO login flows. Not feasible.
- Auto-detecting expired sessions during recording. The user re-captures when their demo fails. (May revisit if it becomes a frequent pain point.)
- Programmatic OAuth via API tokens. Out of scope; site-specific.

## Design

### YAML schema addition

```yaml
# demo_config.yaml
session:
  storage_state: "./auth.json"   # NEW — optional
  pre_session: []                # Existing, unchanged
```

**Field:** `session.storage_state`
- **Type:** string (path)
- **Required:** no
- **Path resolution:** relative to `output.working_dir` if not absolute; `~` expanded
- **Mutually compatible with `pre_session`:** if both set, `storage_state` loads first into the context, then `pre_session` actions run against that already-authenticated context.

### Recorder change

In `scripts/record_demo.py`, in the block that creates the Playwright context:

```python
context_kwargs = {
    "viewport": viewport,
    "record_video_dir": str(video_dir),
    "record_video_size": viewport,
}
storage_state_path = session.get("storage_state")
if storage_state_path:
    resolved = resolve_session_path(storage_state_path, working_dir)
    if not resolved.exists():
        raise FileNotFoundError(
            f"storage_state file not found: {resolved}\n"
            f"Capture it with: uv run helpers/capture_auth.py <start_url> --out {resolved}"
        )
    context_kwargs["storage_state"] = str(resolved)
    log.info("Loading storage_state from %s", resolved)
context = browser.new_context(**context_kwargs)
```

- Log the **path only**, never the file contents.
- Use `raise ... from None` if catching an underlying OSError, to avoid leaking path/contents through `__cause__`.

### Shared helper: `scripts/_lib.py`

Add a small utility used by both `record_demo.py` (storage_state) and pre_session path handling:

```python
def resolve_session_path(path: str, working_dir: Path) -> Path:
    """Resolve a session-related path. Absolute → as-is; ~ → home; else → relative to working_dir."""
    expanded = Path(path).expanduser()
    if expanded.is_absolute():
        return expanded
    return (working_dir / expanded).resolve()
```

### New helper: `helpers/capture_auth.py`

PEP 723 uv-runnable script. Launches headed Chromium with the recorder's default context settings, navigates to a start URL, waits for the user to finish logging in and close the window, then writes `storage_state.json`.

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.45"]
# ///
"""
Capture a Playwright storage_state.json for a demo recording.

Usage:
  uv run helpers/capture_auth.py <start_url> [--out PATH] [--viewport WxH]

Defaults match scripts/record_demo.py: viewport 1440x900, Chromium, no UA override.
"""
import argparse, os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    p = argparse.ArgumentParser()
    p.add_argument("start_url")
    p.add_argument("--out", default="auth.json")
    p.add_argument("--viewport", default="1440x900")
    args = p.parse_args()

    w, h = (int(x) for x in args.viewport.split("x"))
    out_path = Path(args.out).expanduser().resolve()

    # cmux NODE_OPTIONS workaround (same as record_demo.py)
    if os.environ.get("NODE_OPTIONS"):
        os.environ.pop("NODE_OPTIONS", None)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": w, "height": h})
        page = context.new_page()
        page.goto(args.start_url)
        print(f"\nLog in in the browser window. When you're done and on the page "
              f"you want recording to start from, close the window.\n", file=sys.stderr)

        # Wait for the user to close the browser
        page.wait_for_event("close", timeout=0)

        context.storage_state(path=str(out_path))
        os.chmod(out_path, 0o600)
        print(f"Saved {out_path} (mode 0600)")
        print(f"\nNext step: add to demo_config.yaml:\n  session:\n    storage_state: \"{out_path}\"")

if __name__ == "__main__":
    main()
```

Behavior details:
- **Headed Chromium** — user needs to see the OAuth flow.
- **Viewport matches recorder.** Default 1440x900; overrideable via flag.
- **NODE_OPTIONS auto-clear** — same cmux workaround as `record_demo.py` (see `docs/GOTCHAS.md`).
- **No UA override.** Playwright's default Chromium UA is used. If a target site is UA-fingerprinting, the user can pass `--ua "..."` in a future version; YAGNI for now.
- **0600 file mode** on the output to discourage accidental sharing.
- **Window-close signals done** rather than asking the user to hit Enter in the terminal — closing the browser is the natural "I'm finished logging in" gesture.

### New example: `examples/oauth-storage-state/`

Mirrors `examples/login-flow/`:

```
examples/oauth-storage-state/
  README.md           — manual capture step, expiry, security notes
  demo_config.yaml    — session.storage_state: "./auth.json", no pre_session
  branding.yaml       — minimal placeholders
  storyboard.yaml     — 2 beats: goto /, then goto /protected-route
  .gitignore          — excludes auth.json
```

`README.md` content:

```markdown
# OAuth login via storage_state

Use this when your demo target requires OAuth / SSO / passkey login that
can't be scripted reliably.

## One-time setup

1. Capture an authenticated session:
   ```
   uv run helpers/capture_auth.py https://target.example.com/
   ```
2. A Chromium window opens. Log in (Google, Microsoft, etc.), navigate
   to the page you want recording to start from, then close the window.
3. `auth.json` is written to the current directory with mode 0600.
4. Set `session.storage_state` in `demo_config.yaml` to point at it.

## Re-capturing

Sessions expire. When the demo starts recording you on a login page,
re-run capture_auth.py.

## Security

- Never commit `auth.json` to version control.
- It contains live session tokens. Treat like a password.
- The `.gitignore` in this example excludes it.
```

### Documentation updates

**`docs/SCHEMAS.md`** — add to the session block:

| Field | Required | Notes |
|---|---|---|
| `storage_state` | no | Path to a Playwright storage_state.json. Loaded into the recording context before pre_session. Relative paths resolve against working_dir. Mutually compatible with pre_session. |

Plus a paragraph explaining the capture flow and pointing at `helpers/capture_auth.py`.

**`SKILL.md`** — Phase 1 interview gets one more question:

> If the site requires login, ask: form-based (script via `pre_session`) or OAuth/SSO/passkey (capture via `helpers/capture_auth.py` and use `storage_state`)?

**`CLAUDE.md` "Things you must preserve"** — add:

> **Capture-record viewport match** for storage_state. `helpers/capture_auth.py` defaults to the recorder's viewport (1440x900). If a user customizes `recording.viewport`, they must pass `--viewport` to the capture helper too, or session may be invalidated by Chromium reporting a different viewport. The example README documents this.

## Testing

### Unit — `tests/test_storage_state_resolution.py`

1. `resolve_session_path("./auth.json", working_dir)` returns `working_dir / auth.json` resolved.
2. `resolve_session_path("/abs/auth.json", working_dir)` returns `/abs/auth.json`.
3. `resolve_session_path("~/auth.json", working_dir)` returns `$HOME/auth.json`.
4. `record_demo` with `session.storage_state` set to a non-existent file → raises `FileNotFoundError` whose message contains the resolved path AND `helpers/capture_auth.py`.

### Integration — `tests/test_record_storage_state_e2e.py`

End-to-end test using a localhost cookie-gated server. No external network, no real OAuth.

1. Spin up a `http.server.BaseHTTPRequestHandler` subclass in a thread:
   - `GET /` → returns a "Login required" page if no `auth=ok` cookie, else returns "Welcome".
   - `GET /protected` → 401 without cookie, "Protected content" with.
2. Craft a fixture `auth.json`:
   ```json
   {
     "cookies": [{"name": "auth", "value": "ok", "domain": "127.0.0.1", "path": "/", "expires": -1, "httpOnly": false, "secure": false, "sameSite": "Lax"}],
     "origins": []
   }
   ```
3. Build a tiny `storyboard.yaml` with one beat `goto {{ base_url }}/protected`.
4. Run `record_demo.py` end-to-end.
5. Assert: the recorder did not error, and the recorded video file exists. (Frame-level pixel inspection is overkill; reaching `/protected` without 401 is enough proof storage_state loaded.)

### Manual — Halyard reproducibility

The existing `examples/halyard-spme/` regression test must still pass (no storage_state, no pre_session). The change is additive; an absent `storage_state` field means no behavior change.

## Implementation order

1. `scripts/_lib.py` — `resolve_session_path()` + unit tests.
2. `scripts/record_demo.py` — thread `storage_state` into `new_context()` + unit test for missing-file error.
3. `helpers/capture_auth.py` — new script. Smoke test: run against localhost server, verify file is written with 0600.
4. `examples/oauth-storage-state/` — new example dir.
5. `tests/test_record_storage_state_e2e.py` — integration test with localhost cookie server.
6. Docs: `docs/SCHEMAS.md`, `SKILL.md`, `CLAUDE.md`.

Each step gets its own commit. Implementer (Haiku) implements; reviewers (Sonnet) verify spec compliance then code quality.

## Open questions

None at design time. The user has approved this design. Any ambiguity discovered during implementation is escalated via BLOCKED.
