# Crossfade at intro/main/outro seams — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hard-cut concat at intro/main/outro seams in `scripts/finalize_video.py` with a configurable xfade (video) + acrossfade (audio) dissolve, so demos look polished at the transitions.

**Architecture:** Add a `features.crossfade_seconds` knob to `demo_config.yaml`. When `> 0`, swap the concat-demuxer fast path for an `ffmpeg -filter_complex` invocation that chains `xfade` (video) and `acrossfade` (audio) across N segments. Keep the existing `-c copy` path available at `crossfade_seconds: 0`. Validate the value at config-load time and at runtime against segment durations.

**Tech Stack:** Python 3.10+ via uv PEP 723 inline metadata; ffmpeg (with `xfade` and `acrossfade` filters, present in stock builds). No new deps.

**Spec:** `docs/superpowers/specs/2026-05-12-crossfade-seams-design.md`.

---

## File Structure

| File | Role | Action |
|---|---|---|
| `scripts/finalize_video.py` | Add `_build_xfade_filter`, `_validate_crossfade_seconds`, split `concat_segments` into `_concat_copy` + `_concat_xfade`. Wire crossfade_seconds from demo_config through to concat. | Modify |
| `templates/demo_config.example.yaml` | Add `crossfade_seconds: 0.5` line. | Modify |
| `examples/halyard-spme/demo_config.yaml` | Add `crossfade_seconds: 0.5` so canonical exercise covers it. | Modify |
| `docs/SCHEMAS.md` | Document the new field under `features.*`. | Modify |
| `docs/GOTCHAS.md` | New entry: D < min(durations) constraint, duration math. | Modify |
| `CLAUDE.md` | Preserve-list: concat path is branch-dependent. | Modify |

The unit-of-change is `finalize_video.py`. Everything else is documentation/config follow-up.

---

## Task 1: Filter-graph builder (pure function)

The xfade chain offsets are easy to get wrong, so isolate the string-building logic into a pure, testable function before wiring it in.

**Files:**
- Modify: `scripts/finalize_video.py` (add new function before `concat_segments`)

- [ ] **Step 1: Write the function and an inline self-check at the bottom of finalize_video.py for ad-hoc verification.**

Add to `scripts/finalize_video.py` immediately before `def concat_segments(...)`:

```python
def _build_xfade_filter(durations: list[float], crossfade_seconds: float) -> str:
    """Build the -filter_complex string for xfade + acrossfade across N segments.

    For N segments with durations d_0..d_{N-1} and crossfade D:
      Video chain: each xfade's offset = sum(d_0..d_{i-1}) - i*D
      Audio chain: acrossfade with duration D, triangular curves

    Returns the filter graph string. The caller pipes it into
    `ffmpeg -filter_complex` and maps [v]/[a] to the output.
    """
    n = len(durations)
    if n < 2:
        raise ValueError(f"xfade needs >= 2 segments, got {n}")
    if crossfade_seconds <= 0:
        raise ValueError(f"crossfade_seconds must be > 0, got {crossfade_seconds}")
    if crossfade_seconds >= min(durations):
        raise ValueError(
            f"crossfade_seconds={crossfade_seconds} must be less than the "
            f"shortest segment duration ({min(durations):.2f}s)"
        )

    d = crossfade_seconds
    video_parts: list[str] = []
    audio_parts: list[str] = []
    prev_v = "[0:v]"
    prev_a = "[0:a]"
    # Cumulative offset where the next xfade should begin, measured on the
    # output timeline (each xfade shaves `d` off the next segment).
    cum_offset = durations[0] - d
    for i in range(1, n):
        v_out = f"[v{i:02d}]" if i < n - 1 else "[v]"
        a_out = f"[a{i:02d}]" if i < n - 1 else "[a]"
        video_parts.append(
            f"{prev_v}[{i}:v]xfade=transition=fade:duration={d}:offset={cum_offset:.4f}{v_out}"
        )
        audio_parts.append(
            f"{prev_a}[{i}:a]acrossfade=d={d}:c1=tri:c2=tri{a_out}"
        )
        prev_v, prev_a = v_out, a_out
        if i < n - 1:
            cum_offset += durations[i] - d
    return ";".join(video_parts + audio_parts)
```

- [ ] **Step 2: Verify via an ad-hoc run.**

Run from the project root:

