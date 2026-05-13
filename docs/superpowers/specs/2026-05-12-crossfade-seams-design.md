# Crossfade at intro/main/outro seams — design

**Date:** 2026-05-12
**Status:** Approved
**Scope:** Phase C item promoted to ship-now per user direction ("important for demo polish").

## Problem

The Phase B finalize stage uses ffmpeg's concat demuxer with `-c copy` to glue intro + branded demo + outro into the final mp4. The seams are hard cuts on both video (sudden cut from intro slide to demo's first frame) and audio (silent intro audio → silent leading pad on demo). The result looks chopped at the seams. For external-prospect demos this reads as "amateur" rather than "intentional."

## Goal

Smooth, professional transitions between intro→main→outro using ffmpeg's `xfade` (video) and `acrossfade` (audio) filters. Configurable per-demo so users who don't want to pay the re-encode cost can opt out.

## Non-goals

- Animated motion transitions (slide, wipe, push). A simple cross-dissolve is enough — anything fancier draws attention to the seam itself.
- Per-seam configuration (different crossfade duration on intro vs outro). Single global duration is sufficient.
- Audio ducking, envelope shaping beyond the standard `acrossfade` triangular curve.

## Decisions

| Question | Decision |
|---|---|
| Audio-only vs audio+video crossfade? | **Both.** Audio-only with hard video cut feels weird. |
| Crossfade duration? | **Configurable** via `features.crossfade_seconds`. Default 0.5s when omitted. |
| Opt-in vs opt-out? | **Always on when intro/outro enabled.** Set `crossfade_seconds: 0` to opt out (gets the old `-c copy` fast path). |
| Single-pass filter graph vs separate concat step? | **Separate.** Keep the existing burn-then-concat ordering; only the concat step changes. Minimum delta. |

## Surface area

One new config field:

```yaml
# demo_config.yaml
features:
  intro_slide: true
  outro_slide: true
  captions:
    enabled: true
    mode: "burned"
  crossfade_seconds: 0.5    # NEW: 0 = hard cuts (fast `-c copy`), >0 = xfade + acrossfade
  brand_overlay: true
```

**Validation rules:**
- Must be a non-negative number. Reject negatives with a clear error.
- Soft cap at 2.0s. Beyond that, refuse — eats too much intro/outro content.
- Must be less than every segment's duration (runtime check after probing). Otherwise xfade produces garbage.
- 0.0 → existing concat demuxer fast path. No semantic change for users who keep it at 0.
- Field omitted → treat as 0.5 (the default).

## Implementation

### `scripts/finalize_video.py`

The current `concat_segments(segments, output_path, tmp_dir)` function gets a new `crossfade_seconds` parameter and branches:

```python
def concat_segments(segments, output_path, tmp_dir, crossfade_seconds):
    if crossfade_seconds <= 0:
        _concat_copy(segments, output_path, tmp_dir)   # existing path
    else:
        _concat_xfade(segments, output_path, crossfade_seconds)   # new path
```

`_concat_copy` is the current concat-demuxer code, unchanged.

`_concat_xfade` builds a single `ffmpeg -filter_complex` invocation:

1. Probe each segment's video duration via `ffprobe` (use the helper that already exists in this file).
2. Validate `crossfade_seconds < min(durations)`. Hard-fail if not.
3. Build the filter chain. For N segments and crossfade duration D:
   - Video: chained `xfade` filters. First xfade offsets at `dur(seg_0) - D`. Each subsequent xfade offsets at `prev_offset + dur(seg_i) - D`.
   - Audio: chained `acrossfade` filters with `d=D:c1=tri:c2=tri`. The triangular curve is the standard choice for symmetric voice/silence transitions.
4. Map `[v]` and `[a]` outputs. Re-encode with the same profile as the rest of the pipeline (`libx264 -preset medium -crf 20 -pix_fmt yuv420p -c:a aac -b:a 192k`).

**Filter graph shape** (N = 3):

```
[0:v][1:v]xfade=transition=fade:duration=D:offset=(dur0-D)[v01];
[v01][2:v]xfade=transition=fade:duration=D:offset=(dur0+dur1-2*D)[v];
[0:a][1:a]acrossfade=d=D:c1=tri:c2=tri[a01];
[a01][2:a]acrossfade=d=D:c1=tri:c2=tri[a]
```

For N = 2 (only one of intro/outro present): single pair.

### Caller wiring in `main()`

Read `crossfade_seconds` from demo_config:

