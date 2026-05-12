"""Render intro and outro slide videos for Phase B demos.

Each slide is a still PIL render (dark radial gradient bg matching the badge
palette, logo recolored to cream, brand/CTA/social text) encoded by ffmpeg
to an mp4 with a silent AAC track, with a 0.8s fade-in and 0.8s fade-out.

CLI:
    uv run scripts/make_intro_outro.py --working-dir <path>

Reads:
    <working_dir>/branding.yaml     (brand.*, colors.*, logo.path)
    <working_dir>/demo_config.yaml  (features.intro_slide / outro_slide,
                                     recording.viewport, recording.framerate)

Writes:
    <working_dir>/_intermediate/intro.mp4
    <working_dir>/_intermediate/outro.mp4
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "pillow"]
# ///
import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from _lib import load_yaml, resolve_working_dir, ensure_dir, hex_to_rgb, load_logo


INTRO_DURATION = 4.0
OUTRO_DURATION = 5.0
FADE_DURATION = 0.8

# Audio params matched to what mux_demo/brand_video produce (AAC 24kHz mono),
# so finalize_video.py's concat doesn't need to re-encode audio across the seams.
AUDIO_SAMPLE_RATE = 24000
AUDIO_CHANNEL_LAYOUT = "mono"

FONT_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    # Windows
    "C:/Windows/Fonts/arial.ttf",
]


def load_font(size: int) -> ImageFont.ImageFont:
    """Try a few cross-platform sans-serif paths; error out if none found.

    PIL's load_default() returns a ~10px bitmap font that ignores the requested
    size, which would make slide text near-invisible. Better to fail clearly.
    """
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    sys.exit(
        "No usable TrueType font found. Install one of: "
        "Helvetica/Arial (macOS/Windows) or DejaVu/Liberation/Noto Sans (Linux)."
    )


def draw_centered_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont,
                       canvas_w: int, y: int, fill: tuple[int, int, int]) -> int:
    """Draw `text` horizontally centered at vertical position `y` (top of text).
    Returns the y of the bottom of the drawn text.
    """
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    # textbbox can return non-zero top — compensate so `y` is the visible top.
    draw.text(((canvas_w - text_w) // 2 - bbox[0], y - bbox[1]), text, font=font, fill=fill)
    return y + text_h


def render_background(width: int, height: int, ink: tuple, ink_deep: tuple) -> Image.Image:
    """Full-canvas radial gradient: ink_deep at center, ink at edges.

    Matches the badge palette. Implemented via concentric ellipses on a
    downscaled supersampled canvas, then blurred for smoothness.
    """
    img = Image.new("RGB", (width, height), ink)
    draw = ImageDraw.Draw(img)
    cx, cy = width // 2, height // 2
    # Radius reaches the corners so the gradient covers the canvas.
    r_max = int((cx ** 2 + cy ** 2) ** 0.5)
    # Step in pixels; gives ~r_max steps which is plenty smooth before blur.
    for r in range(r_max, 0, -2):
        t = 1 - (r / r_max)
        col = (
            int(ink[0] * (1 - t) + ink_deep[0] * t),
            int(ink[1] * (1 - t) + ink_deep[1] * t),
            int(ink[2] * (1 - t) + ink_deep[2] * t),
        )
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    return img.filter(ImageFilter.GaussianBlur(radius=3))


def paste_logo(canvas: Image.Image, logo: Image.Image, width_ratio: float,
               max_height_ratio: float, center_x: int, top_y: int) -> int:
    """Scale logo to fit within `width_ratio * canvas.width` AND
    `max_height_ratio * canvas.height`, preserving aspect ratio, then paste
    centered horizontally. The height cap prevents tall/square avatar-style
    logos from overflowing into the brand-name area below.

    Returns the y of the bottom edge of the pasted logo.
    """
    target_w = int(canvas.width * width_ratio)
    max_h = int(canvas.height * max_height_ratio)
    scale = min(target_w / logo.size[0], max_h / logo.size[1])
    sized = logo.resize(
        (int(logo.size[0] * scale), int(logo.size[1] * scale)),
        Image.LANCZOS,
    )
    lx = center_x - sized.size[0] // 2
    canvas.paste(sized, (lx, top_y), sized)
    return top_y + sized.size[1]


def _palette(branding: dict) -> dict:
    c = branding.get("colors", {}) or {}
    return {
        "ink": hex_to_rgb(c.get("ink", "#101828")),
        "ink_deep": hex_to_rgb(c.get("ink_deep", "#0c1322")),
        "accent": hex_to_rgb(c.get("accent", "#bae424")),
        "cream": hex_to_rgb(c.get("cream", "#fbf7f3")),
    }


def render_intro_slide(width: int, height: int, branding: dict, logo: Image.Image) -> Image.Image:
    p = _palette(branding)
    brand = branding.get("brand", {}) or {}
    canvas = render_background(width, height, p["ink"], p["ink_deep"]).convert("RGBA")
    logo_bottom = paste_logo(canvas, logo, 0.30, 0.28, width // 2, int(height * 0.28))

    draw = ImageDraw.Draw(canvas)
    y = logo_bottom + int(height * 0.06)
    if brand.get("name"):
        y = draw_centered_text(draw, brand["name"], load_font(max(48, int(height * 0.075))),
                               width, y, p["cream"])
        y += int(height * 0.025)
    if brand.get("tagline"):
        draw_centered_text(draw, brand["tagline"], load_font(max(24, int(height * 0.035))),
                           width, y, p["accent"])
    return canvas.convert("RGB")


def render_outro_slide(width: int, height: int, branding: dict, logo: Image.Image) -> Image.Image:
    p = _palette(branding)
    brand = branding.get("brand", {}) or {}
    cta = brand.get("cta", {}) or {}
    social = brand.get("social", {}) or {}

    canvas = render_background(width, height, p["ink"], p["ink_deep"]).convert("RGBA")
    logo_bottom = paste_logo(canvas, logo, 0.25, 0.22, width // 2, int(height * 0.22))

    draw = ImageDraw.Draw(canvas)
    y = logo_bottom + int(height * 0.07)
    if cta.get("text"):
        y = draw_centered_text(draw, cta["text"], load_font(max(36, int(height * 0.058))),
                               width, y, p["accent"])
        y += int(height * 0.03)
    if cta.get("url"):
        draw_centered_text(draw, cta["url"], load_font(max(24, int(height * 0.038))),
                           width, y, p["cream"])

    handles = [str(v) for v in social.values() if v]
    if handles:
        draw_centered_text(draw, "   ·   ".join(handles),
                           load_font(max(18, int(height * 0.026))),
                           width, int(height * 0.88), p["cream"])
    return canvas.convert("RGB")


def encode_slide(png_path: Path, out_path: Path, duration: float,
                 width: int, height: int, framerate: int) -> None:
    """Encode a still PNG to mp4 with fade in/out + silent AAC audio."""
    fade_out_start = max(0.0, duration - FADE_DURATION)
    vf = (
        f"fade=t=in:st=0:d={FADE_DURATION},"
        f"fade=t=out:st={fade_out_start}:d={FADE_DURATION},"
        f"scale={width}:{height}:flags=lanczos,"
        f"format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", f"{duration}", "-framerate", str(framerate),
        "-i", str(png_path),
        "-f", "lavfi", "-t", f"{duration}",
        "-i", f"anullsrc=channel_layout={AUDIO_CHANNEL_LAYOUT}:sample_rate={AUDIO_SAMPLE_RATE}",
        "-vf", vf,
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
    branding = load_yaml(wd / "branding.yaml")
    demo_config = load_yaml(wd / "demo_config.yaml")

    features = demo_config.get("features", {}) or {}
    want_intro = bool(features.get("intro_slide", False))
    want_outro = bool(features.get("outro_slide", False))
    if not want_intro and not want_outro:
        print("Nothing to do (both intro_slide and outro_slide flags are off)")
        return

    rec = demo_config.get("recording", {}) or {}
    viewport = rec.get("viewport", {}) or {}
    width = int(viewport.get("width", 1440))
    height = int(viewport.get("height", 900))
    framerate = int(rec.get("framerate", 25))

    logo_rel = (branding.get("logo", {}) or {}).get("path")
    if not logo_rel:
        sys.exit("branding.yaml: logo.path is required")
    logo_path = (wd / logo_rel).resolve()
    if not logo_path.exists():
        sys.exit(f"Logo not found at {logo_path}")

    cream = hex_to_rgb((branding.get("colors", {}) or {}).get("cream", "#fbf7f3"))
    logo = load_logo(logo_path, cream)

    out_dir = ensure_dir(wd / "_intermediate")
    tmp_dir = ensure_dir(wd / "_intermediate" / "_slide_tmp")

    if want_intro:
        png = tmp_dir / "intro.png"
        slide = render_intro_slide(width, height, branding, logo)
        slide.save(png)
        encode_slide(png, out_dir / "intro.mp4", INTRO_DURATION, width, height, framerate)
        print(f"✓ Intro: {out_dir / 'intro.mp4'}")

    if want_outro:
        png = tmp_dir / "outro.png"
        slide = render_outro_slide(width, height, branding, logo)
        slide.save(png)
        encode_slide(png, out_dir / "outro.mp4", OUTRO_DURATION, width, height, framerate)
        print(f"✓ Outro: {out_dir / 'outro.mp4'}")


if __name__ == "__main__":
    main()