```bash
uv run --with pyyaml python - <<'PY'
import sys
sys.path.insert(0, "scripts")
from finalize_video import _build_xfade_filter

# 3 segments: intro 4s, middle 308.6s, outro 5s; crossfade 0.5s.
g = _build_xfade_filter([4.0, 308.6, 5.0], 0.5)
print(g)
print()

# 2 segments (only one of intro/outro on).
g2 = _build_xfade_filter([4.0, 308.6], 0.5)
print(g2)
print()

# Error cases.
for case in [([4.0], 0.5), ([4.0, 5.0], 0.0), ([4.0, 5.0], 4.5)]:
    try:
        _build_xfade_filter(*case)
        print(f"unexpected success: {case}")
    except ValueError as e:
        print(f"OK rejected {case}: {e}")
PY
```

Expected output (whitespace approximate):

```
[0:v][1:v]xfade=transition=fade:duration=0.5:offset=3.5000[v01];[v01][2:v]xfade=transition=fade:duration=0.5:offset=311.6000[v];[0:a][1:a]acrossfade=d=0.5:c1=tri:c2=tri[a01];[a01][2:a]acrossfade=d=0.5:c1=tri:c2=tri[a]

[0:v][1:v]xfade=transition=fade:duration=0.5:offset=3.5000[v];[0:a][1:a]acrossfade=d=0.5:c1=tri:c2=tri[a]

OK rejected ([4.0], 0.5): xfade needs >= 2 segments, got 1
OK rejected ([4.0, 5.0], 0.0): crossfade_seconds must be > 0, got 0.0
OK rejected ([4.0, 5.0], 4.5): crossfade_seconds=4.5 must be less than the shortest segment duration (4.00s)
```

Verify each cumulative offset:
- Seam 0→1 at offset 3.5 (intro is 4s, dissolve starts 0.5s before its end).
- Seam 1→2 at offset 311.6 (= 3.5 + 308.6 − 0.5 + 0.5 − 0.5 … = 3.5 + 308.1 = 311.6). Intuitively: the second xfade begins 0.5s before the END of the v01 output. v01 ends at offset 3.5 + 0.5 + (308.6 − 0.5) = 312.1, so offset for the second xfade = 312.1 − 0.5 = 311.6. ✓

- [ ] **Step 3: Commit.**

```bash
git add scripts/finalize_video.py
git commit -m "finalize_video: add _build_xfade_filter pure function"
```

---

## Task 2: Config validation (pure function)

Reject negative, NaN, and out-of-cap values before any ffmpeg invocation so users get a clean error.

**Files:**
- Modify: `scripts/finalize_video.py`

- [ ] **Step 1: Add the validator below `_build_xfade_filter` in `scripts/finalize_video.py`.**

```python
def _validate_crossfade_seconds(value) -> float:
    """Normalize and validate features.crossfade_seconds. Returns the float.

    Allowed: any non-negative number up to a hard cap of 2.0s. 0 = hard cuts
    (concat demuxer fast path). Negative, non-numeric, or > 2.0 → exit with
    a clear error.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        sys.exit(f"features.crossfade_seconds must be a number, got {value!r}")
    v = float(value)
    if v != v:  # NaN
        sys.exit("features.crossfade_seconds must be a number, got NaN")
    if v < 0:
        sys.exit(f"features.crossfade_seconds must be >= 0, got {v}")
    if v > 2.0:
        sys.exit(
            f"features.crossfade_seconds capped at 2.0s, got {v}. "
            "Longer dissolves eat too much intro/outro content."
        )
    return v
```

- [ ] **Step 2: Verify via ad-hoc run.**

```bash
uv run --with pyyaml python - <<'PY'
import sys
sys.path.insert(0, "scripts")
from finalize_video import _validate_crossfade_seconds

# Happy cases.
for v in (0, 0.0, 0.5, 1.0, 2.0):
    out = _validate_crossfade_seconds(v)
    print(f"OK {v!r} -> {out}")

# Error cases — each should sys.exit, so use subprocess.
import subprocess
for v in ("-0.1", "2.1", "True", "'foo'", "float('nan')"):
    r = subprocess.run(
        ["python", "-c",
         f"import sys; sys.path.insert(0,'scripts'); "
         f"from finalize_video import _validate_crossfade_seconds; "
         f"_validate_crossfade_seconds({v})"],
        capture_output=True, text=True,
    )
    print(f"OK rejected {v}: exit {r.returncode}, msg: {r.stderr.strip() or r.stdout.strip()}")
PY
```

Expected: happy cases print without exit; each error case shows a non-zero exit and a relevant `features.crossfade_seconds ...` message.

- [ ] **Step 3: Commit.**

