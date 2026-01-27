import os
import sqlite3
import subprocess
import sys
import time

import django
from django.test import Client


def run_manage_cmd(cmd_args):
    # Use the same python interpreter that runs pytest
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


def test_publisher_ingest_and_render():
    # Ensure environment configured for publisher app
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "justnews_publisher.settings")
    django.setup()

    sample_path = os.path.join(
        os.getcwd(), "agents", "publisher", "news", "sample_articles.json"
    )
    assert os.path.exists(sample_path), "Sample articles JSON not found"

    # Run ingest management command
    rc, out, err = run_manage_cmd(["ingest_articles", sample_path])
    assert rc == 0, f"Ingest command failed: {err}\nSTDOUT: {out}"

    # Connect to the publisher sqlite DB and assert articles present
    db_path = os.path.join(os.getcwd(), "agents", "publisher", "db.sqlite3")
    assert os.path.exists(db_path), "Publisher DB not found"

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM news_article")
    count = cur.fetchone()[0]
    cur.close()
    con.close()

    assert count >= 5, f"Expected at least 5 articles after ingest, found {count}"

    # Use Django test client to request one of the ingested article pages
    # Allow Django testserver host used by Client
    from django.conf import settings as dj_settings

    dj_settings.ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

    _ = Client()
    slugs = [
        "global-climate-accord-paris",
        "uk-parliament-education-bill",
        "tech-giants-ai-breakthrough",
    ]

    # Give a short delay for any DB write latency on constrained hosts
    time.sleep(0.2)

    # Start a lightweight dev server on an ephemeral free port and fetch the rendered page
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server_port = sock.getsockname()[1]
    sock.close()
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
        # wait for server to start (poll for bind/accept readiness)
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
        assert ready, "Dev server failed to start in time"
        # Use standard library HTTP client to avoid pytest's mocked 'requests' fixture

        for slug in slugs:
            url = f"http://127.0.0.1:{server_port}/article/{slug}/"
            with urllib.request.urlopen(url, timeout=5) as r:
                body = r.read().decode("utf-8", errors="ignore")
                assert r.status == 200, f"Article page returned {r.status} for {slug}"
                assert slug in body or "<html" in body, "Rendered content seems empty"
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()
        # Close pipes to avoid unraisable ResourceWarnings in some environments
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
