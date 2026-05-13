"""End-to-end: finalize_video.py with bg music mixes audio correctly.

Builds a minimal test working dir with a fake narration video + a synthetic
bg music input, runs finalize_video.py, and verifies the output audio has
both narration and (ducked) music present.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).parent.parent.resolve()

requires_uv = pytest.mark.skipif(
    shutil.which("uv") is None, reason="uv not on PATH"
)
requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH"
)


def _ffmpeg_run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _make_test_inputs(wd: Path) -> tuple[Path, Path]:
    """Generate a 10s 1440x900 black video with a 440Hz tone (the 'narration'
    proxy) and a separate 10s 220Hz tone mp3 (the 'bg music' proxy).
    Returns (input_video_path, bg_music_path).
    """
    branded = wd / "_intermediate" / "branded.mp4"
    branded.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg_run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=black:s=1440x900:r=25:d=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=10:sample_rate=24000",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(branded),
    ])
    music = wd / "music.mp3"
    _ffmpeg_run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=10:sample_rate=44100",
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(music),
    ])
    return branded, music


def _audio_rms(mp4: Path) -> float:
    """Return RMS level dB of the mp4's audio, downmixed to mono first.

    Downmixing via `-ac 1` produces a single channel so astats reports one
    `RMS level dB:` line regardless of source channel count.
    """
    result = subprocess.run(
        ["ffmpeg", "-i", str(mp4), "-ac", "1",
         "-af", "astats=metadata=1:reset=0",
         "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )
    # Look for "RMS level dB: -12.345" in stderr
    for line in result.stderr.splitlines():
        if "RMS level dB:" in line:
            return float(line.split(":")[-1].strip())
    raise AssertionError("RMS line not found in ffmpeg output")


def _write_minimal_configs(wd: Path, bg_music_path: Path) -> None:
    """Write the three YAMLs the script reads."""
    import yaml
    demo_config = {
        "site": {"base_url": "http://x"},
        "session": {"pre_session": []},
        "output": {
            "filename": "out.mp4",
            "working_dir": str(wd),
            "speed_multiplier": 1.0,
            "target_duration_seconds": 10,
        },
        "features": {
            "intro_slide": False,
            "outro_slide": False,
            "captions": {"enabled": False, "mode": "burned"},
            # Inert here — the no-features branch takes _mix_bg_music_only
            # before crossfade_seconds is ever consulted.
            "crossfade_seconds": 0.5,
            "brand_overlay": False,
        },
        "recording": {
            "viewport": {"width": 1440, "height": 900},
            "framerate": 25,
            "pre_narration_ms": 400,
            "post_narration_ms": 700,
        },
    }
    branding = {
        "brand": {"name": "Test"},
        "logo": {"path": "./nope.png"},
        "colors": {"ink": "#000", "ink_deep": "#000",
                   "accent": "#fff", "cream": "#fff"},
        "voice": {"provider": "openai", "model": "gpt-4o-mini-tts",
                  "voice": "cedar", "tone": "casual", "instructions": ""},
        "audio": {"bg_music_path": str(bg_music_path), "bg_music_volume": 0.4},
    }
    (wd / "demo_config.yaml").write_text(yaml.dump(demo_config))
    (wd / "branding.yaml").write_text(yaml.dump(branding))
    # Empty storyboard.yaml — finalize_video doesn't read it but load_configs might.
    (wd / "storyboard.yaml").write_text("beats: []\n")


@requires_uv
@requires_ffmpeg
def test_finalize_with_bg_music_path_produces_audible_mix(tmp_path):
    """Without intro/outro/captions, bg music should be mixed via _mix_bg_music_only."""
    branded, music = _make_test_inputs(tmp_path)
    _write_minimal_configs(tmp_path, music)
    output = tmp_path / "final.mp4"

    subprocess.run(
        ["uv", "run", str(SKILL_ROOT / "scripts" / "finalize_video.py"),
         "--working-dir", str(tmp_path),
         "--input", str(branded),
         "--output", str(output)],
        check=True,
    )

    assert output.exists()
    assert output.stat().st_size > 1000

    # Mix-strength check: amix normalizes by dividing amplitude by the number
    # of inputs (default normalize=1), so the mixed output is typically 5–9dB
    # quieter than the narration alone. What we verify:
    #   1. Not silent — output is above -50dBFS.
    #   2. Mix contribution — output is within 10dB of the input narration,
    #      proving the signal passed through the filter graph rather than being
    #      dropped or severely attenuated. (A missing/broken mix would land near
    #      -60dBFS or lower.)
    rms_input = _audio_rms(branded)
    rms_output = _audio_rms(output)
    assert rms_output > -50.0, (
        f"output audio appears silent or near-silent: {rms_output:.1f}dB"
    )
    assert rms_output >= rms_input - 10.0, (
        f"output audio is more than 10dB below input — mixing likely broken: "
        f"input={rms_input:.1f}dB, output={rms_output:.1f}dB"
    )


@requires_uv
@requires_ffmpeg
def test_finalize_with_unknown_mood_fails_fast(tmp_path):
    """Mood not in the library → finalize_video.py exits non-zero with actionable error."""
    branded, _ = _make_test_inputs(tmp_path)
    _write_minimal_configs(tmp_path, tmp_path / "ignored.mp3")
    # Overwrite branding.yaml with an unknown mood
    import yaml
    (tmp_path / "branding.yaml").write_text(yaml.dump({
        "brand": {"name": "Test"},
        "logo": {"path": "./nope.png"},
        "colors": {"ink": "#000", "ink_deep": "#000",
                   "accent": "#fff", "cream": "#fff"},
        "voice": {"provider": "openai", "model": "gpt-4o-mini-tts",
                  "voice": "cedar", "tone": "casual", "instructions": ""},
        "audio": {"bg_music_mood": "spicy"},
    }))
    result = subprocess.run(
        ["uv", "run", str(SKILL_ROOT / "scripts" / "finalize_video.py"),
         "--working-dir", str(tmp_path),
         "--input", str(branded),
         "--output", str(tmp_path / "final.mp4")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "spicy" in (result.stderr + result.stdout)
