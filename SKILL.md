---
name: demo-video-from-site
description: Use when the user wants to create a narrated, branded demo video walking through any website. Handles site exploration, storyboard drafting (with user review in plain English), TTS narration via OpenAI, Playwright recording, audio/video mux, speed adjustment, brand overlay, and (Phase B) intro/outro/captions. Produces a polished mp4. Triggers on phrases like "create a demo video", "make a walkthrough video", "produce a narrated screencast", "demo my site/app", "loom-style video of [url]".
---

# demo-video-from-site

You orchestrate a full pipeline that turns any website + a logo + a bit of intent into a 5-minute narrated, branded demo video. The scripts in `scripts/` are dumb pipes; you are the conductor.

Reference docs in this folder: `docs/SCHEMAS.md` (YAML + action grammar), `docs/GOTCHAS.md` (known issues + workarounds), `docs/CONTEXT.md` ("what good output looks like"), `examples/halyard-spme/` (canonical complete example). Read these as needed — don't pre-load them.

## When to use this skill

- User wants a narrated demo video of a website (live, local dev, or static).
- User has at least light intent guidance ("show X, Y, Z" / "demo the dashboard flow").
- User has access to a logo or wordmark.

**Refuse to proceed if the user gives you neither intent notes nor a logo.** Generic demos with default branding are bad demos. Ask for guidance instead of silently producing a weak video.

## Phase 1 — Interview (collect inputs)

Ask one or two questions at a time, not all at once. Required:

1. **Target URL** — confirm it's reachable.
2. **Demo intent notes** — what story does this tell? What features matter?
3. **Audience + tone** — internal/external/investors; explanatory/sales/technical/casual.
4. **Length target** — default 5 min.
5. **Logo** — URL or path. If only text-only is available, flag the limitation but accept.
6. **Brand colors** — primary (ink) + accent. If unspecified, infer from the logo with PIL.
7. **Auth?** — does the site require login?
   - **No** → proceed.
   - **Yes, form-based** (site has its own email/password fields you control) → use `session.pre_session` in `demo_config.yaml`. Collect credential env-var names (NOT actual values) and the login URL/selectors. Tell the user to put the actual credentials in `<working_dir>/.env` themselves before running, never in chat. See `examples/login-flow/`.
   - **Yes, OAuth / SSO / magic-link / passkey** (Google, Microsoft, Okta, etc.) → use `session.storage_state`. The user does NOT run any commands. YOU launch `helpers/capture_auth.py` for them in Phase 2a, and they only log in interactively in the browser window that opens. The captured `auth.json` is then used for both Phase 2b exploration AND Phase 8 recording. See `examples/oauth-storage-state/`.

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

Note for each significant page:

- Demo-worthy moments (scroll-to-feature, click-to-detail, hover-tooltip).
- Site adaptations needed: sticky header trick? PDF deep-link? Modal blockers? Auth wall?
- Selectors that look fragile and might need `wait_for_selector` defenses.

Don't exhaustively crawl. 2–5 actions per page is plenty.

## Phase 3 — Draft storyboard.yaml

Generate 15–30 beats. Each beat = one camera action + 1–3 sentences of narration. See `docs/SCHEMAS.md` for the action grammar (Phase A subset: `goto`, `goto_and_scroll`, `scroll_into_view`, `scroll_y`, `hover`, `click`).

**Target for a 5-minute video at 1.2x speed-up:**
- Total post-speedup: ~5:00
- Total raw runtime: ~6:00
- Per-beat average: ~12s, of which ~9–10s is narration

**Hard rules when drafting narration:**

1. **Every factual claim must be visible on screen at this beat's frame.** No invented numbers ("the agent flagged 199 changes"). If you don't see it on the screenshot, don't say it.
2. **Initialisms read letter-by-letter must be written hyphenated:** `S-P-M-E`, `K-Y-B`, `A-P-I`. The TTS prompt enforces this convention.
3. **Length matches visual content:** 8–18s for scroll beats, 6–12s for click beats.
4. **Tone matches `branding.yaml`'s `voice.tone` field.**

