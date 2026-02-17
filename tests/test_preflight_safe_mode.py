# SPDX-License-Identifier: MIT
import os
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class _SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            # Tell the preflight script the orchestrator is in SAFE_MODE
            self.wfile.write(b'{"status":"ok","safe_mode":true}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Silence default logging for test output clarity
        return


def _start_test_server():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    host, port = sock.getsockname()
    sock.close()

    server = HTTPServer(("127.0.0.1", port), _SimpleHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port


def test_preflight_gate_skips_preload_in_safe_mode(tmp_path):
    server, thread, port = _start_test_server()
    try:
        script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "infrastructure",
            "systemd",
            "scripts",
            "justnews-preflight-check.sh",
        )
        script_path = os.path.abspath(script_path)

        env = os.environ.copy()
        env["GPU_ORCHESTRATOR_URL"] = f"http://127.0.0.1:{port}"

        # Run the preflight script in gate-only mode pointing at our test server.
        # allow up to 30s for the script to run in CI or loaded test environments
        proc = subprocess.run(
            ["/bin/bash", script_path, "--gate-only"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
        )

        # Should exit successfully and mention SAFE_MODE in its output
        assert proc.returncode == 0, f"preflight failed: {proc.stdout}"
        assert "SAFE_MODE" in proc.stdout or "safe_mode" in proc.stdout.lower()
    finally:
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()
