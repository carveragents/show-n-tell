"""Mux the recorded webm with per-beat TTS into a synced mp4.

For each beat, builds a synced audio segment:
    silence(action_ms + pre_ms) + tts_wav + silence(post_ms)

These segments concatenate to the same total duration the recorder produced,
so audio and video stay in lock-step.

CLI:
    uv run scripts/mux_demo.py --working-dir <path>

Reads:
    <working_dir>/_intermediate/reference.webm
    <working_dir>/_voiceover/<beat_id>.wav (one per beat)
    <working_dir>/_voiceover/manifest.json
    <working_dir>/_voiceover/timings.json

Writes:
    <working_dir>/_voiceover/full.wav
    <working_dir>/_intermediate/muxed.mp4
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "pydub", "audioop-lts; python_version >= '3.13'"]
# ///
import argparse
import json
import subprocess
import sys
from pathlib import Path

from pydub import AudioSegment

sys.path.insert(0, str(Path(__file__).parent))
from _lib import resolve_working_dir


def build_audio_track(voice_dir: Path) -> AudioSegment:
    manifest = json.loads((voice_dir / "manifest.json").read_text())
    timings = json.loads((voice_dir / "timings.json").read_text())
    timing_by_id = {b["id"]: b for b in timings["beats"]}

    full = AudioSegment.silent(duration=0)
    target_fr = None

    for entry in manifest["beats"]:
        beat_id = entry["id"]
        t = timing_by_id.get(beat_id)
        if t is None:
            sys.exit(f"No recording timing for beat {beat_id}. "
                     "Re-run record_demo.py.")

        wav_path = voice_dir / f"{beat_id}.wav"
        tts = AudioSegment.from_wav(str(wav_path))
        if target_fr is None:
            target_fr = tts.frame_rate
        elif tts.frame_rate != target_fr:
            tts = tts.set_frame_rate(target_fr)

        pre = AudioSegment.silent(
            duration=t["action_ms"] + t["pre_ms"], frame_rate=target_fr,
        )
        post = AudioSegment.silent(
            duration=t["post_ms"], frame_rate=target_fr,
        )
        full += pre + tts + post

    return full


def mux_av(audio_path: Path, video_path: Path, out_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--working-dir", required=True)
    args = ap.parse_args()

    wd = resolve_working_dir(args.working_dir)
    voice_dir = wd / "_voiceover"
    inter_dir = wd / "_intermediate"
    video_in = inter_dir / "reference.webm"
    audio_out = voice_dir / "full.wav"
    video_out = inter_dir / "muxed.mp4"

    if not video_in.exists():
        sys.exit(f"Missing {video_in}. Run record_demo.py first.")
    if not (voice_dir / "timings.json").exists():
        sys.exit("Missing timings.json. Run record_demo.py first.")

    print("Building synced audio track…")
    audio = build_audio_track(voice_dir)
    audio.export(str(audio_out), format="wav")
    print(f"✓ Audio: {audio_out} ({len(audio) / 1000:.1f}s)")

    print("\nMuxing audio + video → mp4…")
    mux_av(audio_out, video_in, video_out)
    print(f"\n✓ Muxed: {video_out} "
          f"({video_out.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    main()
