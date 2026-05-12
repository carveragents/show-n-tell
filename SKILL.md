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
7. **Login?** — if yes, collect credentials via env vars only, never in chat. (Phase B; warn if Phase A only.)

## Phase 2 — Site exploration

Use the Playwright MCP tools (`mcp__plugin_playwright_playwright__*`) to:

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

Confirm `OPENAI_API_KEY` is available (in the user's shell env or in `<working_dir>/.env`). If missing, ask the user to set it before running TTS.

## Phase 6 — Generate assets (badge)

```bash
uv run scripts/make_overlay.py --working-dir ~/demo-videos/<demo-slug>
```

Inspect `_assets/overlay_frames/frame_0000.png` to verify the badge renders correctly (logo visible, colors right). If wrong, fix `branding.yaml` and rerun.

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

Watch for action failures (`✗ beat 'XX' failed during action`). Common causes:
- Selector no longer matches (site changed, lazy loading) → tighten with `wait_for_selector` or pick a more stable selector
- Element off-screen (the recorder auto-scrolls before hover/click but sometimes a `scroll_into_view` beat needs to precede)

## Phase 9 — Mux + speed + brand

Run sequentially:

```bash
uv run scripts/mux_demo.py    --working-dir ~/demo-videos/<demo-slug>

uv run scripts/speed_video.py \
  --input  ~/demo-videos/<demo-slug>/_intermediate/muxed.mp4 \
  --output ~/demo-videos/<demo-slug>/_intermediate/speed.mp4 \
  --multiplier 1.2

uv run scripts/brand_video.py \
  --working-dir ~/demo-videos/<demo-slug> \
  --input  ~/demo-videos/<demo-slug>/_intermediate/speed.mp4 \
  --output ~/demo-videos/<demo-slug>/<filename_from_demo_config>.mp4
```

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

Then read final duration + file size via `ffprobe` and report to the user.

## Phase 11 — Hand off

Report:

- Final mp4 path, duration, size
- Working-dir location for re-runs
- **How to iterate cheaply:**
  - *Narration tone change:* edit `storyboard.yaml`, re-run `render_voiceover.py` (diff-aware) → `mux` → `speed` → `brand`. No re-record needed.
  - *Visual timing or selector change:* re-run from `record_demo.py` onward.
  - *Branding change (colors, logo):* re-run `make_overlay.py` → `brand_video.py`.

## Common things that go wrong

See `docs/GOTCHAS.md` for the full list. The ones you'll most likely hit:

- **PDF deep-links don't render in headless Chromium** (#4). Pre-render the page as a PNG via `pymupdf` and serve through an HTML viewer wrapper. Phase B has `helpers/pdf_wrapper.py`; in Phase A, generate the wrapper manually if a beat needs it.
- **Sticky-header CSS injection without scroll-margin-top** (#5). Always add `scroll-margin-top: <header_height + buffer>` to scroll targets in the same CSS injection.
- **Narration claims don't match on-screen content** (#11). The verify step catches this. Discipline at draft time prevents it.
- **Storyboard runtime drift** (#12). Sum char-count / 16 before TTS; warn if > 30s off target.
- **Layout shifts between recording sessions** (#13). If the user is re-running a >1-day-old storyboard, re-explore the site briefly first.

## Hard rules (do not bypass)

- **You draft the storyboard. The user reviews in plain English.** Never make the user edit YAML.
- **Narration must only quote what's on screen.** Verify in Phase 10.
- **Refuse without intent + logo.** Don't silently produce a generic demo.
- **Run Phase 10 verification** before saying "demo is ready." Read at least 3 frames.
- **Phase A scope only** unless the user explicitly asks for Phase B features (intro/outro/captions/login). Phase B isn't implemented yet.

## Reference example

Everything in `examples/halyard-spme/` reproduces the Carver Agents / Mastercard-SPME demo. When in doubt about structure, look there.
