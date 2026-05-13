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
