"""Overlay the brand badge + audio-reactive waveform onto a video.

Phase A scope: bottom-left badge + waveform only. Intro/outro/captions are
Phase B and are not handled here.

CLI:
    uv run scripts/brand_video.py --working-dir <path> --input speed.mp4 --output demo.mp4

Reads:
    <working_dir>/branding.yaml                       (colors.accent, optional overlay block)
    <working_dir>/_assets/overlay_frames/frame_%04d.png

Writes:
    --output (final branded mp4)
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import load_yaml, resolve_working_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--working-dir", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    wd = resolve_working_dir(args.working_dir)
    branding = load_yaml(wd / "branding.yaml")

    overlay = branding.get("overlay", {}) or {}
    badge_cfg = overlay.get("badge", {}) or {}
    wave_cfg = overlay.get("waveform", {}) or {}

    badge_visible = int(badge_cfg.get("size", 120))
    badge_canvas = badge_visible + 60  # matches make_overlay padding
    badge_left = int(badge_cfg.get("left_margin", 30))
    bottom_margin = int(badge_cfg.get("bottom_margin", 36))

    wave_w = int(wave_cfg.get("width", 200))
    wave_h = int(wave_cfg.get("height", 36))
    gap = int(wave_cfg.get("gap", 6))
    wave_mode = wave_cfg.get("mode", "p2p")
    wave_scale = wave_cfg.get("scale", "sqrt")
    accent_hex = branding.get("colors", {}).get("accent", "#bae424").lstrip("#")

    # Layout calculation (from bottom-up):
    #   waveform sits `bottom_margin` from bottom
    #   badge sits above waveform with `gap` between
    canvas_y_offset = bottom_margin + wave_h + gap + badge_visible + (badge_canvas - badge_visible) // 2
    canvas_x = badge_left - (badge_canvas - badge_visible) // 2
    if canvas_x < 0:
        canvas_x = 0
    canvas_y_expr = f"H-{canvas_y_offset}"

    wave_x = badge_left + (badge_visible - wave_w) // 2
    if wave_x < 10:
        wave_x = 10
    wave_y_expr = f"H-{bottom_margin + wave_h}"

    overlay_frames = wd / "_assets" / "overlay_frames"
    frames_pattern = overlay_frames / "frame_%04d.png"
    if not (overlay_frames / "frame_0000.png").exists():
        sys.exit(f"Missing overlay frames at {overlay_frames}. Run make_overlay.py first.")

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    filter_complex = (
        f"[0:a]aformat=channel_layouts=mono,"
        f"showwaves=s={wave_w}x{wave_h}:mode={wave_mode}:rate=25:scale={wave_scale}:colors=#{accent_hex},"
        f"format=rgba,colorkey=0x000000:0.15:0[wave];"
        f"[0:v][1:v]overlay=x={canvas_x}:y={canvas_y_expr}:shortest=0[v_badge];"
        f"[v_badge][wave]overlay=x={wave_x}:y={wave_y_expr}[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-framerate", "25", "-stream_loop", "-1", "-i", str(frames_pattern),
        "-filter_complex", filter_complex,
        "-map", "[out]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"\n✓ Branded: {output_path} "
          f"({output_path.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    main()
