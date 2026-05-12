"""Shared helpers for demo-video-from-site scripts.

Kept small and dependency-light. Loaded by other scripts via:
    sys.path.insert(0, str(Path(__file__).parent))
    from _lib import ...
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml


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
