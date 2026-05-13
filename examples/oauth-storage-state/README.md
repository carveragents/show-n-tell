# OAuth-authenticated demo via storage_state

Use this template when your demo target requires OAuth, SSO, magic-link,
or passkey login that can't be reliably scripted via `pre_session`.

## How it works

Playwright can save a fully-authenticated browser context to a JSON file
(`auth.json`) — cookies + localStorage — and load it back into a fresh
context later. So instead of scripting the OAuth flow (brittle, often
blocked by Google), you log in once interactively, and the recorder
re-uses that session every time.

## Running through the skill (recommended)

When you're running the skill via Claude Code, you don't run any commands.
During Phase 5 (working directory setup), Claude launches
`helpers/capture_auth.py` for you. A Chromium window opens; you log in
(Google, Microsoft, whatever — handle 2FA normally), navigate to the page
you want recording to start from, and close the window. Claude saves
`auth.json` into the working dir and continues with TTS + recording.

## Running manually (when the skill isn't driving)

If you're setting up a working dir by hand:

1. From the skill root, capture an authenticated session:
   ```
   cd examples/oauth-storage-state/
   uv run ../../helpers/capture_auth.py https://target.example.com/
   ```
2. A Chromium window opens. Log in, navigate to the page you want
   recording to start from, then close the window.
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
