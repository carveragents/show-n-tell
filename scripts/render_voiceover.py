"""Render per-beat TTS via OpenAI gpt-4o-mini-tts.

Diff-aware: only regenerates wavs whose narration changed since the last run.
Size-anomaly retry: if a wav file looks suspiciously small for its character
count, regenerate (OpenAI's streaming response can truncate mid-sentence).

CLI:
    uv run scripts/render_voiceover.py --working-dir <path> [--clean]

Reads:
    <working_dir>/storyboard.yaml   (beats with id + narration)
    <working_dir>/branding.yaml     (voice block: model, voice, instructions)
    <working_dir>/.env              (optional, OPENAI_API_KEY)

Writes:
    <working_dir>/_voiceover/<beat_id>.wav
    <working_dir>/_voiceover/manifest.json

Cost: ~$0.015 per minute of speech. A 5-minute demo ≈ $0.08.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "openai", "python-dotenv"]
# ///
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (
    load_yaml, resolve_working_dir, ensure_dir,
    wav_duration_seconds, load_dotenv_if_present,
)


DEFAULT_INSTRUCTIONS = (
    "Read calmly and clearly, like a confident product walkthrough narrator. "
    "Pace around 140 words per minute. Treat hyphenated initialisms like "
    "A-P-I and K-Y-B as letter-by-letter readings. Do not sound rushed; "
    "leave small natural breaths between sentences."
)


def narration_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def is_suspicious_size(path: Path, chars: int) -> bool:
    """Heuristic: OpenAI wav at 24kHz mono ≈ 2KB/char. Flag if < 50% of expected."""
    if not path.exists():
        return True
    size = path.stat().st_size
    expected = chars * 2000
    return size < expected * 0.5


def generate_one(client, narration: str, voice: str, model: str,
                 instructions: str, out_path: Path) -> None:
    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=narration,
        instructions=instructions,
        response_format="wav",
    ) as response:
        response.stream_to_file(str(out_path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--working-dir", required=True)
    ap.add_argument("--clean", action="store_true",
                    help="Force regenerate every beat, ignore previous manifest")
    args = ap.parse_args()

    wd = resolve_working_dir(args.working_dir)
    load_dotenv_if_present(wd)

    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not set. Put it in <working_dir>/.env or export it.")

    storyboard = load_yaml(wd / "storyboard.yaml")
    branding = load_yaml(wd / "branding.yaml")
    voice_cfg = branding.get("voice", {})
    model = voice_cfg.get("model", "gpt-4o-mini-tts")
    voice = voice_cfg.get("voice", "cedar")
    instructions = voice_cfg.get("instructions", DEFAULT_INSTRUCTIONS)

    beats = storyboard.get("beats", [])
    if not beats:
        sys.exit("storyboard.yaml has no beats")

    out_dir = ensure_dir(wd / "_voiceover")
    manifest_path = out_dir / "manifest.json"
    prev_hashes = {}
    if manifest_path.exists() and not args.clean:
        prev = json.loads(manifest_path.read_text())
        prev_hashes = {b["id"]: b.get("narration_hash") for b in prev.get("beats", [])}

    from openai import OpenAI
    client = OpenAI()

    manifest = {"model": model, "voice": voice, "beats": []}
    regenerated = 0
    reused = 0
    total_chars = 0
    total_seconds = 0.0

    for beat in beats:
        beat_id = beat["id"]
        narration = beat["narration"].strip()
        chars = len(narration)
        total_chars += chars
        h = narration_hash(narration)
        wav_path = out_dir / f"{beat_id}.wav"

        needs_regen = (
            args.clean
            or not wav_path.exists()
            or prev_hashes.get(beat_id) != h
            or is_suspicious_size(wav_path, chars)
        )

        if needs_regen:
            for attempt in range(1, 4):
                generate_one(client, narration, voice, model, instructions, wav_path)
                if not is_suspicious_size(wav_path, chars):
                    break
                print(f"  ! {beat_id}: wav size suspicious (attempt {attempt}), retrying")
            regenerated += 1
            tag = "REGEN"
        else:
            reused += 1
            tag = "reuse"

        duration = wav_duration_seconds(wav_path)
        total_seconds += duration
        manifest["beats"].append({
            "id": beat_id,
            "chars": chars,
            "duration_seconds": round(duration, 3),
            "narration_hash": h,
            "wav_path": str(wav_path.relative_to(wd)),
        })
        print(f"  {tag}  {beat_id:32}  {chars:4}ch  {duration:5.2f}s")

    manifest_path.write_text(json.dumps(manifest, indent=2))

    print()
    print(f"✓ {len(beats)} beats ({regenerated} regen / {reused} reuse) · "
          f"{total_chars} chars · {total_seconds:.1f}s "
          f"({total_seconds / 60:.1f} min)")
    print(f"✓ Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
