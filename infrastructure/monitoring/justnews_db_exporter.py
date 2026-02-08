#!/usr/bin/env python3
"""Simple exporter exposing ChromaDB and MariaDB up/latency gauges."""

import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Gauge,
    generate_latest,
)

try:
    import requests
except Exception:
    requests = None

CHROMA_HOST = os.environ.get("CHROMADB_HOST", "127.0.0.1")
CHROMA_PORT = int(
    os.environ.get("CHROMADB_PORT", os.environ.get("CHROMA_PORT", "3307"))
)
CHROMA_TENANT_PATH = os.environ.get(
    "CHROMADB_HEALTH_PATH", "/api/v2/tenants/default_tenant"
)
MARIADB_HOST = os.environ.get("MARIADB_HOST", "127.0.0.1")
MARIADB_PORT = int(os.environ.get("MARIADB_PORT", "3306"))

SCRAPE_INTERVAL = int(os.environ.get("DB_EXPORTER_INTERVAL", "10"))
EXPORTER_PORT = int(os.environ.get("DB_EXPORTER_PORT", "9127"))

registry = CollectorRegistry()
chroma_up = Gauge(
    "justnews_chromadb_up", "ChromaDB up (1 = ok, 0 = down)", registry=registry
)
chroma_latency = Gauge(
    "justnews_chromadb_latency_seconds",
    "ChromaDB response latency seconds",
    registry=registry,
)
mariadb_up = Gauge(
    "justnews_mariadb_up",
    "MariaDB TCP up (1 = tcp connect ok, 0 = down)",
    registry=registry,
)
mariadb_latency = Gauge(
    "justnews_mariadb_tcp_latency_seconds",
    "MariaDB TCP connect latency seconds",
    registry=registry,
)

_last = {"chroma_up": 0, "chroma_latency": 0.0, "mariadb_up": 0, "mariadb_latency": 0.0}


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        data = generate_latest(registry)
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPE_LATEST)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        return


def probe_chroma():
    url = f"http://{CHROMA_HOST}:{CHROMA_PORT}{CHROMA_TENANT_PATH}"
    start = time.time()
    try:
        if requests is None:
            # fallback to socket-level check for HTTP port
            s = socket.create_connection((CHROMA_HOST, CHROMA_PORT), timeout=3)
            s.close()
            latency = time.time() - start
            _last["chroma_up"] = 1
            _last["chroma_latency"] = latency
            return
        r = requests.get(url, timeout=3)
        latency = time.time() - start
        if r.status_code == 200:
            _last["chroma_up"] = 1
            _last["chroma_latency"] = latency
        else:
            _last["chroma_up"] = 0
            _last["chroma_latency"] = latency
    except Exception:
        _last["chroma_up"] = 0
        _last["chroma_latency"] = 0.0


def probe_mariadb():
    start = time.time()
    try:
        s = socket.create_connection((MARIADB_HOST, MARIADB_PORT), timeout=3)
        s.close()
        latency = time.time() - start
        _last["mariadb_up"] = 1
        _last["mariadb_latency"] = latency
    except Exception:
        _last["mariadb_up"] = 0
        _last["mariadb_latency"] = 0.0


def updater():
    while True:
        try:
            probe_chroma()
            probe_mariadb()
            chroma_up.set(_last["chroma_up"])
            chroma_latency.set(_last["chroma_latency"])
            mariadb_up.set(_last["mariadb_up"])
            mariadb_latency.set(_last["mariadb_latency"])
        except Exception:
            pass
        time.sleep(SCRAPE_INTERVAL)


def run_server():
    server = HTTPServer(("127.0.0.1", EXPORTER_PORT), MetricsHandler)
    t = threading.Thread(target=updater, daemon=True)
    t.start()
    server.serve_forever()


if __name__ == "__main__":
    run_server()
