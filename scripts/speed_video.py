"""Speed up (or slow down) an mp4 while preserving audio pitch.

Uses ffmpeg's atempo + setpts for combined audio+video speed adjustment.
atempo supports 0.5–2.0 in a single filter.

CLI:
    uv run scripts/speed_video.py --input muxed.mp4 --output speed.mp4 --multiplier 1.2

Pass-through: --multiplier 1.0 copies streams without re-encoding (fast).
"""
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def speed_change(input_path: Path, output_path: Path, multiplier: float) -> None:
    if multiplier == 1.0:
        # No-op: just copy
        shutil.copy(input_path, output_path)
        return

    if not (0.5 <= multiplier <= 2.0):
        sys.exit(f"--multiplier must be between 0.5 and 2.0 (got {multiplier}). "
                 "For ranges outside that, chain multiple atempo filters.")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-filter_complex",
        f"[0:v]setpts=PTS/{multiplier}[v];[0:a]atempo={multiplier}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--multiplier", type=float, default=1.2)
    args = ap.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        sys.exit(f"Input not found: {input_path}")

    speed_change(input_path, output_path, args.multiplier)
    print(f"\n✓ Sped: {output_path} "
          f"({output_path.stat().st_size / 1_048_576:.1f} MB, "
          f"multiplier {args.multiplier})")


if __name__ == "__main__":
    main()
