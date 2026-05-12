# Target folder layout

```
~/.claude/skills/demo-video-from-site/
├── SKILL.md                          # Claude's entry point — see SKILL-MD-OUTLINE.md
├── docs/                             # (already exists — these planning files)
│   ├── PLAN.md
│   ├── CONTEXT.md
│   ├── REFERENCE.md
│   ├── DESIGN-DECISIONS.md
│   ├── ARCHITECTURE.md               ← you are here
│   ├── SCHEMAS.md
│   ├── SKILL-MD-OUTLINE.md
│   ├── GOTCHAS.md
│   └── PHASE-A-TASKS.md
├── scripts/                          # Phase A
│   ├── render_voiceover.py           # storyboard YAML → wavs + manifest
│   ├── record_demo.py                # Playwright recorder + action interpreter
│   ├── mux_demo.py                   # synced audio mux
│   ├── speed_video.py                # atempo + setpts wrapper
│   ├── make_overlay.py               # PIL badge frames renderer
│   └── brand_video.py                # ffmpeg compositor for badge + waveform
├── scripts/                          # Phase B additions
│   ├── make_intro_outro.py           # generates intro + end-card slides
│   └── make_captions.py              # SRT generator from storyboard + timings
├── helpers/                          # Phase B
│   ├── login.py                      # pre-session step interpreter
│   ├── pdf_wrapper.py                # auto-generates HTML wrappers for PDFs
│   └── site_explorer.py              # Playwright helpers Claude uses during exploration
├── recipes/                          # opt-in site adaptations
│   ├── sticky_header.css.j2
│   ├── inline_pdf.html.j2
│   └── login_form_fill.yaml
├── templates/                        # reference YAML structures
│   ├── storyboard.example.yaml
│   ├── branding.example.yaml
│   └── demo_config.example.yaml
└── examples/                         # reference complete configs
    └── halyard-spme/                 # reproduction of the demo we built
        ├── storyboard.yaml
        ├── branding.yaml
        └── demo_config.yaml
```

## Working directory model (per demo)

When a user invokes the skill for a new demo, Claude creates a fresh working directory and writes all generated artifacts there. The skill folder stays clean.

Default working directory: `~/demo-videos/<demo-slug>/` where `<demo-slug>` is derived from the target URL or user-provided name.

```
~/demo-videos/acme-app-2026-05-12/
├── storyboard.yaml                   # Claude-drafted + user-reviewed
├── branding.yaml                     # links to logo path or pre-downloaded asset
├── demo_config.yaml                  # target URL, output filename, login config
├── _assets/
│   ├── logo.png                      # downloaded/copied from branding source
│   └── overlay_frames/               # rendered badge animation frames
│       └── frame_NNNN.png
├── _voiceover/
│   ├── <beat_id>.wav                 # one per beat
│   ├── manifest.json                 # beat IDs + durations
│   └── full.wav                      # merged synced track
├── _intermediate/
│   ├── reference.webm                # Playwright raw recording
│   ├── timings.json                  # per-beat measured action_ms
│   ├── muxed.mp4                     # audio + video locked together
│   └── speed.mp4                     # after atempo/setpts
└── demo.mp4                          # final branded output
```

The presence of intermediate artifacts is what makes re-runs cheap. If only narration tone changes, only TTS regenerates + audio rebuilds — recording is not re-run.

## Script responsibilities (each ≤ 250 lines)

### `scripts/render_voiceover.py`
- Inputs: `storyboard.yaml`, `branding.yaml` (for voice), working dir
- Reads each beat's narration
- Calls OpenAI TTS with retry-on-truncation (size sanity check vs character count)
- Saves `_voiceover/<beat_id>.wav` per beat
- Measures duration via ffprobe
- Writes `_voiceover/manifest.json` with `[{id, chars, duration_seconds, wav_path}, ...]`

### `scripts/record_demo.py`
- Inputs: `storyboard.yaml`, `demo_config.yaml` (target URL, login session, viewport), `_voiceover/manifest.json`, working dir
- Auto-unsets `NODE_OPTIONS` in subprocess env (cmux workaround)
- Launches Playwright headless Chromium
- If `demo_config.yaml` has `session.pre_session`, runs those steps first (Phase B)
- Injects optional CSS from `branding.yaml`'s `recording_css` field (e.g., sticky-header recipe)
- For each beat:
  - Measure wall-clock time of action execution
  - Hold `PRE_NARRATION_MS + tts_duration_ms + POST_NARRATION_MS`
  - Record `action_ms` to timings
- Saves `_intermediate/reference.webm` and `_voiceover/timings.json`

### `scripts/mux_demo.py`
- Inputs: manifest, timings, raw webm, working dir
- Builds per-beat audio segment: `silence(action_ms + PRE_MS) + tts + silence(POST_MS)`
- Concatenates all segments via pydub → `_voiceover/full.wav`
- ffmpeg muxes video + audio → `_intermediate/muxed.mp4` (h264 + AAC re-encode for universal mp4 playback)

### `scripts/speed_video.py`
- Inputs: any mp4, speed multiplier
- ffmpeg one-liner: `setpts=PTS/M` + `atempo=M` (preserves pitch)
- atempo supports 0.5–2.0; if speed is outside this, refuse
- If multiplier is 1.0, just copy through

### `scripts/make_overlay.py`
- Inputs: `branding.yaml` (logo, colors), working dir
- Renders badge as a 2-second loop of N frames (default 50 @ 25fps)
- Static badge composed once via PIL: radial gradient circle, ring border, halo, recolored logo
- Pulse rings overlaid per frame at different phases
- Saves `_assets/overlay_frames/frame_NNNN.png`

### `scripts/brand_video.py`
- Inputs: any mp4, branding config, overlay frames, working dir
- ffmpeg `-stream_loop -1` for badge frame sequence
- `showwaves` filter on audio with `mode=p2p:scale=sqrt:colors=<accent>`
- `colorkey=0x000000:0.15:0` to remove black bg
- Overlay badge frames at bottom-left
- Overlay waveform below badge
- Output → working dir's final mp4

(Phase B: also prepend intro slide + append outro slide via concat filter; burn captions via subtitles filter if enabled)

## Data flow

```
storyboard.yaml ─┬─→ render_voiceover.py ─→ manifest.json + N wavs
                 │
                 └─→ record_demo.py    ─→ reference.webm + timings.json
                                            ↓
manifest + timings + webm ──→ mux_demo.py ─→ muxed.mp4
                                            ↓
                                speed_video.py ─→ speed.mp4
                                            ↓
                          ┌─ branding.yaml ─→ make_overlay.py ─→ overlay frames
                          │                                       ↓
                          └────────────→ brand_video.py ──→ demo.mp4
```

## SKILL.md as orchestrator

SKILL.md (sibling to docs/) doesn't run any of these scripts itself. It contains the **workflow Claude executes**: collect inputs from user, draft storyboard, review with user, then invoke each script in sequence and report progress. The scripts are dumb pipes; Claude is the conductor.

See `SKILL-MD-OUTLINE.md` for what to put in SKILL.md.
