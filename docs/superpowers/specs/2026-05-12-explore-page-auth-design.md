# Authenticated page exploration for OAuth demos

**Status:** Approved 2026-05-12
**Author:** Claude (Opus 4.7) with achint
**Phase:** B+ (companion to storage_state recording shipped earlier today)

## Problem

The skill's Phase 2 site exploration uses the Playwright MCP, which spins up a separate Chromium process with no per-call `storage_state` option. So for OAuth-authenticated targets, Phase 2 can only see public pages (landing, login screen). The skill then has to draft a storyboard in Phase 3 with no visibility into the authenticated UI.

Today's flow (for OAuth):
- Phase 1: interview user (asks about auth type)
- Phase 2: explore site via Playwright MCP — but can't see logged-in pages
- Phase 3: draft storyboard — flying blind for auth-required beats
- Phase 5: capture auth, scaffold working dir
- Phase 8: record (uses storage_state correctly)

The gap is Phase 2 ↔ Phase 8. Auth is captured way too late.

## Goal

Capture auth state ONCE, early in the workflow, and use it for both exploration AND recording. The user logs in once, then the skill can both view and record authenticated pages.

## Non-goals

- Modifying the Playwright MCP server config to support `storage_state`. The MCP I have access to creates its own Chromium with no per-call options. Out of scope.
- Headed exploration. Skip; not needed.
- Multi-tab exploration / complex interactions during Phase 2. The exploration phase is "take a snapshot of each page I care about." Interactivity belongs in recording (Phase 8).

## Design

### Workflow change

Move auth capture from Phase 5 to a new **Phase 2a "Auth capture"** that runs BEFORE site exploration. Phase 2 (now 2b "Site exploration") branches on whether auth.json exists:

- **No auth.json** → use Playwright MCP as today.
- **auth.json present** → use new `helpers/explore_page.py` per page, which launches headless Chromium with `storage_state=auth.json` loaded.

The exploration helper is a thin one-shot: navigate → wait for networkidle → screenshot + DOM dump + metadata → exit. The skill (Claude as orchestrator) invokes it once per page it wants to inspect.

### New script: `helpers/explore_page.py`

```
uv run helpers/explore_page.py <url> \
  --storage-state PATH \
  --out-dir DIR \
  [--slug NAME] \
  [--viewport WxH]
```

Writes three files into `out-dir`:
- `<slug>.png` — full-page screenshot (clipped to viewport for fast Claude reads)
- `<slug>.dom.html` — full DOM at networkidle
- `<slug>.meta.json` — `{url_requested, final_url, title, status}`

Defaults:
- `--viewport` defaults to `1440x900` (matches recorder + capture_auth.py)
- `--slug` defaults to a sanitized version of the URL path (e.g. `/dashboard/account` → `dashboard_account`; root `/` → `home`)

Behavior details:
- Headless Chromium (`pw.chromium.launch(headless=True)`).
- `NODE_OPTIONS` auto-cleared (cmux workaround, same as record_demo.py and capture_auth.py).
- 60-second timeout on `page.goto(url, wait_until="networkidle")`.
- If `--storage-state` path doesn't exist → exit non-zero with an actionable message pointing at `helpers/capture_auth.py`.
- If the page returns 401 or redirects to a login URL, the resulting screenshot will show that visibly and `final_url` in meta.json will surface it. The script itself doesn't try to detect "session expired" — that's the user's signal to re-run capture_auth.py.
- 0600 perms on output files: NOT required. These are non-secret (screenshots and DOM). Use default umask.

### SKILL.md changes

**Phase 1 (Interview)** — no change to question 7's branching, but the OAuth case's pointer text changes from "during Phase 5" to "during Phase 2a".

**New Phase 2a — Auth capture (if OAuth)** — placed between Phase 1 and existing Phase 2. Contains the same content as the current Phase 5 "Auth capture" sub-step (Bash invocation, 10-min timeout, what to say to the user, viewport-match note). Move it here.

**Phase 2 → Phase 2b — Site exploration** — Phase 2's existing content stays, with a new branching paragraph at the top:

