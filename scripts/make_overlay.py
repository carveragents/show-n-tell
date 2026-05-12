"""Render the brand badge overlay frames.

Produces a sequence of PNG frames (2-second loop at 25fps) — static gradient
badge + two phase-staggered pulse rings. Looped indefinitely by ffmpeg via
-stream_loop in brand_video.py.

CLI:
    uv run scripts/make_overlay.py --working-dir <path> [--frames 50] [--badge-size 120]

Reads:
    <working_dir>/branding.yaml  (logo.path, colors.*)

Writes:
    <working_dir>/_assets/overlay_frames/frame_NNNN.png
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "pillow"]
# ///
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
from _lib import load_yaml, resolve_working_dir, ensure_dir, hex_to_rgb, load_logo


SS = 4  # supersample factor for smooth anti-aliasing


def draw_static_badge(badge_size: int, canvas: int, logo: Image.Image,
                      ink: tuple, ink_deep: tuple, accent: tuple,
                      logo_width_ratio: float = 0.62) -> Image.Image:
    cs = canvas * SS
    img = Image.new("RGBA", (cs, cs), (0, 0, 0, 0))
    cx = cy = cs // 2
    r_outer = badge_size * SS // 2

    # Outer halo glow
    halo = Image.new("RGBA", (cs, cs), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse(
        [cx - r_outer - 8 * SS, cy - r_outer - 8 * SS,
         cx + r_outer + 8 * SS, cy + r_outer + 8 * SS],
        fill=(*accent, 60),
    )
    halo = halo.filter(ImageFilter.GaussianBlur(7 * SS))
    img = Image.alpha_composite(img, halo)

    # Radial gradient fill (ink → ink_deep)
    draw = ImageDraw.Draw(img)
    for i in range(r_outer, 0, -1):
        t = 1 - (i / r_outer)
        r = int(ink[0] * (1 - t) + ink_deep[0] * t)
        g = int(ink[1] * (1 - t) + ink_deep[1] * t)
        b = int(ink[2] * (1 - t) + ink_deep[2] * t)
        draw.ellipse([cx - i, cy - i, cx + i, cy + i], fill=(r, g, b, 255))

    # Accent ring border
    ring_w = 2 * SS
    draw.ellipse(
        [cx - r_outer + ring_w // 2, cy - r_outer + ring_w // 2,
         cx + r_outer - ring_w // 2, cy + r_outer - ring_w // 2],
        outline=(*accent, 255), width=ring_w,
    )

    # Logo centered
    target_w = int(badge_size * SS * logo_width_ratio)
    scale = target_w / logo.size[0]
    logo_sized = logo.resize(
        (int(logo.size[0] * scale), int(logo.size[1] * scale)),
        Image.LANCZOS,
    )
    lx = cx - logo_sized.size[0] // 2
    ly = cy - logo_sized.size[1] // 2
    img.paste(logo_sized, (lx, ly), logo_sized)
    return img


def draw_pulse_ring(img: Image.Image, phase: float, badge_size: int,
                    accent: tuple) -> Image.Image:
    cs = img.size[0]
    overlay = Image.new("RGBA", (cs, cs), (0, 0, 0, 0))
    cx = cy = cs // 2
    r_base = badge_size * SS // 2

    expansion = phase * 22 * SS
    r = r_base + 4 * SS + expansion
    alpha = int(160 * (1 - phase) ** 1.5)

    if alpha > 4:
        ring_img = Image.new("RGBA", (cs, cs), (0, 0, 0, 0))
        ImageDraw.Draw(ring_img).ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            outline=(*accent, alpha), width=int(3 * SS),
        )
        ring_img = ring_img.filter(ImageFilter.GaussianBlur(1.5 * SS))
        overlay = Image.alpha_composite(overlay, ring_img)

    return Image.alpha_composite(img, overlay)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--working-dir", required=True)
    ap.add_argument("--frames", type=int, default=50)
    ap.add_argument("--badge-size", type=int, default=120)
    args = ap.parse_args()

    wd = resolve_working_dir(args.working_dir)
    branding = load_yaml(wd / "branding.yaml")

    logo_rel = branding.get("logo", {}).get("path")
    if not logo_rel:
        sys.exit("branding.yaml: logo.path is required")
    logo_path = (wd / logo_rel).resolve()
    if not logo_path.exists():
        sys.exit(f"Logo not found at {logo_path}")

    colors = branding.get("colors", {})
    ink = hex_to_rgb(colors.get("ink", "#101828"))
    ink_deep = hex_to_rgb(colors.get("ink_deep", "#0c1322"))
    accent = hex_to_rgb(colors.get("accent", "#bae424"))
    cream = hex_to_rgb(colors.get("cream", "#fbf7f3"))

    badge_size = args.badge_size
    canvas = badge_size + 60  # 30px padding all around for pulse ring + halo

    logo = load_logo(logo_path, cream)

    out_dir = ensure_dir(wd / "_assets" / "overlay_frames")
    print(f"Rendering {args.frames} frames at {canvas}x{canvas} → {out_dir}/")
    static = draw_static_badge(badge_size, canvas, logo, ink, ink_deep, accent)
    for f in range(args.frames):
        phase_a = (f / args.frames + 0.0) % 1.0
        phase_b = (f / args.frames + 0.5) % 1.0
        frame = static.copy()
        frame = draw_pulse_ring(frame, phase_a, badge_size, accent)
        frame = draw_pulse_ring(frame, phase_b, badge_size, accent)
        final = frame.resize((canvas, canvas), Image.LANCZOS)
        final.save(out_dir / f"frame_{f:04d}.png")
    print(f"✓ Wrote {args.frames} frames")


if __name__ == "__main__":
    main()