```bash
git add scripts/finalize_video.py
git commit -m "finalize_video: add _validate_crossfade_seconds"
```

---

## Task 3: Split `concat_segments` into copy and xfade branches

Rename the current `concat_segments` body to `_concat_copy` and add `_concat_xfade`. The public `concat_segments` becomes a thin dispatcher.

**Files:**
- Modify: `scripts/finalize_video.py:90-106`

- [ ] **Step 1: Replace the existing `concat_segments` function in `scripts/finalize_video.py` with this three-function block:**

Find the existing function (around line 90, currently named `concat_segments`):

```python
def concat_segments(segments: list[Path], output_path: Path, tmp_dir: Path) -> None:
    """ffmpeg concat demuxer with -c copy. Requires matching codec/fps/sr.

    make_intro_outro and brand_video both produce h264 + AAC 24kHz mono +
    same resolution + 25fps, so -c copy works.
    """
    list_file = tmp_dir / "concat_list.txt"
    list_file.write_text("\n".join(f"file '{p}'" for p in segments) + "\n")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path),
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
```

Replace it with:

```python
def concat_segments(segments: list[Path], output_path: Path, tmp_dir: Path,
                    crossfade_seconds: float) -> None:
    """Concatenate segments into output_path.

    If crossfade_seconds == 0, uses ffmpeg's concat demuxer with -c copy
    (instant, no re-encode). If > 0, uses an xfade + acrossfade filter graph
    (re-encodes, ~30-60s for a 5-minute video, but produces soft seams).
    """
    if crossfade_seconds == 0:
        _concat_copy(segments, output_path, tmp_dir)
    else:
        _concat_xfade(segments, output_path, crossfade_seconds)


def _concat_copy(segments: list[Path], output_path: Path, tmp_dir: Path) -> None:
    """ffmpeg concat demuxer with -c copy. Requires matching codec/fps/sr.

    make_intro_outro and brand_video both produce h264 + AAC 24kHz mono +
    same resolution + 25fps, so -c copy works.
    """
    list_file = tmp_dir / "concat_list.txt"
    list_file.write_text("\n".join(f"file '{p}'" for p in segments) + "\n")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path),
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def _concat_xfade(segments: list[Path], output_path: Path,
                  crossfade_seconds: float) -> None:
    """Build a single ffmpeg -filter_complex call that chains xfade + acrossfade.

    Probes each segment's duration via ffprobe, then constructs the filter
    graph via `_build_xfade_filter`. Re-encodes with the same profile as
    brand_video.py.
    """
    durations = [video_duration_seconds(p) for p in segments]
    filter_graph = _build_xfade_filter(durations, crossfade_seconds)
    cmd = ["ffmpeg", "-y"]
    for seg in segments:
        cmd.extend(["-i", str(seg)])
    cmd.extend([
        "-filter_complex", filter_graph,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ])
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
```

- [ ] **Step 2: Update the lone call site in `main()` to pass the new argument.**

Find this line in `main()` (around line 186):

```python
            concat_segments(segments, output_path, tmp_dir)
```

Change to:

```python
            concat_segments(segments, output_path, tmp_dir, crossfade_seconds)
```

