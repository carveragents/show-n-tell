# Phase A — concrete task checklist

Goal: a working skill that produces a fully-branded video for sites **without** login or PDFs. Validated by reproducing the Halyard demo end-to-end.

**Estimated effort: ~4 hours of focused work.** Do not attempt Phase B in the same session.

---

## Pre-work (5 min)

- [ ] Read `PLAN.md`, `CONTEXT.md`, `DESIGN-DECISIONS.md`, `REFERENCE.md`, `ARCHITECTURE.md`. (You should have already.)
- [ ] Verify reference repo exists at `~/work/scribble/code/repos/carver/policy-diffs/`. If not, ask the user where it moved.
- [ ] Verify `ffmpeg`, `ffprobe`, and `uv` are on PATH. Install if missing.

---

## Task 1 — Folder scaffolding (5 min)

- [ ] `mkdir -p ~/.claude/skills/demo-video-from-site/{scripts,templates,examples/halyard-spme,recipes}`
- [ ] Verify directory tree matches `ARCHITECTURE.md`.

---

## Task 2 — Extract and parameterize `make_overlay.py` (30 min)

Source: `~/work/scribble/code/repos/carver/policy-diffs/scripts/make_overlay.py`

Parameterize:

- [ ] `WORDMARK` path → from `branding.yaml`'s `logo.path`
- [ ] `INK`, `INK_DEEP`, `LIME`, `CREAM` → from `branding.yaml`'s `colors` dict
- [ ] `OUT_DIR` → from working dir + `_assets/overlay_frames/`
- [ ] `BADGE_SIZE`, `FRAMES`, `LOGO_WIDTH_RATIO` → keep as defaults but allow override via CLI flags

Auto-detect:

- [ ] If logo is monochrome-on-transparent → recolor to cream. If full-color → paste as-is.

CLI interface:

```bash
python scripts/make_overlay.py --working-dir <path> [--frames 50] [--badge-size 120]
```

Reads `<working-dir>/branding.yaml` for logo + colors. Writes frames to `<working-dir>/_assets/overlay_frames/frame_NNNN.png`.

- [ ] Test by running against the halyard-spme example branding.yaml (Task 7). Inspect frame_0010.png to verify badge renders correctly.

---

## Task 3 — Extract and parameterize `render_voiceover.py` (45 min)

Source: `~/work/scribble/code/repos/carver/policy-diffs/scripts/render_voiceover.py`

Generalize:

