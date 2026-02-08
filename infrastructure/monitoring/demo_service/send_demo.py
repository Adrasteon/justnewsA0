"""Emit a single trace and log to OTLP endpoint then expose HTTP 200.

This script sends one span and a log event to the configured OTLP endpoint
and then starts a minimal HTTP server so CI can probe it.
"""

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

OTLP_ENDPOINT = os.environ.get("OTLP_ENDPOINT", "http://otel-node:4318/v1/traces")


def configure_tracer():
    resource = Resource.create({"service.name": "justnews-demo-emitter"})
    provider = TracerProvider(resource=resource)
    # OTLP gRPC exporter can use an insecure channel in dev environments.
    # Use OTLP_GRPC_INSECURE env var to opt-in (true/1/yes).
    insecure_val = os.environ.get("OTLP_GRPC_INSECURE", "false").lower()
    insecure = insecure_val in ("1", "true", "yes")
    exporter = OTLPSpanExporter(
        endpoint=os.environ.get("OTLP_GRPC_ENDPOINT", "otel-node:4317"),
        insecure=insecure,
    )
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


class ProbeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


def run_server():
    server = HTTPServer(("0.0.0.0", 8080), ProbeHandler)
    server.serve_forever()


def main():
    configure_tracer()
    tracer = trace.get_tracer(__name__)

    # emit a sample trace
    with tracer.start_as_current_span("demo-span"):
        print("Sending demo trace to OTLP collector...", flush=True)

    # send a sample HTTP log into Loki-compatible endpoint if provided
    log_endpoint = os.environ.get("LOKI_PUSH", "")
    if log_endpoint:
        print("Posting sample log to Loki push endpoint...", flush=True)
        payload = {
            "streams": [
                {
                    "labels": '{job="justnews-demo"}',
                    "entries": [
                        {
                            "ts": "2025-01-01T00:00:00Z",
                            "line": "demo-log: hello from demo emitter",
                        }
                    ],
                }
            ]
        }
        try:
            requests.post(log_endpoint, json=payload, timeout=5)
        except Exception as e:
            print("Failed to push log to Loki", e)

    # run HTTP probe server to show the service is alive
    threading.Thread(target=run_server, daemon=True).start()

    # give collectors a short time to transmit
    time.sleep(2)

    # keep process running for a bit so CI can probe
    time.sleep(30)


if __name__ == "__main__":
    main()
