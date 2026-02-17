# Sentry integration example

This document shows a minimal Sentry integration pattern for JustNews services to capture uncaught exceptions and
release-level error tracking.

Requirements

- `sentry-sdk`is available in the runtime (see`security/requirements.txt`in the repo which already lists`sentry-sdk`).

Example usage (Python application)

1. Install the SDK in your runtime environment:

```bash
pip install sentry-sdk

```bash

1. Initialize in your service startup (safe minimal example):

```python
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

## Capture logging errors (ERROR+), and warnings

sentry_logging = LoggingIntegration(level=None, event_level="ERROR")

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN", ""),
    integrations=[sentry_logging],
    traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
    release=os.environ.get("JUSTNEWS_RELEASE", "dev"),
    environment=os.environ.get("DEPLOYMENT_ENVIRONMENT", "local"),
)

## Use as normal: sentry will automatically capture uncaught exceptions and log events

```

Notes & operational guidance

- Keep `SENTRY_DSN` secret (store in secure env / secrets manager). In local dev, set it to an empty string to avoid
  noisy test events.

- Use `traces_sample_rate` for production to avoid high-volume traces; 0.1 or lower is typical for heavy workloads.

- Combine Sentry events with OTEL traces by propagating trace IDs when applicable.

CI and sandbox projects -----------------------

We provide an optional GitHub Actions workflow (`.github/workflows/sentry- sandbox.yml`) that will send a single demo
event to a Sentry project when you manually dispatch it and the `SENTRY_DSN` secret is configured. This is useful for
validating integration with a sandbox project without enabling Sentry globally in CI.

Ensure `SENTRY_DSN`is not set by default in`/etc/justnews/global.env` and only add it to your CI secrets for sandbox
validation.