Mentally group beats into segments (Overview / Feature A / Feature B / Closing) but write a flat list in YAML — no section markers.

## Phase 4 — Review in plain English

**The user does not edit YAML directly.** You present the draft as a numbered list and accept natural-language feedback. Use this format exactly:

```
Here's the demo flow I've drafted. Estimated runtime: 5:08 (after 1.2x speedup).
Tell me what you'd like to change.

OVERVIEW (60s)
1. Land on homepage (10s) — "Welcome to Acme Cloud, a serverless platform for small teams..."
2. Scroll to features (15s) — "Three core capabilities power the platform..."
3. Scroll to outputs (8s) — "These ten policy areas..."

FEATURE 1 — Dashboard (45s)
4. Navigate to dashboard (8s) — "Clicking into the dashboard..."
5. Hover live activity feed (12s) — "Every project shows a live activity feed..."
...

CLOSING (20s)
27. Back to homepage stats (12s) — "Three reasons teams choose Acme..."
28. Outro (8s)
```

Then: **"Anything to add, remove, or reorder? Any narration tone adjustments? Anything to skip?"**

Translate natural-language feedback into YAML edits:
- "Skip beat 7" → remove from YAML
- "Make beat 3 longer" → extend narration with more on-screen detail (split into two beats if much longer)
- "Mention pricing somewhere" → identify the right beat and add a sentence (verify pricing is actually visible on that beat's frame)
- "Tone too formal" → rewrite narration with looser phrasing
- "Show the team page instead of about" → swap URL + adjust narration

Re-present the updated flow. Iterate until the user explicitly approves.

**Runtime drift check before TTS:** sum `len(beat.narration) / 16` (chars/sec at 140wpm) across all beats. If `estimated * (1 / speed_multiplier)` is more than 30s off the target, surface it: "This currently lands at ~6:20 post-speedup vs your 5min target. Want me to trim?"

## Phase 5 — Working directory setup

```bash
mkdir -p ~/demo-videos/<demo-slug>/_assets
cp <logo_path>             ~/demo-videos/<demo-slug>/_assets/<logo>.png
# write storyboard.yaml, branding.yaml, demo_config.yaml from your drafts
```

If the user doesn't have a logo file on disk and only has a URL, download it with `curl` and place it in `_assets/`.

If any beats need to show a PDF page (inline, not as a download dialog), declare them at the top of `storyboard.yaml` under a `pdfs:` block — see `docs/SCHEMAS.md`. The pre-record step in `record_demo.py` invokes `helpers/pdf_wrapper.py` for each declared PDF automatically; you don't need to run the wrapper script yourself.

Confirm `OPENAI_API_KEY` is available (in the user's shell env or in `<working_dir>/.env`). If missing, ask the user to set it before running TTS. If form-based login is required, confirm any credential env-var names declared in `session.pre_session` are also set in `<working_dir>/.env`. If OAuth login is required, confirm `auth.json` is already present in the working dir from Phase 2a — if it's missing, re-run Phase 2a's capture step.

If `branding.yaml` declares an `audio:` block with a `bg_music_path` or `bg_music_mood`, the file will be validated at this phase: the path must exist (Mode A), or the mood must be one of the bundled set (`upbeat`, `warm`, `calm`, `playful`, `cinematic`, `tech`). Both fields set → error. Neither set → no bg music (back-compat default). See `docs/SCHEMAS.md` "Audio bed" section.

## Phase 6 — Generate assets (badge)

```bash
uv run scripts/make_overlay.py --working-dir ~/demo-videos/<demo-slug>
```

Inspect `_assets/overlay_frames/frame_0000.png` to verify the badge renders correctly (logo visible, colors right). If wrong, fix `branding.yaml` and rerun.

If `features.intro_slide` or `features.outro_slide` is enabled in `demo_config.yaml`, the intro/outro slide videos are generated by `scripts/make_intro_outro.py` **after** recording (Phase 9 below). Captions, if enabled, are generated by `scripts/make_captions.py` at the same stage. Don't run them here — they depend on timing data the recorder produces.

## Phase 7 — TTS generation

Before running, surface cost to the user: ~$0.015/min × ~6min raw ≈ **$0.10**.

```bash
uv run scripts/render_voiceover.py --working-dir ~/demo-videos/<demo-slug>
```

The script is **diff-aware**: on iterative re-runs it only regenerates beats whose narration changed. Pass `--clean` to nuke and regenerate everything.

If you see size-anomaly warnings (`! beat_id: wav size suspicious`), the script auto-retries up to 3x. If still failing after 3 retries, that beat will play truncated — flag to user, consider rephrasing the narration.

## Phase 8 — Record

```bash
uv run scripts/record_demo.py --working-dir ~/demo-videos/<demo-slug>
```

The script auto-unsets `NODE_OPTIONS` (see `docs/GOTCHAS.md` #1). Wall-clock time roughly equals the total raw runtime (~5–6 min for a 5-min demo).

Before the main recording loop, the script runs (when configured): the **PDF pre-flight** (generating wrappers for every entry under `pdfs:`) and the **login pre-session** (executing the steps under `session.pre_session` against a separate context that hands its storage state to the recording context). Both run automatically based on the storyboard / `demo_config.yaml`; the recorder logs each step (with credential values masked).

Watch for action failures (`✗ beat 'XX' failed during action`). Common causes:
- Selector no longer matches (site changed, lazy loading) → tighten with `wait_for_selector` or pick a more stable selector
- Element off-screen (the recorder auto-scrolls before hover/click but sometimes a `scroll_into_view` beat needs to precede)

## Phase 9 — Mux + speed + brand + finalize

Run sequentially. The first three stages are always required. The last three (intro/outro, captions, finalize) only do work when the matching `features.*` flag is enabled in `demo_config.yaml`; otherwise `finalize_video.py` passes the branded mp4 through as-is.

```bash
uv run scripts/mux_demo.py    --working-dir ~/demo-videos/<demo-slug>

uv run scripts/speed_video.py \
  --input  ~/demo-videos/<demo-slug>/_intermediate/muxed.mp4 \
  --output ~/demo-videos/<demo-slug>/_intermediate/speed.mp4 \
  --multiplier 1.2

uv run scripts/brand_video.py \
  --working-dir ~/demo-videos/<demo-slug> \
  --input  ~/demo-videos/<demo-slug>/_intermediate/speed.mp4 \
  --output ~/demo-videos/<demo-slug>/_intermediate/branded.mp4

# Phase B (only when features.intro_slide or features.outro_slide is true):
uv run scripts/make_intro_outro.py --working-dir ~/demo-videos/<demo-slug>

# Phase B (only when features.captions.enabled is true):
uv run scripts/make_captions.py --working-dir ~/demo-videos/<demo-slug>

# Always run finalize last — it concats intro/outro and burns or sidecars captions.
# When all features.* flags are false, it copies branded.mp4 through unchanged.
uv run scripts/finalize_video.py \
  --working-dir ~/demo-videos/<demo-slug> \
  --input  ~/demo-videos/<demo-slug>/_intermediate/branded.mp4 \
  --output ~/demo-videos/<demo-slug>/<filename_from_demo_config>.mp4
```

`finalize_video.py` requires an `ffmpeg` built with `libass` for caption burn-in (`captions.mode: burned`). The default Homebrew `ffmpeg` formula does **not** include libass — install `ffmpeg-full` instead (`brew install ffmpeg-full`) or set `captions.mode: srt-sidecar` to skip burn-in and ship the SRT alongside the mp4.

## Phase 10 — Verify (mandatory, before claiming success)

Extract spot-check frames at intro, mid-demo, and outro:

```bash
mkdir -p ~/demo-videos/<demo-slug>/_verify
for t in 5 60 180 280; do
  ffmpeg -y -ss $t -i ~/demo-videos/<demo-slug>/<filename>.mp4 \
    -vframes 1 ~/demo-videos/<demo-slug>/_verify/frame_t${t}.jpg 2>/dev/null
done
```

Read each frame with the Read tool. Confirm:

- **Brand badge** appears bottom-left with the logo and lime ring.
- **Section headers / sticky elements** visible where expected (no content hidden under a header).
- **Narration's specific claims match what's on screen** at that beat — if a beat says "five releases" the screen at that timestamp must show "5". If a mismatch shows up here, identify the beat, fix the storyboard, regenerate just the affected TTS (`render_voiceover.py` will diff-detect) and re-record.

If intro/outro slides are enabled, also extract a frame from inside the intro (e.g. `t=2`) and inside the outro (e.g. `t = duration - 2`) and confirm the brand name, tagline, CTA, and logo render correctly with no clipping. If captions are burned in, confirm at least one mid-demo frame shows readable captions (white text with dark outline) anchored at the bottom of the demo region.

Then read final duration + file size via `ffprobe` and report to the user.

## Phase 11 — Hand off

Report:

- Final mp4 path, duration, size
- Working-dir location for re-runs
- **How to iterate cheaply:**
  - *Narration tone change:* edit `storyboard.yaml`, re-run `render_voiceover.py` (diff-aware) → `mux` → `speed` → `brand` → (`make_captions.py` if captions are on) → `finalize_video.py`. No re-record needed.
  - *Visual timing or selector change:* re-run from `record_demo.py` onward.
  - *Branding change (colors, logo):* re-run `make_overlay.py` → `brand_video.py` → `make_intro_outro.py` (if intro/outro on) → `finalize_video.py`.
  - *Intro/outro copy or captions toggle:* edit `branding.yaml` or `demo_config.yaml`, re-run `make_intro_outro.py` (and/or `make_captions.py`) → `finalize_video.py`.
  - *Background music change (file path or mood):* edit `branding.yaml`'s `audio:` block, re-run `finalize_video.py`. No re-record, no re-TTS.

## Common things that go wrong

See `docs/GOTCHAS.md` for the full list. The ones you'll most likely hit:

- **PDF deep-links don't render in headless Chromium** (#4). Declare the PDF in the storyboard's `pdfs:` block; `record_demo.py` runs `helpers/pdf_wrapper.py` automatically to pre-render the page and serve through an HTML viewer wrapper.
- **Sticky-header CSS injection without scroll-margin-top** (#5). Always add `scroll-margin-top: <header_height + buffer>` to scroll targets in the same CSS injection.
- **Narration claims don't match on-screen content** (#11). The verify step catches this. Discipline at draft time prevents it.
- **Storyboard runtime drift** (#12). Sum char-count / 16 before TTS; warn if > 30s off target.
- **Layout shifts between recording sessions** (#13). If the user is re-running a >1-day-old storyboard, re-explore the site briefly first.
- **libass missing for caption burn-in** (#18). Default Homebrew `ffmpeg` doesn't include libass; `subtitles=` filter fails with an opaque "No such filter" error. Install `ffmpeg-full` or use `captions.mode: srt-sidecar`.
- **Codec mismatch at intro/outro/main seams** (#21). `make_intro_outro.py` is configured to match `brand_video.py`'s encoding profile (framerate, h264 profile, AAC sample rate, channel layout) so `finalize_video.py` can concat with `-c copy`. If you customize either script, keep the profiles aligned.

## Hard rules (do not bypass)

- **You draft the storyboard. The user reviews in plain English.** Never make the user edit YAML.
- **Narration must only quote what's on screen.** Verify in Phase 10.
- **Refuse without intent + logo.** Don't silently produce a generic demo.
- **Run Phase 10 verification** before saying "demo is ready." Read at least 3 frames (more if intro/outro/captions are enabled).
- **Feature flags live in `demo_config.yaml`.** `features.intro_slide`, `features.outro_slide`, `features.captions.enabled` (+ `features.captions.mode: burned | srt-sidecar`), and `session.pre_session` for login are all opt-in. The default profile (all flags off) reproduces the Phase A baseline.

## Reference example

Everything in `examples/halyard-spme/` reproduces the Carver Agents / Mastercard-SPME demo. When in doubt about structure, look there.