```python
crossfade_seconds = features.get("crossfade_seconds", 0.5)
if not isinstance(crossfade_seconds, (int, float)) or crossfade_seconds < 0:
    sys.exit(f"features.crossfade_seconds must be >= 0, got {crossfade_seconds!r}")
if crossfade_seconds > 2.0:
    sys.exit(f"features.crossfade_seconds capped at 2.0, got {crossfade_seconds}")
```

Pass into `concat_segments(segments, output_path, tmp_dir, crossfade_seconds)`.

### `templates/demo_config.example.yaml`

Add the new field with an inline comment:

```yaml
  brand_overlay: true
  crossfade_seconds: 0.5     # 0 = hard cuts (fast). >0 = xfade+acrossfade at intro/main/outro seams.
```

### `examples/halyard-spme/demo_config.yaml`

Add `crossfade_seconds: 0.5` so the canonical example exercises the feature.

### `docs/SCHEMAS.md`

Document `features.crossfade_seconds` under the `features.*` section. Note the 0 = fast-path semantic and the 2.0s cap.

### `docs/GOTCHAS.md`

New entry: `D < min(durations)` constraint, and how crossfade shortens final video duration by `(N-1) * D` seconds.

### `CLAUDE.md`

Add to preserve-list: the concat path is now branch-dependent on `crossfade_seconds`. If someone "optimizes" by always using `-c copy`, they lose the seam polish.

## Edge cases

| Case | Behavior |
|---|---|
| `crossfade_seconds: 0` | Concat demuxer with `-c copy` (current behavior, instant). |
| Negative value | Hard-fail with clear error. |
| > 2.0 | Hard-fail with clear error citing the cap. |
| `D >= min(segment durations)` | Hard-fail at runtime (after probing) — xfade would produce a black/garbled output. |
| Only intro enabled (2 segments) | Single xfade pair. General loop handles this. |
| Only outro enabled (2 segments) | Same — single xfade pair. |
| Neither intro nor outro enabled | `concat_segments` isn't called; existing pass-through/burn-only paths run. |
| Captions burned, crossfade on | Captions are pre-burned into the middle (existing behavior). The first/last `D` seconds of the middle's visible content cross-dissolve with intro/outro. Since the first caption doesn't appear until ~action_ms + pre_ms (~1s+) and the last ends well before middle's end (per the existing 336ms slack), no caption is mid-displaying during the dissolve. No timing fix needed. |

## Final video duration math

With hard cuts: `final = intro + middle + outro` (e.g., 4 + 308.6 + 5 = 317.6s).

With crossfade D and 3 segments: `final = intro + middle + outro - 2*D` (e.g., 4 + 308.6 + 5 - 1.0 = 316.6s).

With crossfade D and N segments: `final = sum(durations) - (N-1)*D`.

Document in the script's print summary so the user knows what they got.

## Testing

End-to-end against the existing Halyard Phase B test working-dir:

1. **Default behavior** (`crossfade_seconds: 0.5`): re-run finalize. Verify final mp4 duration ≈ 316.6s (vs Phase B's 317.6s). Extract frames at the seam transitions (around t=3.5s and t=312s) and confirm they show a dissolve, not a hard cut.
2. **Opt-out** (`crossfade_seconds: 0`): run finalize. Verify final mp4 is byte-identical to the existing Phase B output (or close — ffmpeg may re-stamp timestamps, but duration should match).
3. **Custom duration** (`crossfade_seconds: 1.0`): verify final mp4 duration ≈ 315.6s.
4. **Invalid values**: `crossfade_seconds: -0.5` rejects; `3.0` rejects; `5.0` rejects.
5. **Edge: only intro on**: set `outro_slide: false`. Verify final mp4 is `intro + middle - D` long, dissolves at the seam.
6. **Captions still align**: with crossfade + burned captions both on, extract a frame mid-caption and verify text reads correctly.

## What this doesn't address

- The audio crossfade between silent intro audio and the demo's first beat is technically a fade-in of the demo audio. This is what we want — the demo's `pre_narration_ms` silence pad already provides headroom so no narration gets clipped. But if someone changes `pre_narration_ms` to 0, the crossfade could eat into the first beat's TTS. Document this in `GOTCHAS.md`: `crossfade_seconds + 100ms` should be less than `pre_narration_ms`.
- xfade transition style is hardcoded to `fade` (cross-dissolve). Other styles (`slideleft`, `circleopen`, etc.) might be exposed later. Not now.

## Acceptance

- `features.crossfade_seconds: 0.5` produces a finalized Halyard demo with dissolves at both seams. Frame extraction shows mid-dissolve frames containing pixels from both segments.
- `features.crossfade_seconds: 0` produces a finalized demo with hard cuts identical to the current Phase B output.
- Invalid values produce clear error messages, not cryptic ffmpeg failures.
- No regression in any other Phase A or B output.