(`crossfade_seconds` is wired in Task 4; the variable doesn't exist yet at this point, so the next step compiles but fails to run until Task 4 is in.)

- [ ] **Step 3: Stage but don't commit yet — finish Task 4 first to keep the tree runnable.**

---

## Task 4: Wire `crossfade_seconds` from demo_config into `main()`

**Files:**
- Modify: `scripts/finalize_video.py` (in `main()`, after the captions_mode validation)

- [ ] **Step 1: Add the validation + default into `main()`.**

Find this block in `main()` (around line 131-139):

```python
    captions_on = bool(captions_cfg.get("enabled", False))
    captions_mode = captions_cfg.get("mode", "burned")
    # Validate mode early so typos (e.g. "burn", "sidecar") don't silently
    # drop captions despite captions.enabled: true.
    if captions_on and captions_mode not in ("burned", "srt-sidecar"):
        sys.exit(
            f"features.captions.mode must be 'burned' or 'srt-sidecar', "
            f"got {captions_mode!r}"
        )
```

Add immediately after the captions_mode validation:

```python
    # crossfade_seconds defaults to 0.5 (polish by default). Set to 0 to
    # opt out and get the original -c copy concat fast path.
    crossfade_seconds = _validate_crossfade_seconds(
        features.get("crossfade_seconds", 0.5)
    )
```

- [ ] **Step 2: Verify the end-to-end import + arg parsing still works.**

```bash
uv run scripts/finalize_video.py --help
```

Expected: usage prints, no traceback.

- [ ] **Step 3: Commit Tasks 3 + 4 together.**

```bash
git add scripts/finalize_video.py
git commit -m "finalize_video: branch concat on crossfade_seconds (xfade + acrossfade)"
```

---

## Task 5: Update templates, schema doc, gotchas, CLAUDE.md

Five small doc/config edits. Group them in one commit.

**Files:**
- Modify: `templates/demo_config.example.yaml`
- Modify: `examples/halyard-spme/demo_config.yaml`
- Modify: `docs/SCHEMAS.md`
- Modify: `docs/GOTCHAS.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: `templates/demo_config.example.yaml`** — add the new line under the `features` block. Find:

```yaml
  captions:
    enabled: false               # Phase B
    mode: "burned"               # burned | srt-sidecar
    # srt-sidecar mode writes <output>.mp4.srt alongside the video
  brand_overlay: true            # badge + waveform
```

Change to:

```yaml
  captions:
    enabled: false               # Phase B
    mode: "burned"               # burned | srt-sidecar
    # srt-sidecar mode writes <output>.mp4.srt alongside the video
  crossfade_seconds: 0.5         # 0 = hard cuts (fast `-c copy`); >0 = xfade+acrossfade at intro/main/outro seams. Capped at 2.0.
  brand_overlay: true            # badge + waveform
```

- [ ] **Step 2: `examples/halyard-spme/demo_config.yaml`** — same addition.

Find the `features` block (look for `brand_overlay: true`) and add `crossfade_seconds: 0.5` on the line above it. Final shape should look like:

```yaml
features:
  intro_slide: true
  outro_slide: true
  captions:
    enabled: true
    mode: "burned"
  crossfade_seconds: 0.5
  brand_overlay: true
```

- [ ] **Step 3: `docs/SCHEMAS.md`** — document the new field. Find the `features:` block in the `demo_config.yaml` section and add a row/note documenting `crossfade_seconds`. If SCHEMAS.md uses prose, add a paragraph; if it uses a table, add a table row. Either way, the content is:

> `crossfade_seconds` (number, default `0.5`, range `0`–`2.0`): controls the duration of the audio + video cross-dissolve at the intro→main and main→outro seams. `0` disables the dissolve and uses the faster `-c copy` concat path (no re-encode). Values up to `2.0` are accepted; longer dissolves are refused because they eat too much intro/outro content. The dissolve uses ffmpeg's `xfade=transition=fade` (video) and `acrossfade=c1=tri:c2=tri` (audio). Crossfading shortens the final video duration by `(N-1) * crossfade_seconds` seconds.

- [ ] **Step 4: `docs/GOTCHAS.md`** — add a new numbered entry following the existing format. Add after the last entry (currently #22):

```markdown
## 23. xfade crossfade requires headroom inside each segment

**Symptom:** Configuring `features.crossfade_seconds: 4.0` against a 4-second intro produces a black or garbled output.

**Cause:** ffmpeg's `xfade` filter requires the crossfade duration to be strictly less than each adjacent segment's duration. When the crossfade equals or exceeds the shorter segment, there's no clean frame to dissolve from.

**Workaround:** `scripts/finalize_video.py` probes each segment's duration via `ffprobe` and refuses to run if `crossfade_seconds >= min(durations)`. The error message names the offending segment duration. Also: crossfading shortens the final video by `(N-1) * crossfade_seconds`, so a 0.5s dissolve across 3 segments removes 1 second from the total.
```

- [ ] **Step 5: `CLAUDE.md`** — add a preserve-list entry. Find the existing preserve-list section (it has bullets starting with `**Auto-unset NODE_OPTIONS**`, `**TTS size-anomaly retry**`, etc.) and add a new bullet at the end of that list:

```markdown
- **`finalize_video.py`'s concat is branch-dependent on `features.crossfade_seconds`.** When `0`, uses the concat demuxer with `-c copy` (instant, no re-encode). When `> 0`, uses an `xfade` + `acrossfade` filter graph (re-encodes the whole concat, ~30-60s for a 5-minute video, but produces soft seams). Don't "optimize" by always taking the copy path — you lose the seam polish. If you change `make_intro_outro.py`'s or `brand_video.py`'s codec profile, the copy path may also start failing; audit both.
```

- [ ] **Step 6: Commit all five.**

```bash
git add templates/demo_config.example.yaml examples/halyard-spme/demo_config.yaml docs/SCHEMAS.md docs/GOTCHAS.md CLAUDE.md
git commit -m "Document features.crossfade_seconds across templates and docs"
```

---

## Task 6: E2E test against Halyard with default crossfade

Run finalize against the existing Phase B working-dir using the updated `examples/halyard-spme/demo_config.yaml` and verify the output.

**Files:** none changed. Pure verification.

- [ ] **Step 1: Set up a fresh working dir from the updated example.**

```bash
WD=/Users/achintthomas/work/scribble/misc/demo-videos/halyard-crossfade-test
PHASE_B_WD=/Users/achintthomas/work/scribble/misc/demo-videos/halyard-spme-phaseb-test

mkdir -p "$WD/_assets" "$WD/_intermediate" "$WD/_voiceover"
cp examples/halyard-spme/storyboard.yaml "$WD/"
cp examples/halyard-spme/branding.yaml "$WD/"
cp examples/halyard-spme/demo_config.yaml "$WD/"     # has crossfade_seconds: 0.5
cp examples/halyard-spme/_assets/carver_wordmark.png "$WD/_assets/"
cp -r "$PHASE_B_WD/_intermediate/intro.mp4"  "$WD/_intermediate/"
cp -r "$PHASE_B_WD/_intermediate/outro.mp4"  "$WD/_intermediate/"
cp -r "$PHASE_B_WD/_intermediate/branded.mp4" "$WD/_intermediate/" 2>/dev/null \
  || cp -r "$PHASE_B_WD/halyard-demo-phaseb.mp4"  "$WD/_intermediate/branded.mp4"
cp "$PHASE_B_WD/_voiceover/captions.srt" "$WD/_voiceover/"
```

(If `branded.mp4` doesn't exist in the Phase B working dir but `halyard-demo-phaseb.mp4` does, the fallback copies the finalized video as the "input"; for this test it doesn't matter — we're testing finalize itself.)

- [ ] **Step 2: Run finalize.**

```bash
uv run scripts/finalize_video.py \
  --working-dir "$WD" \
  --input "$WD/_intermediate/branded.mp4" \
  --output "$WD/halyard-demo-crossfade.mp4"
```

Expected: ffmpeg runs once (caption burn-in into temp) then once more (`-filter_complex` xfade+acrossfade). Final line should be `OK Finalized: ... (~30 MB, ~316.6s)`.

- [ ] **Step 3: Probe the output duration.**

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \
  "$WD/halyard-demo-crossfade.mp4"
```

Expected: a number around `316.6` (Phase B hard-cut was 317.6; crossfade saves 1.0s = 2 seams × 0.5s).

- [ ] **Step 4: Extract a frame mid-dissolve to verify visually.**

The first dissolve runs from t = 3.5s to t = 4.0s. Extract at t = 3.75s:

```bash
ffmpeg -y -ss 3.75 -i "$WD/halyard-demo-crossfade.mp4" \
  -vframes 1 "$WD/_verify_xfade_intro.jpg" 2>/dev/null
```

Read the JPG (`Read` tool). The frame should show **both** the intro slide content (Carver wordmark + brand text) AND the Halyard homepage's first frame partially layered together — clearly a dissolve, not a hard cut.

- [ ] **Step 5: Extract a frame mid-dissolve at the outro seam.**

The outro dissolve runs in the last 0.5s of the middle. Middle duration is ~308.6s; in the final timeline the second xfade begins at `3.5 + 308.6 - 0.5 = 311.6s` and ends at `312.1s`. Extract at `311.85`:

```bash
ffmpeg -y -ss 311.85 -i "$WD/halyard-demo-crossfade.mp4" \
  -vframes 1 "$WD/_verify_xfade_outro.jpg" 2>/dev/null
```

Read the JPG. Should show demo content + outro slide layered.

- [ ] **Step 6: Commit the test fixture only if you added anything to the repo (you shouldn't have — the test working-dir is outside the repo). Skip if no repo changes.**

---

## Task 7: E2E test the opt-out path and invalid values

**Files:** none changed. Pure verification.

- [ ] **Step 1: Test opt-out (`crossfade_seconds: 0`).**

Edit `"$WD/demo_config.yaml"` (the working-dir copy from Task 6, NOT the repo example) to set `crossfade_seconds: 0`. Then:

```bash
uv run scripts/finalize_video.py \
  --working-dir "$WD" \
  --input "$WD/_intermediate/branded.mp4" \
  --output "$WD/halyard-demo-hardcut.mp4"
```

Probe duration:

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \
  "$WD/halyard-demo-hardcut.mp4"
```

Expected: ~317.6s (matches Phase B hard-cut output). ffmpeg log should show a single `-c copy` invocation, no `-filter_complex`.

- [ ] **Step 2: Test invalid value rejection.**

```bash
# Edit working-dir demo_config.yaml to crossfade_seconds: -0.5
uv run scripts/finalize_video.py --working-dir "$WD" \
  --input "$WD/_intermediate/branded.mp4" \
  --output /tmp/_should_not_be_created.mp4
```

Expected exit code 1, stderr contains `features.crossfade_seconds must be >= 0`.

Repeat for `crossfade_seconds: 3.0`:

Expected exit code 1, stderr contains `features.crossfade_seconds capped at 2.0s`.

Repeat for `crossfade_seconds: "fast"` (string):

Expected exit code 1, stderr contains `features.crossfade_seconds must be a number`.

- [ ] **Step 3: Test the segment-too-short runtime check.**

Generate a synthetic 0.3-second intro and run finalize with `crossfade_seconds: 0.5`:

```bash
ffmpeg -y -f lavfi -i color=c=red:s=1440x900:d=0.3 \
  -f lavfi -i anullsrc=channel_layout=mono:sample_rate=24000 \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest \
  -t 0.3 "$WD/_intermediate/intro.mp4"

# crossfade_seconds back to 0.5 in demo_config.yaml
uv run scripts/finalize_video.py --working-dir "$WD" \
  --input "$WD/_intermediate/branded.mp4" \
  --output /tmp/_should_not_be_created.mp4
```

Expected exit code 1, stderr contains `crossfade_seconds=0.5 must be less than the shortest segment duration (0.30s)`.

Restore the original intro before moving on:

```bash
cp "$PHASE_B_WD/_intermediate/intro.mp4" "$WD/_intermediate/intro.mp4"
```

- [ ] **Step 4: No commit. These are runtime tests; no repo changes.**

---

## Final verification

After Task 7, run a quick smoke against the canonical example to confirm nothing regressed and the default behavior is the crossfade:

```bash
# From the repo root, with the dist server running on :8080 if needed:
WD=/Users/achintthomas/work/scribble/misc/demo-videos/halyard-crossfade-final
mkdir -p "$WD/_assets"
cp examples/halyard-spme/*.yaml "$WD/"
cp examples/halyard-spme/_assets/carver_wordmark.png "$WD/_assets/"
cp /Users/achintthomas/work/scribble/misc/demo-videos/.env "$WD/.env"
cp -r /Users/achintthomas/work/scribble/misc/demo-videos/halyard-spme-test/_voiceover "$WD/"

uv run scripts/make_overlay.py     --working-dir "$WD"
uv run scripts/render_voiceover.py --working-dir "$WD"
uv run scripts/record_demo.py      --working-dir "$WD"
uv run scripts/mux_demo.py         --working-dir "$WD"
uv run scripts/speed_video.py --input "$WD/_intermediate/muxed.mp4" --output "$WD/_intermediate/speed.mp4" --multiplier 1.2
uv run scripts/brand_video.py --working-dir "$WD" --input "$WD/_intermediate/speed.mp4" --output "$WD/_intermediate/branded.mp4"
uv run scripts/make_intro_outro.py --working-dir "$WD"
uv run scripts/make_captions.py    --working-dir "$WD"
uv run scripts/finalize_video.py --working-dir "$WD" --input "$WD/_intermediate/branded.mp4" --output "$WD/halyard-demo.mp4"

ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$WD/halyard-demo.mp4"
```

Expected: clean run end-to-end. Final mp4 duration ≈ 316.6s.

This run is optional — if Task 6's intermediate-mp4 reuse covered the finalize path adequately, skip the full re-record.

---

## Acceptance

- `features.crossfade_seconds: 0.5` (default) produces a Halyard demo with mid-dissolve frames at both seams (confirmed via frame extraction in Task 6 Steps 4-5).
- `features.crossfade_seconds: 0` reproduces the existing Phase B hard-cut output duration ~317.6s (Task 7 Step 1).
- Invalid values (`-0.5`, `3.0`, non-numeric, longer than shortest segment) all exit with clear messages and don't produce an output file (Task 7 Steps 2-3).
- No regression in the existing Phase A or B pipelines when `crossfade_seconds` is absent or set to `0`.
