"""Shared helpers for demo-video-from-site scripts.

Kept small and dependency-light. Loaded by other scripts via:
    sys.path.insert(0, str(Path(__file__).parent))
    from _lib import ...
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml


def hex_to_rgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    if len(s) != 6:
        raise ValueError(f"Bad hex color: {s!r}")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def is_monochrome_on_transparent(img) -> bool:
    """All non-transparent pixels share the same RGB → safe to recolor.

    `img` is a PIL Image. PIL is imported lazily to keep _lib import-cheap.
    """
    rgba = img.convert("RGBA")
    pixels = list(rgba.getdata())
    seen_rgb = set()
    for r, g, b, a in pixels:
        if a < 8:
            continue
        seen_rgb.add((r, g, b))
        if len(seen_rgb) > 1:
            return False
    return len(seen_rgb) <= 1


def load_logo(logo_path: Path, fill_rgb: tuple[int, int, int]):
    """Load logo; recolor to `fill_rgb` if monochrome-on-transparent."""
    from PIL import Image  # lazy import — PIL not always required
    src = Image.open(logo_path).convert("RGBA")
    if is_monochrome_on_transparent(src):
        recolored = Image.new("RGBA", src.size, (*fill_rgb, 0))
        recolored.putalpha(src.getchannel("A"))
        return recolored
    return src


def load_yaml(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"Missing config file: {path}")
    return yaml.safe_load(path.read_text()) or {}


def load_configs(working_dir: Path) -> tuple[dict, dict, dict]:
    """Load the three per-demo YAML files. Returns (storyboard, branding, demo_config)."""
    storyboard = load_yaml(working_dir / "storyboard.yaml")
    branding = load_yaml(working_dir / "branding.yaml")
    demo_config = load_yaml(working_dir / "demo_config.yaml")
    return storyboard, branding, demo_config


_ENV_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def expand_env(value):
    """Expand `${VAR}` references in strings recursively through dict/list."""
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    return value


_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def interp_template(value, ctx: dict):
    """Substitute `{{ name }}` references using `ctx`."""
    if isinstance(value, str):
        return _TEMPLATE_RE.sub(lambda m: str(ctx.get(m.group(1), m.group(0))), value)
    if isinstance(value, dict):
        return {k: interp_template(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [interp_template(v, ctx) for v in value]
    return value


def wav_duration_seconds(path: Path) -> float:
    """ffprobe-based duration. Python's `wave` module misparses OpenAI's wav header."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def resolve_working_dir(raw: str) -> Path:
    """Expand `~` and resolve to an absolute Path. Caller is responsible for mkdir."""
    return Path(raw).expanduser().resolve()


def resolve_session_path(path: str, working_dir: Path) -> Path:
    """Resolve a session-related path string against the working dir.

    Rules:
      - Absolute paths → returned as-is (resolved).
      - `~`-prefixed → expanded against `$HOME`.
      - Otherwise → joined to `working_dir` and resolved.

    Used by record_demo.py for `session.storage_state`.
    """
    expanded = Path(path).expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (working_dir / expanded).resolve()


def resolve_bg_music_path(
    branding: dict,
    working_dir: Path,
    skill_dir: Path,
) -> Path | None:
    """Resolve the background-music file path from branding.yaml's `audio:` block.

    Returns:
      - None if neither `bg_music_path` nor `bg_music_mood` is set
      - Absolute Path for Mode A (user file) or Mode B (bundled library lookup)

    Raises:
      - ValueError if both modes set, or mood unknown / has empty track list
      - FileNotFoundError if a referenced file does not exist
    """
    audio = (branding.get("audio") or {})
    path_raw = audio.get("bg_music_path")
    mood = audio.get("bg_music_mood")

    if path_raw == "":
        raise ValueError(
            "branding.audio.bg_music_path is set to an empty string; "
            "remove the key or supply a path"
        )
    if mood == "":
        raise ValueError(
            "branding.audio.bg_music_mood is set to an empty string; "
            "remove the key or supply a mood name"
        )

    if path_raw and mood:
        raise ValueError(
            "branding.audio: set exactly one of bg_music_path or bg_music_mood, not both"
        )
    if not path_raw and not mood:
        return None

    if path_raw:
        # Mode A — user-supplied file, resolved like session paths
        resolved = resolve_session_path(path_raw, working_dir)
        if not resolved.exists():
            raise FileNotFoundError(
                f"branding.audio.bg_music_path → {resolved} does not exist"
            )
        return resolved

    # Mode B — bundled library lookup
    library_path = skill_dir / "_assets" / "bg_music" / "library.json"
    if not library_path.exists():
        raise FileNotFoundError(
            f"Bundled music library missing at {library_path}. "
            "Skill installation appears corrupted; re-install or restore the _assets/bg_music/ folder."
        )
    try:
        library = json.loads(library_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"_assets/bg_music/library.json is not valid JSON: {exc}. "
            "Restore it from the skill installation or re-run the curation step."
        ) from exc
    moods = library.get("moods", {})
    if mood not in moods:
        raise ValueError(
            f"branding.audio.bg_music_mood={mood!r} is not a known mood. "
            f"Valid moods: {sorted(moods.keys())}"
        )
    track_ids = moods[mood]
    if not track_ids:
        raise ValueError(
            f"branding.audio.bg_music_mood={mood!r} has no tracks in library.json"
        )
    track_path = skill_dir / "_assets" / "bg_music" / f"{track_ids[0]}.mp3"
    if not track_path.exists():
        raise FileNotFoundError(
            f"Library mood={mood} → first track {track_ids[0]}.mp3 "
            f"is missing at {track_path}"
        )
    return track_path


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_dotenv_if_present(working_dir: Path) -> None:
    """If `<working_dir>/.env` exists, load it into os.environ (without overwriting)."""
    env_path = working_dir / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)
