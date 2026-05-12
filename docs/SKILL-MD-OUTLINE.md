# What to put in SKILL.md

`SKILL.md` is the file Claude reads when this skill is invoked. It's the playbook for the entire workflow. Keep it under ~400 lines.

## Frontmatter

```yaml
---
name: demo-video-from-site
description: Use when the user wants to create a narrated, branded demo video walking through any website. Handles site exploration, storyboard drafting (with user review in plain English), TTS narration via OpenAI, Playwright recording, audio/video mux, speed adjustment, brand overlay, and optional intro/outro/captions. Produces a polished 5-minute mp4. Triggers on phrases like "create a demo video", "make a walkthrough video", "produce a narrated screencast", "demo my site/app".
---
```

## Section structure

### 1. When to use this skill

- User wants a narrated demo video of a website
- Has at least light intent guidance ("show X, Y, Z" or "demo the dashboard flow")
- Has access to a logo or wordmark to brand the video

If the user has none of these, ask for them. Refuse to proceed silently with defaults — generic demos are bad demos.

### 2. Required inputs (interview the user upfront)

Before starting, collect:

1. **Target URL** — live site, dev server, or static path. Confirm it's reachable.
2. **Demo intent notes** — free-form. What story does this demo tell? What features matter?
3. **Audience** — internal team / external prospects / investors / engineers.
4. **Tone** — explanatory / sales / technical / casual.
5. **Length** — default 5 min if unspecified.
6. **Logo** — URL or local path. If user has no logo, refuse to proceed (or accept a text-only badge as a last resort, but flag the limitation).
7. **Brand colors** — primary + accent. Default to "I'll infer from your logo" if unspecified (use PIL to extract dominant colors).
8. **Login needed?** — if yes, collect credentials safely via env vars, not in chat.

Ask one or two at a time, not all at once.

### 3. Site exploration phase

Use Playwright MCP (available as `mcp__plugin_playwright_playwright__*` tools) to:

- Navigate the target site, starting from the URL
- Take screenshots of key pages
- Read DOM structure to identify good selectors for scroll/hover/click targets
- Note any site-specific concerns (auth wall, dynamic loading, PDFs, modals)

This phase should take 2–5 MCP browser actions per significant page. Don't exhaustively crawl — focus on pages the user's intent notes mentioned.

While exploring, note:

- Which pages are most demo-worthy
- Good camera moments (scroll-to-feature, click-to-detail, hover-tooltip)
- Site-specific challenges (need sticky-header CSS? need PDF wrapper? need login pre-session?)

### 4. Storyboard drafting

Generate a `storyboard.yaml` with 15–30 beats. Each beat:

- One camera action (see action grammar in SCHEMAS.md)
- 1–3 sentences of narration aligned to the visible content
- Narration claims that are verifiable on screen at this beat's frame

Group beats into segments mentally (Overview, Feature A, Feature B, Closing) but don't add section markers in the YAML — the storyboard is a flat list of beats.

**Target runtime breakdown** (for 5-minute video at 1.2x speed):

- Total post-speedup: 5:00
- Total raw runtime: 6:00
- Per beat average: ~12s, of which ~9–10s is narration

### 5. User review — plain English

Present the storyboard to the user **without YAML**. Use this format:

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

Then ask: "Anything to add, remove, or reorder? Any narration tone adjustments? Anything to skip?"

Accept natural-language feedback and edit the YAML. Re-present the updated flow. Iterate until user explicitly approves.

Typical edits the user may request:

- "Skip beat 7" → remove from YAML
- "Make beat 3 longer" → extend the narration with more detail (and possibly split into two beats if much longer)
- "Mention pricing somewhere" → identify the right beat and add a sentence
- "Tone too formal" → rewrite narration with looser phrasing
- "Show the team page instead of the about page" → swap the URL + adjust narration

### 6. Asset preparation

- Download or copy the logo to the working directory
- Verify logo loads cleanly; if it's black-on-transparent (common case), the badge renderer will recolor automatically
- Run `scripts/make_overlay.py` to generate the badge frame sequence
- If any beat opens a PDF, generate the inline-PDF wrapper via `helpers/pdf_wrapper.py` (Phase B)

### 7. TTS generation

Run `python scripts/render_voiceover.py --working-dir <path>`. This reads the storyboard, generates one wav per beat via OpenAI, and writes the manifest. Includes size-anomaly retry.

Report estimated cost to the user before generating (~$0.015/min audio × estimated minutes).

### 8. Recording

Run `unset NODE_OPTIONS && python scripts/record_demo.py --working-dir <path>` (or invoke via a subprocess wrapper that auto-clears NODE_OPTIONS).

The recorder:

- Launches headless Chromium at the configured viewport
- Runs pre-session auth if configured (Phase B)
- Injects `recording_css` from branding config
- Executes each beat's action, holds for the calculated duration, records action_ms

Wall-clock time: roughly equal to total raw runtime (5–6 minutes for a 5-min demo).

### 9. Mux + speed + brand

Run sequentially:

- `python scripts/mux_demo.py --working-dir <path>` → muxed.mp4
- `python scripts/speed_video.py --input muxed.mp4 --output speed.mp4 --multiplier 1.2` → speed.mp4
- `python scripts/brand_video.py --working-dir <path> --input speed.mp4 --output demo.mp4` → final demo.mp4

(Phase B: brand_video.py also handles intro/outro slide prepend/append and caption burn-in.)

### 10. Verify

Extract spot-check frames:

```bash
for t in <pick 3-5 representative timestamps>; do
  ffmpeg -y -ss $t -i demo.mp4 -vframes 1 _verify/frame_t${t}.jpg
done
```

Inspect each frame and confirm:

- Brand badge appears in correct position
- Section headers visible where expected
- Narration's visible-claims match what's actually on screen at that beat

If anything looks off, identify which beat is responsible and fix the storyboard or branding config, then re-run from the failed step.

Report the final mp4 path, duration, file size, and a summary of what was produced.

### 11. Handing off

After producing the final mp4, summarize for the user:

- File path
- Duration + size
- Working directory location (for re-runs / tweaks)
- How to re-run if narration needs changing (just re-run from TTS step, don't need to re-record)
- How to re-run if visual timing needs changing (re-record + re-mux)

---

## Style notes for SKILL.md

- Bias toward concrete commands and example formats over abstract description
- Show the user-review format inline so Claude knows the exact pattern
- Include a "Common things that go wrong" subsection cross-referencing GOTCHAS.md
- Don't reproduce GOTCHAS.md content inside SKILL.md — link to it
- Keep narration tone guidance terse — point to CONTEXT.md "What good output looks like" rather than re-explaining

## Things to omit from SKILL.md

- Don't repeat schemas in detail; reference SCHEMAS.md
- Don't repeat the architecture diagram; reference ARCHITECTURE.md
- Don't repeat design decisions; reference DESIGN-DECISIONS.md
- Skill files should be focused playbooks, not all-in-one manuals
