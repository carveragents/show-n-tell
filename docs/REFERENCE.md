# Reference implementation paths

The working reference implementation lives at:

```
~/work/scribble/code/repos/carver/policy-diffs/
```

This is the **source material** you will extract scripts from when building Phase A. Read each file in full before extracting — the implementation has been hardened against several real-world failures (PDF download, TTS truncation, NODE_OPTIONS pollution, sticky-header layout, etc.) that you must preserve.

## Scripts to extract (Phase A)

| Source file (in policy-diffs repo) | Skill target | Notes |
|---|---|---|
| `scripts/demo_script.py` | DELETE — replace with YAML storyboard | The reference is a Python module with hardcoded BEATS. Skill version loads beats from a YAML file. |
| `scripts/render_voiceover.py` | `scripts/render_voiceover.py` | Generalize: read storyboard YAML, configurable voice/model, retry on truncation, ffprobe for durations. |
| `scripts/record_demo.py` | `scripts/record_demo.py` | Generalize: read storyboard YAML, parameterize CSS injection, optional pre-session for login. Auto-unset NODE_OPTIONS. |
| `scripts/mux_demo.py` | `scripts/mux_demo.py` | Mostly portable. Reads manifest + timings, builds synced audio, ffmpeg muxes. |
| `scripts/make_overlay.py` | `scripts/make_overlay.py` | Parameterize: logo path, ink/accent colors, badge size, pulse intensity. |
| `scripts/brand_video.py` | `scripts/brand_video.py` | Parameterize: badge position, waveform color/dimensions/mode. Extend to add intro/outro/captions (Phase B). |
| *(speed-up was inline ffmpeg)* | `scripts/speed_video.py` | New thin wrapper. Default 1.2x. Pass-through speed=1.0 means no-op. |

## Reference branding assets

- Carver Agents wordmark (already saved in policy-diffs repo): `credio-policies/dist/_recording_assets/carver_wordmark.png`. Original source: `https://cdn.prod.website-files.com/685e918182df0411e92bb871/686b56a986d9788a8c9ec9ec_ef3a0bb24570ecbd0982361d0d97a08a_Carver_black-07.png` (Carver Agents brand assets, hosted on Webflow CDN). It's black-on-transparent; the make_overlay script recolors to cream.
- Carver brand colors (from the site CSS):
  - Ink (primary): `#101828`
  - Ink deep (gradient inner): `#0c1322`
  - Lime (accent): `#bae424`
  - Cream (text on dark): `#fbf7f3`

## Reference example to ship in `examples/halyard-spme/`

To prove Phase A works, create an example that reproduces the existing Halyard demo:

```
examples/halyard-spme/
├── storyboard.yaml      # 28 beats translated to YAML (see CONTEXT.md for narration intent)
├── branding.yaml        # Carver colors, wordmark path, voice cedar
└── demo_config.yaml     # base_url localhost:8080, output path, speed 1.2
```

The full storyboard from the existing implementation is in `scripts/demo_script.py` in the policy-diffs repo — every `BEATS` entry has an `id`, `action` (a dict), and `narration` (a string). Convert directly to YAML.

Verify by running:

```bash
# Start the dist server
(cd ~/work/scribble/code/repos/carver/policy-diffs/credio-policies/dist && python3 -m http.server 8080) &

# Run the skill against the halyard example
# (exact command depends on how you wire SKILL.md — could be a single python entry point
#  or a sequence of scripts driven by Claude)
```

The output should be qualitatively identical to `credio-policies/dist/demo-video.mp4` (allowing for minor variance in waveform shape due to TTS regeneration).

## Things in the reference implementation you don't need to copy

- `scripts/demo_script.py` — replaced by YAML storyboard format
- The repo's other scripts (Mastercard pipeline, PDF extraction, etc.) — unrelated to the demo skill

## Things in the reference implementation you must preserve

- **NODE_OPTIONS unset** in record_demo.py — auto-clear it in the subprocess environment, don't make users remember
- **TTS truncation retry** — if the wav file is suspiciously small for its character count, regenerate
- **ffprobe for wav duration** — the Python `wave` module misparses OpenAI's wav header
- **scroll-margin-top recipe** — when a sticky header is injected, scroll targets need scroll-margin-top so they land below the header rather than under it
- **Per-beat timing model** — `action_ms` (wall-clock measured during recording) + `PRE_MS` (default 400) + `tts_ms` (from manifest) + `POST_MS` (default 700) defines the beat's total duration. The recorder holds for `PRE + tts + POST` after action completes; the audio track is built with `silence(action_ms + PRE) + tts + silence(POST)` per beat
- **2x supersample rendering** for PIL badge frames (smooth anti-aliased edges)
- **`atempo=1.2` + `setpts=PTS/1.2`** for combined audio+video speed-up while preserving pitch
- **`colorkey=0x000000:0.15:0`** for making `showwaves` black background transparent
- **`mode=p2p` + `scale=sqrt`** for visible waveform at typical speech amplitudes

## Other reference paths to know

- The final Halyard demo video: `~/work/scribble/code/repos/carver/policy-diffs/credio-policies/dist/demo-video.mp4`
- The dist site (served at localhost:8080 during recording): `~/work/scribble/code/repos/carver/policy-diffs/credio-policies/dist/`
- The site config that drives template rendering: `~/work/scribble/code/repos/carver/policy-diffs/config/sites/spme.yaml`
- The PDF wrapper template (recipe to extract for skill): `~/work/scribble/code/repos/carver/policy-diffs/credio-policies/dist/_recording_assets/pdf_view_2024-09_p60.html`
