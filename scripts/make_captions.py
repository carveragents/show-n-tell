"""Generate SRT captions aligned with per-beat narration.

For each beat, derives the audible narration window from `timings.json` (the
TTS audio plays inside the `(action_ms + pre_ms)` to
`(action_ms + pre_ms + tts_ms)` slice of the beat's total wall-clock segment),
then divides by `output.speed_multiplier` to map to the final-video timeline.

CLI:
    uv run scripts/make_captions.py --working-dir <path>

Reads:
    <working_dir>/storyboard.yaml      (narration text per beat)
    <working_dir>/_voiceover/timings.json
    <working_dir>/demo_config.yaml     (output.speed_multiplier)

Writes:
    <working_dir>/_voiceover/captions.srt
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import load_yaml, resolve_working_dir


def format_srt_timestamp(ms: int) -> str:
    """Convert milliseconds to SRT timestamp `HH:MM:SS,mmm`."""
    if ms < 0:
        ms = 0
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def build_srt_entries(timings: dict, narrations: dict, speed: float) -> list[str]:
    """Return one SRT entry string per beat, in storyboard order.

    Skips timings entries whose beat id no longer exists in storyboard.
    """
    entries = []
    cumulative_ms = 0
    index = 0
    for t in timings["beats"]:
        beat_id = t["id"]
        narration = narrations.get(beat_id)
        if narration is None:
            # Beat was removed from storyboard since timings were recorded.
            # Still advance the timeline so subsequent beats stay aligned.
            cumulative_ms += t["total_ms"]
            continue

        raw_start_ms = cumulative_ms + t["action_ms"] + t["pre_ms"]
        raw_end_ms = raw_start_ms + t["tts_ms"]
        start_ms = round(raw_start_ms / speed)
        end_ms = round(raw_end_ms / speed)

        index += 1
        entries.append(
            f"{index}\n"
            f"{format_srt_timestamp(start_ms)} --> {format_srt_timestamp(end_ms)}\n"
            f"{narration}\n"
        )
        cumulative_ms += t["total_ms"]

    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--working-dir", required=True)
    args = ap.parse_args()

    wd = resolve_working_dir(args.working_dir)
    storyboard = load_yaml(wd / "storyboard.yaml")
    demo_config = load_yaml(wd / "demo_config.yaml")
    timings_path = wd / "_voiceover" / "timings.json"
    if not timings_path.exists():
        sys.exit(f"Missing {timings_path}. Run record_demo.py first.")
    timings = json.loads(timings_path.read_text())

    speed = float(demo_config.get("output", {}).get("speed_multiplier", 1.0))
    if speed <= 0:
        sys.exit(f"Invalid speed_multiplier: {speed}")

    narrations = {
        b["id"]: b["narration"].strip()
        for b in storyboard.get("beats", [])
        if b.get("narration") is not None
    }

    timing_ids = {b["id"] for b in timings["beats"]}
    missing = [bid for bid in narrations if bid not in timing_ids]
    if missing:
        sys.exit(
            "Storyboard has beats with no entry in timings.json: "
            f"{', '.join(missing)}. timings.json is stale — re-run record_demo.py."
        )

    entries = build_srt_entries(timings, narrations, speed)
    if not entries:
        sys.exit("No SRT entries produced — storyboard and timings don't share any beat ids.")

    out_path = wd / "_voiceover" / "captions.srt"
    out_path.write_text("\n".join(entries))

    last_end = entries[-1].splitlines()[1].split(" --> ")[1]
    print(f"  {len(entries)} entries · speed_multiplier={speed} · last ends at {last_end}")
    print(f"OK Captions: {out_path}")


if __name__ == "__main__":
    main()
