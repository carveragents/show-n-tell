# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Claude Code skill named **show-n-tell** that produces narrated, branded demo videos of any website. Open source, MIT-licensed. The canonical home is `https://github.com/carveragents/show-n-tell`.

The skill is **user-global**: cloning it into `~/.claude/skills/show-n-tell/` (or `%USERPROFILE%\.claude\skills\show-n-tell\` on Windows) makes it available across every Claude Code session.

## Status — read before doing anything

- **Phase A and Phase B are shipped.** `SKILL.md`, `scripts/`, `helpers/`, `recipes/`, and `examples/halyard-spme/` are populated and produce the reference output end-to-end. Phase C items are tracked but deferred.
- All major design questions are answered in `docs/DESIGN-DECISIONS.md`. **Do not re-litigate them with the user** — treat them as binding.

## Reading order for a fresh session

Read these in order before writing any code:

1. `docs/CONTEXT.md` — what the skill produces, who it's for, what "good output" looks like
2. `docs/DESIGN-DECISIONS.md` — locked-in choices
3. `docs/ARCHITECTURE.md` — folder layout + per-script responsibilities
4. `docs/SCHEMAS.md`, `docs/SKILL-MD-OUTLINE.md`, `docs/GOTCHAS.md` — reference material, open as needed

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

## Python environment

A `pyproject.toml` at the repo root lists every runtime dependency. The standard workflow:

```bash
uv sync                                  # one-time: creates ./.venv with all deps pinned
uv run scripts/<name>.py …               # uv automatically uses ./.venv when pyproject.toml is present
```

Every script in `scripts/` and `helpers/` *also* carries a PEP 723 inline-dependency header, so `uv run scripts/foo.py` works even outside a synced project (uv creates an ephemeral isolated env per script). The two workflows are interchangeable. Both keep Python deps off the user's system Python — there is no `pip install` step anywhere in the pipeline.

When you add a new dependency to any script, update **both** the script's PEP 723 header and `pyproject.toml`'s `dependencies` list. They drift easily; check both whenever a runtime import is added.

## Phase boundaries

- **Phase A (MVP):** sites without login or PDFs. Reproduces the reference demo end-to-end. **Shipped.**
- **Phase B:** intro/outro slides, captions, login pre-session, PDF wrapper auto-gen, recipe library, bundled background-music library. **Shipped.**
- **Phase C:** multi-provider TTS, richer site-adaptation recipes (modal dismiss, lazy content waits, more login templates), failure recovery (retry a single failed beat without redoing the whole recording), audio crossfade at intro/main/outro seams. Out of scope for now.

Every Phase B feature is gated by a flag in `demo_config.yaml`. The Phase A baseline is reproducible by setting all `features.*` flags to false and omitting `session.pre_session` / the storyboard's `pdfs:` block.

## Things you must preserve

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
- **libass is required for caption burn-in** in `finalize_video.py`. Default Homebrew `ffmpeg` doesn't include it on macOS; the script surfaces an actionable error pointing at `brew install ffmpeg-full` (or switch to `captions.mode: srt-sidecar`). Linux distros' `ffmpeg` packages usually include libass already.
- **SRT path escaping in the ffmpeg `subtitles=` filter** is fragile across platforms. `finalize_video.py` copies the SRT into a CWD-local temp file and invokes ffmpeg with the file's basename so the filter arg stays simple — don't refactor it to pass an absolute path back in.
- **`force_style` commas inside the `subtitles=` filter arg** must be backslash-escaped or ffmpeg interprets them as filter-graph delimiters. Preserve the `\,` style separators already in `finalize_video.py`.
- **Encoder profile consistency for `-c copy` concat.** `make_intro_outro.py` and `brand_video.py` must produce matching framerate (25fps), h264 profile, audio sample rate (24000), and channel layout (mono) so `finalize_video.py` can concat with stream copy. If you adjust either script, audit the other.
- **Credentials in `${ENV_VAR}` form only, never literal in YAML.** `record_demo.py` runs `expand_env` after `interp_template` (so `${VAR}` resolves after `{{ base_url }}`). The logger masks the resolved `value` for any `fill` step. Use `raise ... from None` when surfacing missing-env errors so chained `__cause__` doesn't leak the underlying value through traceback rendering.
- **`finalize_video.py`'s concat is branch-dependent on `features.crossfade_seconds`.** When `0`, uses the concat demuxer with `-c copy` (instant, no re-encode). When `> 0`, uses an `xfade` + `acrossfade` filter graph (re-encodes the whole concat, ~30-60s for a 5-minute video, but produces soft seams). Don't "optimize" by always taking the copy path — you lose the seam polish. If you change `make_intro_outro.py`'s or `brand_video.py`'s codec profile, the copy path may also start failing; audit both.
- **Capture/explore/record viewport alignment.** `helpers/capture_auth.py`, `helpers/explore_page.py`, and `scripts/record_demo.py` must all use the same viewport for a given demo. Default 1440x900 across all three. If a demo customizes `recording.viewport`, pass the same `--viewport WxH` to capture_auth.py AND explore_page.py. Some sites fingerprint viewport size between capture and use; mismatch invalidates the session.
- **Bundled bg_music library is part of the skill.** `_assets/bg_music/library.json` and the six per-mood mp3+json pairs ship with the skill and are referenced by `_lib.resolve_bg_music_path()`. Do not relocate or rename without updating `library.json` and the path resolution in `_lib.py`.
- **Music attribution print at Phase 11.** When `branding.audio` resolves to a bundled track, `finalize_video.py` reads the sidecar JSON and prints `Music: <attribution_text>` plus license info. Don't suppress this print — it satisfies the license attribution requirement for bundled tracks. (Placeholder library entries ship with empty `attribution_text` so nothing prints until real tracks are curated — that's expected. Once curated, the print is mandatory.)

## Non-negotiable behavioral constraints

These come from the user's stated requirements — `docs/DESIGN-DECISIONS.md` is authoritative:

- **Claude drafts the storyboard; user reviews in plain English.** Never ask the user to edit YAML. Present beats as a numbered list with timestamps + narration quotes, accept natural-language feedback ("skip beat 7", "make beat 3 longer"), iterate until approved.
- **Narration must only quote numbers and names visible on screen at that beat.** No invented facts. The verification step extracts frames and checks this.
- **Refuse to proceed** if the user provides neither intent notes nor a logo. Generic demos with default branding are bad demos.
- **Verify before claiming success.** After producing the final mp4, extract ≥3 spot-check frames and inspect them. Don't hand-wave success.
- **The skill is self-contained and portable.** Don't introduce runtime imports from outside this folder. The skill must work after a fresh `git clone` + `uv sync`.
- **Skill orchestrates shell commands; user only does what fundamentally requires a human.** For OAuth-authenticated demos, this means: YOU launch `helpers/capture_auth.py` via Bash during Phase 5. The user only logs in in the browser window that opens. Never tell the user to "run this command yourself" when you can run it.

## Reference example

`examples/halyard-spme/` is the canonical end-to-end example — a storyboard, branding, and demo_config that together produce a complete demo of a public site. When in doubt about file structure, look there.

## Workflow

Use the superpowers skills throughout this work — they are not optional or judgment-call:

- **superpowers:executing-plans** or **superpowers:subagent-driven-development** when working from a written plan. Default to subagent-driven-development for new code; executing-plans is fine for refactors/glue.
- **superpowers:test-driven-development** for any new implementation work — write tests first.
- **superpowers:brainstorming** before creative work that isn't already covered by an approved plan.
- **superpowers:systematic-debugging** when something breaks.
- **superpowers:verification-before-completion** before claiming any task done — fresh evidence, not assumptions.
- **superpowers:finishing-a-development-branch** at the end of a chunk of work.

The user has stated this as a durable preference: "always use superpowers." Don't make a cost/benefit judgment call to skip them — they're the default workflow.

## Tooling

- Python ≥ 3.10 with `uv` (creates and manages the venv automatically)
- `ffmpeg` + `ffprobe` for all video/audio work (linked with `libass` if you want burned captions)
- Playwright (Python) for recording; Playwright MCP (`mcp__plugin_playwright_playwright__*`) for site exploration
- OpenAI SDK for TTS (`gpt-4o-mini-tts`, voice `cedar`)
- PIL for badge frame rendering
- `pymupdf` for PDF page rasterization (Phase B)

Verify `ffmpeg`, `ffprobe`, and `uv` are on PATH before starting. Cross-platform install instructions live in the top-level `README.md`.
