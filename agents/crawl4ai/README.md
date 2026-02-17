Crawl4AI agent (JustNews) =================================

This directory contains the helper used to run the local Crawl4AI HTTP bridge as a managed JustNews agent. The service
is started via the instance systemd template `justnews@.service`as`justnews@crawl4ai`.

Files

- `main.py`– agent entry point invoked by the`justnews-start-agent.sh`helper. It launches the FastAPI bridge
  (`agents.c4ai.server:app`) using`uvicorn`.

- `__init__.py` – package marker.

How it's managed

- Use the canonical flow to start/enable the agent (recommended):

- `sudo ./infrastructure/systemd/reset_and_start.sh`

- or: `sudo ./infrastructure/systemd/scripts/enable_all.sh fresh`

Configuration

- Configure runtime variables in `/etc/justnews/global.env`or`/etc/justnews/crawl4ai.env`.
Important variables include `CRAWL4AI_HOST`,`CRAWL4AI_PORT`,`CRAWL4AI_USE_LLM`, and`CRAWL4AI_MODEL_CACHE_DIR`.

Security:

- `CRAWLER_API_TOKEN`: when set, the`/crawl`endpoint requires this token to be supplied via`Authorization: Bearer
  <token>`or`X-Api-Token` header. This is optional (if unset, endpoints are open for compatibility).

Notes

- The repository previously included a standalone systemd unit `crawl4ai-bridge.service`for ad-hoc testing; the
  canonical deployment uses`justnews@crawl4ai` so the agent participates in ordering, dependency gating, and health
  checks.

If you need me to update `/etc/justnews/global.env` examples or the unit template to pin an absolute Python path, tell
me which option you prefer (global.env PYTHON_BIN vs. absolute ExecStart in unit).
