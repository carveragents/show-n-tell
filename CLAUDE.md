# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A planning workspace for a Claude Code skill named **demo-video-from-site** that produces narrated, branded demo videos of any website. The skill itself lives at `~/.claude/skills/demo-video-from-site/` and is **user-global** (works across every project).

## Status — read before doing anything

- **Phase A and Phase B are shipped (2026-05-12).** `SKILL.md`, `scripts/`, `helpers/`, `recipes/`, and `examples/halyard-spme/` are all populated and reproduce the Halyard reference. Phase C is deferred — see `docs/PHASE-B-TASKS.md` for the retrospective.
- The original working reference implementation lives at `~/work/scribble/code/repos/carver/policy-diffs/`. Phase A was an extraction-and-parameterization job from that repo's `scripts/` directory; see `docs/REFERENCE.md` for the source paths and what was preserved.
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
storyboard.yaml ─┬─→ render_voiceover.py    ─→ manifest + N wavs
                 └─→ record_demo.py          ─→ reference.webm + timings.json
                       (pre: helpers/pdf_wrapper.py per pdfs[], session.pre_session login)
                                                  ↓
            make_overlay.py → mux_demo.py → speed_video.py → brand_video.py → branded.mp4
                                                                ↓
                          make_intro_outro.py (Phase B; gated on features.intro_slide / outro_slide)
                          make_captions.py     (Phase B; gated on features.captions.enabled)
                                                                ↓
                                                       finalize_video.py → demo.mp4
                          (concats intro + branded + outro; burns or sidecars captions)
