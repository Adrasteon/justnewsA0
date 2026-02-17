import json
import os
import subprocess
import sys
import time

import django


def run_manage_cmd(cmd_args):
    cmd = [
        sys.executable,
        os.path.join(os.getcwd(), "agents", "publisher", "manage.py"),
    ] + cmd_args
    env = os.environ.copy()
    publisher_dir = os.path.join(os.getcwd(), "agents", "publisher")
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{publisher_dir}:{current_pythonpath}" if current_pythonpath else publisher_dir

    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def test_publisher_api_and_metrics():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "justnews_publisher.settings")
    django.setup()

    # ensure migrations applied (creates PublishAudit table)
    rc, out, err = run_manage_cmd(["migrate", "--noinput"])
    assert rc == 0, f"migrate failed: {err}\n{out}"

    # Start a lightweight dev server on ephemeral port
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server_port = sock.getsockname()[1]
    sock.close()

    # Provide an API key for the server to require
    os.environ["PUBLISHER_API_KEY"] = "ci-key"

    server_proc = subprocess.Popen(
        [
            sys.executable,
            os.path.join(os.getcwd(), "agents", "publisher", "manage.py"),
            "runserver",
            f"127.0.0.1:{server_port}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # wait for server to be ready
        start = time.time()
        ready = False
        import urllib.request

        while time.time() - start < 8:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{server_port}/", timeout=1
                ) as r:
                    ready = True
                    break
            except Exception:
                time.sleep(0.25)
        assert ready, "publisher server failed to start in time"

        # POST a publish payload with correct API key
        payload = {
            "article_id": "e2e-1",
            "title": "CI Publish Test",
            "slug": "ci-publish-test",
            "summary": "summary",
            "body": "body",
            "author": "CI",
            "score": 0.9,
            "evidence": "none",
            "is_featured": False,
            "category": "world",
        }

        req = urllib.request.Request(
            f"http://127.0.0.1:{server_port}/api/publish/",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-API-KEY": "ci-key"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 200
            body = r.read().decode("utf-8")
            assert "ok" in body

        # Ensure metrics reflect the successful publish
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server_port}/api/metrics/", timeout=5
        ) as r:
            assert r.status == 200
            data = json.loads(r.read().decode("utf-8"))
            assert data.get("success", 0) >= 1

        # Ensure the Prometheus metrics endpoint is available and reports publishing metric name
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server_port}/metrics/", timeout=5
        ) as r:
            body = r.read().decode("utf-8")
            assert "justnews_stage_b_publishing_total" in body

    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()
        # close pipes to avoid unraisable ResourceWarnings
        try:
            if getattr(server_proc, "stdout", None):
                server_proc.stdout.close()
        except Exception:
            pass
        try:
            if getattr(server_proc, "stderr", None):
                server_proc.stderr.close()
        except Exception:
            pass
