# Login-flow reference example

A 5-beat demo of a (fictional) authenticated SaaS app, showing the canonical
shape of a `session.pre_session` login block.

This example is **structural, not runnable**. The URLs (`{{ base_url }}/login`,
`/dashboard`, `/projects`, `/reports`, `/settings`) and selectors
(`input[name=email]`, `button[type=submit]`, `[data-testid='filter-env-prod']`,
…) reference a placeholder "Acme Cloud" app that does not exist. Adapt them to
your real target site before recording.

## How to use as a template

1. Copy this directory to your working dir:
   ```bash
   cp -r examples/login-flow ~/demo-videos/my-app-demo
   cp examples/login-flow/.env.example ~/demo-videos/my-app-demo/.env
   ```
2. Edit `demo_config.yaml`:
   - Set `site.base_url` to your real app URL.
   - Update the `session.pre_session` selectors to match your login form's
     actual `name=` / `data-testid=` attributes.
   - Change the redirect check (`wait_for_url: /dashboard`) to whatever path
     your app lands on after a successful login.
3. Edit `storyboard.yaml`:
   - Rewrite each beat's URL + selector + narration to walk through your
     app's post-login pages.
4. Edit `branding.yaml`:
   - Replace the brand name, tagline, CTA, colors, and `_assets/<logo>.png`
     with your real brand assets.
5. Fill in `~/demo-videos/my-app-demo/.env` with real credentials. Use a
   dedicated demo account, never a real human's login.
6. Run the full pipeline (see project root `SKILL.md`).

## Credential hygiene

- Credentials live in `.env`, which is git-ignored. Never put real passwords
  in `demo_config.yaml`.
- `record_demo.py` masks `fill.value` to `***` in stdout for pre-session
  steps, so secrets pulled from `${ENV_VAR}` don't appear in logs even on
  failure.
- The env-var naming convention `<BRAND>_DEMO_<FIELD>` (e.g. `ACME_DEMO_EMAIL`)
  lets multiple demos coexist on one machine without clobbering each other's
  secrets.

## Files

| File                | Purpose                                                  |
|---------------------|----------------------------------------------------------|
| `storyboard.yaml`   | 5 beats walking the post-login app.                      |
| `demo_config.yaml`  | `site.base_url`, `session.pre_session`, feature flags.   |
| `branding.yaml`     | Brand name, colors, logo, voice config.                  |
| `.env.example`      | Template for credentials. Copy to `.env` in working dir. |
| `_assets/`          | Drop your brand logo PNG here (see `branding.yaml`).     |
