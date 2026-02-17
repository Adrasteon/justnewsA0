"""Entry point for the justnews-managed crawl4ai agent.
This module is invoked by the systemd helper via `python -m agents.crawl4ai.main`.
It launches the FastAPI bridge at agents.c4ai.server:app using uvicorn.
"""

import os
import sys


def main() -> None:
    host = os.environ.get("CRAWL4AI_HOST", "127.0.0.1")
    port = int(os.environ.get("CRAWL4AI_PORT", "3308"))
    log_level = os.environ.get("CRAWL4AI_LOG_LEVEL", "info")

    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover - runtime guard
        print(
            "uvicorn is required to run the Crawl4AI bridge (install uvicorn)",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc

    # Use programmatic run to avoid shell/argline issues
    uvicorn.run("agents.c4ai.server:app", host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