- [ ] Read storyboard from YAML, not Python module
- [ ] `MODEL`, `VOICE`, `INSTRUCTIONS` → from `branding.yaml`'s `voice` block
- [ ] OUT_DIR → working-dir's `_voiceover/`
- [ ] Add **size-anomaly retry**: after each TTS call, sanity-check wav size vs character count. If suspiciously small (< 50% of expected), regenerate (up to 2 retries).
- [ ] Use **ffprobe** for duration measurement (not `wave` module — see GOTCHAS #3).
- [ ] **Diff-aware regeneration**: if `manifest.json` already exists, only regenerate wavs whose narration changed (hash-compare). Add `--clean` flag to nuke and regen all.

CLI:

```bash
python scripts/render_voiceover.py --working-dir <path> [--clean]
```

Reads `<working-dir>/{storyboard,branding}.yaml`. Writes `<working-dir>/_voiceover/{<beat_id>.wav, manifest.json}`.

- [ ] Test by running against halyard storyboard. Verify all 28 wavs produced with sensible durations.

---

## Task 4 — Extract and parameterize `record_demo.py` (60 min)

Source: `~/work/scribble/code/repos/carver/policy-diffs/scripts/record_demo.py`

This is the most complex extraction. Carefully preserve:

- [ ] **NODE_OPTIONS auto-clear**: at the top of `main()`, `os.environ.pop("NODE_OPTIONS", None)`. Don't rely on the user.
- [ ] **Action grammar interpreter** for all action types listed in SCHEMAS.md. Phase A subset: `goto`, `goto_and_scroll`, `scroll_into_view`, `scroll_y`, `hover`, `click` (with optional `then_scroll`).
- [ ] **CSS injection** at every page load (via `context.add_init_script`) using `branding.yaml`'s `recording_css` field. If empty, skip injection.
- [ ] **Per-beat timing measurement**: action_ms = wall-clock from action start to end. Total beat wait = `PRE_NARRATION_MS + tts_ms + POST_NARRATION_MS`.
- [ ] **{{ base_url }} interpolation** in action URLs from `demo_config.yaml`.

Generalize:

- [ ] `VIEWPORT`, `framerate`, `PRE_NARRATION_MS`, `POST_NARRATION_MS` → from `demo_config.yaml`.

Add for Phase B compatibility (but no-op for Phase A):

- [ ] Wiring for `session.pre_session` block — accept the config field, log "skipping pre-session in Phase A" if present.

CLI:

```bash
python scripts/record_demo.py --working-dir <path>
```

Reads `{storyboard, branding, demo_config}.yaml` + `_voiceover/manifest.json`. Writes `_intermediate/reference.webm` + `_voiceover/timings.json`.

- [ ] Test by running against the halyard demo with the dist server running at localhost:8080. Verify the webm gets recorded and timings.json is sensible.

---

## Task 5 — Extract `mux_demo.py` (15 min)

Source: `~/work/scribble/code/repos/carver/policy-diffs/scripts/mux_demo.py`

Mostly direct port. Generalize:

- [ ] Read paths from working dir
- [ ] Use `branding.yaml`'s `voice.sample_rate` if specified (default 24000)
- [ ] Use ffmpeg encoder options from defaults: `-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -c:a aac -b:a 192k`

CLI:

```bash
python scripts/mux_demo.py --working-dir <path>
```

Reads manifest + timings + reference.webm + per-beat wavs. Writes `_intermediate/muxed.mp4`.

- [ ] Test: muxed.mp4 should have audio and video locked. Open in QuickTime, verify sync.

---

## Task 6 — New: `speed_video.py` (15 min)

No reference implementation; build from the inline ffmpeg command we used:

```python
# Conceptually:
ffmpeg -i input.mp4 -filter_complex "[0:v]setpts=PTS/<M>[v];[0:a]atempo=<M>[a]" \
  -map "[v]" -map "[a]" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 192k \
  output.mp4
```

CLI:

```bash
python scripts/speed_video.py --input <muxed.mp4> --output <speed.mp4> --multiplier 1.2
```

- [ ] If multiplier == 1.0, just copy through (no re-encode).
- [ ] If multiplier outside 0.5–2.0, error.
- [ ] Test: input duration N, output duration N / multiplier (within 100ms).

---

## Task 7 — Extract `brand_video.py` (45 min)

Source: `~/work/scribble/code/repos/carver/policy-diffs/scripts/brand_video.py`

Generalize:

- [ ] Read input mp4, overlay frames dir, branding config from working dir
- [ ] Compute layout positions (badge canvas position, waveform position) from `branding.yaml` overrides if provided, else defaults
- [ ] Waveform color from `branding.yaml`'s `colors.accent`
- [ ] Waveform width/height from `branding.yaml`'s `waveform` block (optional)

Phase A scope:

- [ ] Bottom-left badge + waveform only. No intro/outro/captions yet (those are Phase B).

CLI:

```bash
python scripts/brand_video.py --working-dir <path> --input <speed.mp4> --output <demo.mp4>
```

- [ ] Test against halyard demo: extract a few frames, confirm badge appears bottom-left with Carver wordmark and waveform below.

---

## Task 8 — Build halyard-spme example (45 min)

Reproduce the existing demo as the canonical example.

- [ ] Create `examples/halyard-spme/storyboard.yaml` — translate every `BEATS` entry from `scripts/demo_script.py` in the policy-diffs repo to YAML format per SCHEMAS.md. All 28 beats.
- [ ] Create `examples/halyard-spme/branding.yaml`:
  ```yaml
  brand: { name: "Carver Agents" }
  logo: { path: "./_assets/carver_wordmark.png" }   # copy from policy-diffs repo
  colors: { ink: "#101828", ink_deep: "#0c1322", accent: "#bae424", cream: "#fbf7f3" }
  voice: { provider: openai, model: gpt-4o-mini-tts, voice: cedar, tone: explanatory, instructions: "..." }
  recording_css: |
    .change-header { position: sticky; top: 0; background: var(--surface, #fff); z-index: 40; padding-top: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--border, #e5e7eb); }
    section.tab-panel, section.tab-panel .file-panel, section.tab-panel .col, section.tab-panel .prose, section.tab-panel pre, .extraction-warning, .callout { scroll-margin-top: 130px; }
    .overview-section { scroll-margin-top: 24px; }
  ```
- [ ] Create `examples/halyard-spme/demo_config.yaml`:
  ```yaml
  site: { base_url: "http://localhost:8080" }
  output: { filename: "halyard-demo.mp4", working_dir: "~/demo-videos/halyard-spme-test", speed_multiplier: 1.2 }
  features: { intro_slide: false, outro_slide: false, captions: { enabled: false }, brand_overlay: true }
  recording: { viewport: { width: 1440, height: 900 }, framerate: 25, pre_narration_ms: 400, post_narration_ms: 700 }
  ```
- [ ] Copy the Carver wordmark from `~/work/scribble/code/repos/carver/policy-diffs/credio-policies/dist/_recording_assets/carver_wordmark.png` into the example's `_assets/` for reference.

- [ ] **End-to-end test**:
  1. Start dist server: `(cd ~/work/scribble/code/repos/carver/policy-diffs/credio-policies/dist && python3 -m http.server 8080) &`
  2. Setup working dir: `mkdir -p ~/demo-videos/halyard-spme-test && cp examples/halyard-spme/*.yaml ~/demo-videos/halyard-spme-test/ && cp -r examples/halyard-spme/_assets ~/demo-videos/halyard-spme-test/`
  3. Run pipeline:
     ```bash
     python scripts/make_overlay.py --working-dir ~/demo-videos/halyard-spme-test
     python scripts/render_voiceover.py --working-dir ~/demo-videos/halyard-spme-test
     python scripts/record_demo.py --working-dir ~/demo-videos/halyard-spme-test
     python scripts/mux_demo.py --working-dir ~/demo-videos/halyard-spme-test
     python scripts/speed_video.py --input <muxed> --output <speed> --multiplier 1.2
     python scripts/brand_video.py --working-dir ~/demo-videos/halyard-spme-test --input <speed> --output <final>
     ```
  4. Extract spot-check frames at t=10, 100, 200, 300 from final mp4.
  5. Compare to the reference video at `~/work/scribble/code/repos/carver/policy-diffs/credio-policies/dist/demo-video.mp4`.

Acceptance: visual parity is "close enough" — exact byte-for-byte match impossible due to TTS variance. The branded badge should appear identical (same wordmark, same colors, same waveform). Narration should sound the same voice. Overall flow should match. Duration ≈ 5 min ± 30 s.

---

## Task 9 — Write SKILL.md (45 min)

Reference: `docs/SKILL-MD-OUTLINE.md`. Don't just copy the outline — write it as a concrete playbook with example dialogue, exact commands, and the user-review presentation format. Keep under 400 lines.

- [ ] Add frontmatter (name + description per SKILL-MD-OUTLINE.md).
- [ ] Each phase has: trigger conditions, the action(s) Claude takes, expected outputs.
- [ ] Include the "non-technical storyboard review" format inline so Claude has a template.
- [ ] Cross-reference: link to GOTCHAS.md, SCHEMAS.md, examples/halyard-spme/.

---

## Task 10 — Template stubs (15 min)

- [ ] `templates/storyboard.example.yaml` — 3-beat skeleton with comments
- [ ] `templates/branding.example.yaml` — populated with placeholder values, comments explaining each
- [ ] `templates/demo_config.example.yaml` — populated minimal config

These get copied to working dirs as starting points when a fresh demo is initialized.

---

## Task 11 — Final integration test (30 min)

- [ ] Simulate a fresh user invoking the skill:
  - Start in a new shell with no working dir
  - Imagine target site is the Halyard dist site
  - Walk through the workflow as if you were Claude reading SKILL.md
  - Run each script, observe outputs
- [ ] Document any pain points or gaps in `docs/PHASE-B-TASKS.md` (create if needed) — these are surface-level issues to fix in Phase B.

---

## Phase A acceptance criteria

- [ ] All scripts run end-to-end with `--working-dir` flag
- [ ] Halyard example reproduces visually-equivalent demo to the reference
- [ ] SKILL.md is complete and a fresh Claude can pick it up
- [ ] NODE_OPTIONS workaround is automatic
- [ ] TTS regenerates only changed beats on re-run
- [ ] No part of the pipeline requires the user to know the internal script invocations — SKILL.md drives everything

## Stop after Phase A

Do not attempt to build Phase B (intro/outro, captions, login, PDF auto-wrap) in the same session. Stop, check in with the user, get feedback on Phase A before extending.