```

Per-demo artifacts live in a working directory (`~/demo-videos/<demo-slug>/`), not in the skill folder. The skill folder stays clean — scripts, templates, examples, and `SKILL.md` only. The working-dir model is what makes re-runs cheap: changing narration tone regenerates only TTS + mux; re-recording is not required.

## Phase boundaries

- **Phase A (MVP):** sites without login or PDFs. Reproduces the existing Halyard / Mastercard-SPME demo end-to-end. **Shipped.** See `docs/PHASE-A-TASKS.md`.
- **Phase B:** intro/outro slides, captions, login pre-session, PDF wrapper auto-gen, recipe library. **Shipped 2026-05-12.** See `docs/PHASE-B-TASKS.md` for the retrospective and Phase C deferrals.
- **Phase C:** multi-provider TTS, richer site-adaptation recipes (modal dismiss, lazy content waits, more login templates), failure recovery (retry a single failed beat without redoing the whole recording), audio crossfade at intro/main/outro seams. Out of scope for now.

Every Phase B feature is gated by a flag in `demo_config.yaml`. The Phase A baseline is reproducible by setting all `features.*` flags to false and omitting `session.pre_session` / the storyboard's `pdfs:` block.

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
- **libass is required for caption burn-in** in `finalize_video.py`. Default Homebrew `ffmpeg` doesn't include it; the script surfaces an actionable error pointing at `brew install ffmpeg-full` (or switch to `captions.mode: srt-sidecar`).
- **SRT path escaping in the ffmpeg `subtitles=` filter** is fragile across platforms. `finalize_video.py` copies the SRT into a CWD-local temp file and invokes ffmpeg with the file's basename so the filter arg stays simple — don't refactor it to pass an absolute path back in.
- **`force_style` commas inside the `subtitles=` filter arg** must be backslash-escaped or ffmpeg interprets them as filter-graph delimiters. Preserve the `\,` style separators already in `finalize_video.py`.
- **Encoder profile consistency for `-c copy` concat.** `make_intro_outro.py` and `brand_video.py` must produce matching framerate (25fps), h264 profile, audio sample rate (24000), and channel layout (mono) so `finalize_video.py` can concat with stream copy. If you adjust either script, audit the other.
- **Credentials in `${ENV_VAR}` form only, never literal in YAML.** `record_demo.py` runs `expand_env` after `interp_template` (so `${VAR}` resolves after `{{ base_url }}`). The logger masks the resolved `value` for any `fill` step. Use `raise ... from None` when surfacing missing-env errors so chained `__cause__` doesn't leak the underlying value through traceback rendering.
- **`finalize_video.py`'s concat is branch-dependent on `features.crossfade_seconds`.** When `0`, uses the concat demuxer with `-c copy` (instant, no re-encode). When `> 0`, uses an `xfade` + `acrossfade` filter graph (re-encodes the whole concat, ~30-60s for a 5-minute video, but produces soft seams). Don't "optimize" by always taking the copy path — you lose the seam polish. If you change `make_intro_outro.py`'s or `brand_video.py`'s codec profile, the copy path may also start failing; audit both.

## Non-negotiable behavioral constraints

These come from the user's stated requirements — `docs/DESIGN-DECISIONS.md` is authoritative:

- **Claude drafts the storyboard; user reviews in plain English.** Never ask the user to edit YAML. Present beats as a numbered list with timestamps + narration quotes, accept natural-language feedback ("skip beat 7", "make beat 3 longer"), iterate until approved.
- **Narration must only quote numbers and names visible on screen at that beat.** No invented facts. The verification step extracts frames and checks this.
- **Refuse to proceed** if the user provides neither intent notes nor a logo. Generic demos with default branding are bad demos.
- **Verify before claiming success.** After producing the final mp4, extract ≥3 spot-check frames and inspect them. Don't hand-wave success.
- **Extract clean copies** of reference scripts into the skill folder — do not import from the policy-diffs repo at runtime. The skill is self-contained and portable.

## Test target

The Halyard / Mastercard-SPME demo at `~/work/scribble/code/repos/carver/policy-diffs/credio-policies/dist/demo-video.mp4` is the gold standard.

- **Phase A baseline:** `halyard-demo.mp4` (~5:09, badge + waveform, no intro/outro/captions). Phase A is reproducible by setting every `features.*` flag in `demo_config.yaml` to false and omitting `session.pre_session` and the storyboard `pdfs:` block. Still the baseline for "the boring path works."
- **Phase B reference:** `halyard-demo-phaseb.mp4` (~5:18, intro slide + branded demo + burned captions + outro slide, PDF beat auto-wrapped). Produced from the same `examples/halyard-spme/` inputs with `features.intro_slide: true`, `features.outro_slide: true`, `features.captions: { enabled: true, mode: burned }`, and the `pdfs:` block declared.

Phase B is "done" when the skill reproduces both targets from the example inputs alone (no hand-edited intermediates).

## Workflow

Use the superpowers skills throughout this work — they are not optional or judgment-call:

- **superpowers:executing-plans** or **superpowers:subagent-driven-development** when working from a written plan (e.g., `docs/PHASE-A-TASKS.md`, `docs/PHASE-B-TASKS.md`). Default to subagent-driven-development for new code; executing-plans is fine for extraction/glue.
- **superpowers:test-driven-development** for any new implementation work — write tests first.
- **superpowers:brainstorming** before creative work that isn't already covered by an approved plan.
- **superpowers:systematic-debugging** when something breaks.
- **superpowers:verification-before-completion** before claiming any task done — fresh evidence, not assumptions.
- **superpowers:finishing-a-development-branch** at the end of a chunk of work.

The user has stated this as a durable preference: "always use superpowers." Don't make a cost/benefit judgment call to skip them — they're the default workflow.

## Tooling

- Python with `uv` for script execution
- `ffmpeg` + `ffprobe` for all video/audio work
- Playwright (Python) for recording; Playwright MCP (`mcp__plugin_playwright_playwright__*`) for site exploration
- OpenAI SDK for TTS (`gpt-4o-mini-tts`, voice `cedar`)
- PIL for badge frame rendering
- `pymupdf` for PDF page rasterization (Phase B)

Verify `ffmpeg`, `ffprobe`, and `uv` are on PATH before starting.
