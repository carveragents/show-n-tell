# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A planning workspace for a Claude Code skill named **demo-video-from-site** that produces narrated, branded demo videos of any website. The skill itself lives at `~/.claude/skills/demo-video-from-site/` and is **user-global** (works across every project).

## Status — read before doing anything

- **Planning phase only.** `docs/` is the entire repo today. There is no `SKILL.md`, no `scripts/`, no `examples/` yet — you are building them.
- A working reference implementation lives at `~/work/scribble/code/repos/carver/policy-diffs/`. Phase A is largely an extraction-and-parameterization job from that repo's `scripts/` directory, not greenfield. See `docs/REFERENCE.md` for the exact source paths and what to preserve.
- All major design questions are answered in `docs/DESIGN-DECISIONS.md`. **Do not re-litigate them with the user** — treat them as binding.

## Reading order for a fresh session

Read these in order before writing any code:

1. `docs/PLAN.md` — orientation and end-to-end workflow
2. `docs/CONTEXT.md` — what was built before, who the user is, what "good output" looks like
3. `docs/DESIGN-DECISIONS.md` — locked-in choices
4. `docs/REFERENCE.md` — paths to the source scripts you will extract from
5. `docs/ARCHITECTURE.md` — target folder layout + per-script responsibilities
6. `docs/PHASE-A-TASKS.md` — concrete checklist for the first build session

Open `docs/SCHEMAS.md`, `docs/SKILL-MD-OUTLINE.md`, and `docs/GOTCHAS.md` as reference material while building.

## The skill's shape (high-level architecture)

The skill is an orchestrator, not a monolith. Each pipeline stage is a separate small script (≤ 250 lines) invoked sequentially by Claude per `SKILL.md`:

```
storyboard.yaml ─┬─→ render_voiceover.py ─→ manifest + N wavs
                 └─→ record_demo.py       ─→ reference.webm + timings.json
                                              ↓
            mux_demo.py → speed_video.py → make_overlay.py → brand_video.py → demo.mp4
```

Per-demo artifacts live in a working directory (`~/demo-videos/<demo-slug>/`), not in the skill folder. The skill folder stays clean — scripts, templates, examples, and `SKILL.md` only. The working-dir model is what makes re-runs cheap: changing narration tone regenerates only TTS + mux; re-recording is not required.

## Phase boundaries (do not cross them in one session)

- **Phase A (MVP):** sites without login or PDFs. Reproduces the existing Halyard / Mastercard-SPME demo end-to-end. See `docs/PHASE-A-TASKS.md`.
- **Phase B:** intro/outro slides, captions, login pre-session, PDF wrapper auto-gen, recipe library.
- **Phase C:** multi-provider TTS, richer recipes, failure recovery.

The user has explicitly asked: build Phase A only, verify it reproduces the Halyard demo, then stop and check in. Do not build Phase B in the same session.

## Things you must preserve when extracting from the reference repo

These are real-world fixes from the original build — `docs/GOTCHAS.md` has full context for each:

- **Auto-unset `NODE_OPTIONS`** in `record_demo.py` (cmux's hook breaks Playwright's Node driver). Do this in the script — don't make the user remember.
- **TTS size-anomaly retry** in `render_voiceover.py` (OpenAI streaming occasionally truncates).
- **Use `ffprobe` for wav duration**, never Python's `wave` module — it misparses OpenAI's wav header and returns absurd numbers.
- **Per-beat timing model:** `action_ms` (measured at record time) + `PRE_MS` (400ms default) + `tts_ms` (from manifest) + `POST_MS` (700ms default). The recorder holds for `PRE + tts + POST` after action completes; the audio track is `silence(action_ms + PRE) + tts + silence(POST)` per beat.
- **`scroll-margin-top` on scroll targets** whenever sticky-header CSS is injected.
- **`atempo=1.2` + `setpts=PTS/1.2`** for combined audio+video speed-up with pitch preservation.
- **`showwaves` → `colorkey=0x000000:0.15:0`** to remove the black background. `mode=p2p` + `scale=sqrt` for visible waveform at speech amplitudes.
- **2x supersample** for PIL badge rendering (smooth anti-aliased edges).
- **mp4 re-encode** in mux: `-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -c:a aac -b:a 192k` (Playwright outputs webm; yuv420p needed for QuickTime/iMessage compatibility).
- **Recolor monochrome-on-transparent logos** to the configured cream color via alpha-channel masking. Auto-detect: only recolor if all non-transparent pixels are the same color.

## Non-negotiable behavioral constraints

These come from the user's stated requirements — `docs/DESIGN-DECISIONS.md` is authoritative:

- **Claude drafts the storyboard; user reviews in plain English.** Never ask the user to edit YAML. Present beats as a numbered list with timestamps + narration quotes, accept natural-language feedback ("skip beat 7", "make beat 3 longer"), iterate until approved.
- **Narration must only quote numbers and names visible on screen at that beat.** No invented facts. The verification step extracts frames and checks this.
- **Refuse to proceed** if the user provides neither intent notes nor a logo. Generic demos with default branding are bad demos.
- **Verify before claiming success.** After producing the final mp4, extract ≥3 spot-check frames and inspect them. Don't hand-wave success.
- **Extract clean copies** of reference scripts into the skill folder — do not import from the policy-diffs repo at runtime. The skill is self-contained and portable.

## Test target

The Halyard / Mastercard-SPME demo at `~/work/scribble/code/repos/carver/policy-diffs/credio-policies/dist/demo-video.mp4` is the gold standard. Phase A is "done" when the skill can reproduce a qualitatively-equivalent video given only the `examples/halyard-spme/` inputs (storyboard + branding + demo_config YAMLs) and the dist site served at `localhost:8080`.

## Tooling

- Python with `uv` for script execution
- `ffmpeg` + `ffprobe` for all video/audio work
- Playwright (Python) for recording; Playwright MCP (`mcp__plugin_playwright_playwright__*`) for site exploration
- OpenAI SDK for TTS (`gpt-4o-mini-tts`, voice `cedar`)
- PIL for badge frame rendering
- `pymupdf` for PDF page rasterization (Phase B)

Verify `ffmpeg`, `ffprobe`, and `uv` are on PATH before starting.
