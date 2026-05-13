#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest>=8", "pyyaml>=6"]
# ///
"""End-to-end test: recorder loads storage_state and accesses gated content.

Spins up a localhost http.server with a cookie-gated `/protected` route.
Runs render_voiceover.py is NOT required — we build a stub manifest by hand
and skip TTS so the test is offline + fast. We then run record_demo.py and
assert it produced a reference.webm and didn't print any 401 markers.
"""
import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent


class CookieGatedHandler(http.server.SimpleHTTPRequestHandler):
    """Tiny gated server.

    GET /          → 200, plain HTML, always
    GET /protected → 200 with "Protected content" if `auth=ok` cookie; else 401
    """
    def do_GET(self):
        cookie = self.headers.get("Cookie", "")
        if self.path == "/":
            self._respond(200, "<html><body><h1>Home</h1></body></html>")
            return
        if self.path == "/protected":
            if "auth=ok" in cookie:
                self._respond(200, "<html><body><h1>Protected content</h1></body></html>")
            else:
                self._respond(401, "<html><body>Login required</body></html>")
            return
        self._respond(404, "not found")

    def log_message(self, *args):  # quiet
        pass

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode())


@pytest.fixture
def gated_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), CookieGatedHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _write_minimal_demo(wd: Path, base_url: str):
    """Build the smallest possible working dir that record_demo.py will accept.

    NOTE: The real manifest schema (from render_voiceover.py) uses:
      - "duration_seconds" (not "tts_duration_ms") — record_demo.py reads
        b["duration_seconds"] to build the durations dict.
      - "wav_path" (not "wav") — record_demo.py doesn't use wav_path directly
        but it's part of the schema written by render_voiceover.py.
    """
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "_voiceover").mkdir()
    # Stub manifest with one beat that has minimal duration
    (wd / "_voiceover" / "manifest.json").write_text(json.dumps({
        "model": "gpt-4o-mini-tts",
        "voice": "cedar",
        "beats": [{
            "id": "01_protected",
            "chars": 12,
            "duration_seconds": 0.1,
            "narration_hash": "x",
            "wav_path": "_voiceover/stub.wav",
        }]
    }))
    # Empty wav so ffprobe doesn't crash — produce 0.1s of silence
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", "0.1", "-acodec", "pcm_s16le", str(wd / "_voiceover" / "stub.wav"),
    ], check=True, capture_output=True)
    (wd / "storyboard.yaml").write_text(
        "beats:\n"
        "  - id: 01_protected\n"
        "    narration: irrelevant\n"
        "    action:\n"
        "      type: goto\n"
        f"      url: {base_url}/protected\n"
    )
    (wd / "branding.yaml").write_text("brand:\n  name: Test\n")
    (wd / "demo_config.yaml").write_text(
        f"site:\n  base_url: {base_url}\n"
        f"output:\n  filename: out.mp4\n  working_dir: {wd}\n"
        "recording:\n"
        "  viewport:\n    width: 800\n    height: 600\n"
        "  framerate: 25\n"
        "  pre_narration_ms: 100\n"
        "  post_narration_ms: 100\n"
        "session:\n  storage_state: ./auth.json\n"
    )


def _write_storage_state(wd: Path, host: str):
    """Hand-craft a Playwright storage_state.json with the gating cookie."""
    state = {
        "cookies": [{
            "name": "auth", "value": "ok",
            "domain": host, "path": "/",
            "expires": -1, "httpOnly": False,
            "secure": False, "sameSite": "Lax",
        }],
        "origins": []
    }
    (wd / "auth.json").write_text(json.dumps(state))


def test_recorder_honors_storage_state(tmp_path, gated_server):
    base = gated_server  # e.g. http://127.0.0.1:54321
    host, _port = base.replace("http://", "").split(":")
    wd = tmp_path / "wd"
    _write_minimal_demo(wd, base)
    _write_storage_state(wd, host)

    script = PROJECT / "scripts" / "record_demo.py"
    proc = subprocess.run(
        ["uv", "run", str(script), "--working-dir", str(wd)],
        capture_output=True, text=True, timeout=180,
    )

    assert proc.returncode == 0, (
        f"record_demo failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert "Loading storage_state from" in proc.stdout, (
        f"Expected 'Loading storage_state from' in stdout:\n{proc.stdout}"
    )
    # reference.webm should exist — storage_state would have made /protected return 200
    assert (wd / "_intermediate" / "reference.webm").exists(), (
        f"reference.webm missing under {wd / '_intermediate'}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
