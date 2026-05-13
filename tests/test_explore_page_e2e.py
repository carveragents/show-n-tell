#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest>=8"]
# ///
"""End-to-end test: explore_page.py loads storage_state and accesses gated content."""
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
    def do_GET(self):
        cookie = self.headers.get("Cookie", "")
        if self.path == "/protected":
            if "auth=ok" in cookie:
                self._respond(200, "<html><body><h1>Protected content</h1></body></html>")
            else:
                self._respond(401, "<html><body>Login required</body></html>")
            return
        self._respond(200, "<html><body><h1>Home</h1></body></html>")

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


def test_explore_page_loads_storage_state(tmp_path, gated_server):
    base = gated_server
    host = base.replace("http://", "").split(":")[0]

    # Hand-craft auth.json with the gating cookie
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(json.dumps({
        "cookies": [{
            "name": "auth", "value": "ok",
            "domain": host, "path": "/",
            "expires": -1, "httpOnly": False,
            "secure": False, "sameSite": "Lax",
        }],
        "origins": []
    }))

    out_dir = tmp_path / "explore"
    script = PROJECT / "helpers" / "explore_page.py"
    proc = subprocess.run(
        ["uv", "run", str(script),
         f"{base}/protected",
         "--storage-state", str(auth_path),
         "--out-dir", str(out_dir),
         "--slug", "protected"],
        capture_output=True, text=True, timeout=120,
    )

    assert proc.returncode == 0, f"explore_page failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert (out_dir / "protected.png").exists()
    assert (out_dir / "protected.png").stat().st_size > 0
    dom = (out_dir / "protected.dom.html").read_text()
    assert "Protected content" in dom, f"DOM did not contain protected content:\n{dom[:500]}"
    meta = json.loads((out_dir / "protected.meta.json").read_text())
    assert meta["final_url"] == f"{base}/protected", meta
    assert meta["status"] == 200, meta


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