> If `auth.json` was captured in Phase 2a, use `helpers/explore_page.py` instead of the Playwright MCP for any page that requires authentication. The MCP can't load the captured storage_state, so it would only see login walls.
>
> ```bash
> mkdir -p ~/demo-videos/<demo-slug>/_explore/
> uv run helpers/explore_page.py https://target.example.com/dashboard \
>   --storage-state ~/demo-videos/<demo-slug>/auth.json \
>   --out-dir ~/demo-videos/<demo-slug>/_explore/
> ```
>
> Read the resulting `.png` and `.dom.html` files with the Read tool. For non-auth pages (landing page, marketing pages), Playwright MCP is still fine and more interactive.

**Phase 5 — Working directory setup** — REMOVE the "Auth capture (OAuth / SSO / magic-link only)" sub-step I added earlier today (commit ea8ca56 / 574928d). It's now in Phase 2a.

Phase 5 should still mention `auth.json` (it's a file that lives in the working dir), but as a "this should already exist from Phase 2a" reminder, not a step to run.

### CLAUDE.md change

The existing "Skill orchestrates shell commands; user only does what fundamentally requires a human" non-negotiable (added in commit 574928d) is reinforced — no edit needed. The "Capture-record viewport match" preserve invariant (commit ea8ca56) gains a sibling: explore-record viewport match. The capture helper, the explore helper, and the recorder must all use the same viewport, or some sites will invalidate the session.

Add a new preserve bullet:

> - **Capture/explore/record viewport alignment.** `helpers/capture_auth.py`, `helpers/explore_page.py`, and `scripts/record_demo.py` must all use the same viewport for a given demo. Default 1440x900 across all three. If a demo customizes `recording.viewport`, pass the same `--viewport WxH` to capture_auth.py AND explore_page.py. Some sites fingerprint viewport size between capture and use; mismatch invalidates the session.

(Replace the existing "Capture-record viewport match" bullet with this expanded version.)

### `docs/SCHEMAS.md` change

The `session.storage_state` subsection added in commit ea8ca56 has a "Viewport match" paragraph mentioning capture_auth.py. Update it to also mention explore_page.py:

> **Viewport match.** `capture_auth.py` and `explore_page.py` both default to viewport 1440x900 (the recorder default). If you customize `recording.viewport`, pass the same size via `--viewport WxH` to both — some sites invalidate sessions when the viewport changes.

## Testing

### Unit — `tests/test_explore_page.py`

1. `--storage-state` points at a non-existent file → exit non-zero with message containing the resolved path AND "capture_auth.py".
2. Slug derivation: `/dashboard/account` → `dashboard_account`; `/` → `home`; `/foo/bar.html` → `foo_bar_html`; query string stripped; trailing slash stripped.

### Integration — `tests/test_explore_page_e2e.py`

End-to-end against the same localhost cookie-gated server pattern from `test_record_storage_state_e2e.py`:

1. Spin up a localhost http.server with the cookie-gated `/protected` route from Task 3's pattern.
2. Hand-craft an `auth.json` with the gating cookie.
3. Run `helpers/explore_page.py http://127.0.0.1:<port>/protected --storage-state <auth.json> --out-dir <tmp>/explore/ --slug protected`.
4. Assert:
   - Exit code 0.
   - `<tmp>/explore/protected.png` exists and is non-empty.
   - `<tmp>/explore/protected.dom.html` exists and contains "Protected content".
   - `<tmp>/explore/protected.meta.json` exists and contains `"final_url": "http://127.0.0.1:<port>/protected"` (i.e., no redirect to login).

This proves the helper actually loads storage_state and accesses authenticated content.

### Manual — non-auth path unchanged

`examples/halyard-spme/` still works without any `auth.json`. The skill's Phase 2 with no `session.storage_state` declared in `demo_config.yaml` still uses Playwright MCP exclusively.

## Implementation order

1. `helpers/explore_page.py` — new script + unit tests (slug derivation) + e2e test (with localhost server, mirroring Task 3's pattern). One commit.
2. `SKILL.md` — restructure: Phase 2 → 2a + 2b, remove duplicate from Phase 5. One commit.
3. `CLAUDE.md` and `docs/SCHEMAS.md` — viewport-alignment update + explore_page.py mention. One commit.

Each task has its own implementer + spec review + code quality review per the subagent-driven-development workflow. Model tiers: Haiku for all implementers (mechanical, spec is complete); Sonnet for both review stages.

## Open questions

None at design time. User has approved the design verbally.
