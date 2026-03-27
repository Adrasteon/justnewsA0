import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException

from agents.common.mcp_bus_client import MCPBusClient

try:
    from database.models.migrated_models import MigratedDatabaseService
    from database.utils.migrated_database_utils import get_db_config

    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

logger = logging.getLogger(__name__)

EXTERNAL_URL = os.getenv("FACT_CHECKER_EXTERNAL_URL", "http://host.docker.internal:8003")
MCP_BUS_URL = os.getenv("MCP_BUS_URL", "http://localhost:8000")
PORT = int(os.getenv("PORT", os.getenv("FACT_CHECKER_AGENT_PORT", 8018)))

REQUEST_TIMEOUT_SEC = float(os.getenv("FACT_CHECKER_SHIM_TIMEOUT_SEC", "20"))
MAX_RETRIES = int(os.getenv("FACT_CHECKER_SHIM_MAX_RETRIES", "2"))
RETRY_BACKOFF_SEC = float(os.getenv("FACT_CHECKER_SHIM_RETRY_BACKOFF_SEC", "0.35"))
CB_FAILURE_THRESHOLD = int(os.getenv("FACT_CHECKER_SHIM_CB_FAILURE_THRESHOLD", "5"))
CB_OPEN_SEC = int(os.getenv("FACT_CHECKER_SHIM_CB_OPEN_SEC", "30"))

CANONICAL_VERDICTS = {
    "true": "True",
    "likely true": "Likely True",
    "uncertain": "Uncertain",
    "likely false": "Likely False",
    "false": "False",
}
VERDICT_ALIASES = {
    "proven": "True",
    "plausible": "Likely True",
    "unverified": "Uncertain",
    "improbable": "Likely False",
    "disproven": "False",
}
VERDICT_SCORE = {
    "True": 1.0,
    "Likely True": 0.75,
    "Uncertain": 0.5,
    "Likely False": 0.25,
    "False": 0.0,
}


class CircuitBreaker:
    def __init__(self, failure_threshold: int, open_seconds: int):
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self.failure_count = 0
        self.open_until = 0.0

    def is_open(self) -> bool:
        return time.monotonic() < self.open_until

    def record_success(self):
        self.failure_count = 0
        self.open_until = 0.0

    def record_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.open_until = time.monotonic() + self.open_seconds


_circuit_breaker = CircuitBreaker(CB_FAILURE_THRESHOLD, CB_OPEN_SEC)
_db_service: MigratedDatabaseService | None = None


def _normalize_verdict(raw_verdict: Any) -> str:
    if not raw_verdict:
        return "Uncertain"
    normalized = str(raw_verdict).strip().lower()
    if normalized in CANONICAL_VERDICTS:
        return CANONICAL_VERDICTS[normalized]
    if normalized in VERDICT_ALIASES:
        return VERDICT_ALIASES[normalized]
    return "Uncertain"


def _status_from_verdict(verdict: str) -> str:
    if verdict in ("True", "Likely True"):
        return "passed"
    if verdict in ("False", "Likely False"):
        return "failed"
    return "needs_review"


def _score_from_verdict(verdict: str) -> float:
    return VERDICT_SCORE.get(verdict, 0.5)


def _extract_kwargs(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if "kwargs" in payload and isinstance(payload.get("kwargs"), dict):
        return payload.get("kwargs", {})
    return payload


def _extract_article_id(payload: dict[str, Any]) -> int:
    kwargs = _extract_kwargs(payload)
    article_id = kwargs.get("article_id")
    if article_id is None and isinstance(payload, dict):
        args = payload.get("args")
        if isinstance(args, list) and args:
            article_id = args[0]
    try:
        return int(article_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Missing or invalid article_id") from exc


def _get_db_service() -> MigratedDatabaseService:
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable in shim runtime")

    global _db_service
    if _db_service is None:
        config = get_db_config()
        _db_service = MigratedDatabaseService(config)
    return _db_service


def _load_article_for_fact_check(article_id: int) -> dict[str, Any]:
    db_service = _get_db_service()
    cursor = None
    conn = None
    try:
        cursor, conn = db_service.get_safe_cursor(per_call=True, dictionary=True)
        cursor.execute(
            """
            SELECT id, title, content, summary, source_url AS url, source_id
            FROM articles
            WHERE id = %s
            LIMIT 1
            """,
            (article_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
        return row
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load article %s for fact-check", article_id)
        raise HTTPException(status_code=503, detail=f"Unable to load article {article_id}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def _persist_article_fact_check(
    article_id: int,
    fact_check_status: str,
    factual_accuracy_score: float,
    fact_check_details: dict[str, Any],
):
    db_service = _get_db_service()
    cursor = None
    conn = None
    try:
        cursor, conn = db_service.get_safe_cursor(per_call=True, dictionary=False)
        cursor.execute(
            """
            UPDATE articles
            SET fact_check_status = %s,
                factual_accuracy_score = %s,
                fact_check_details = %s
            WHERE id = %s
            """,
            (
                fact_check_status,
                float(factual_accuracy_score),
                json.dumps(fact_check_details, ensure_ascii=False),
                int(article_id),
            ),
        )
        conn.commit()
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        logger.exception("Failed to persist fact-check for article %s", article_id)
        raise HTTPException(status_code=503, detail=f"Unable to persist fact-check for article {article_id}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def _build_fact_check_payload(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    kwargs = _extract_kwargs(payload)

    if tool_name == "verify_claim":
        claim = kwargs.get("claim") or kwargs.get("fact")
        if not claim:
            raise HTTPException(status_code=400, detail="verify_claim requires claim or fact")
        return {
            "fact": str(claim),
            "context": kwargs.get("context"),
            "sources": kwargs.get("sources") or [],
            "options": kwargs.get("options") or {},
        }

    if tool_name == "fact_check":
        if "fact" in kwargs:
            return {
                "fact": str(kwargs.get("fact")),
                "context": kwargs.get("context"),
                "sources": kwargs.get("sources") or [],
                "options": kwargs.get("options") or {},
            }
        raise HTTPException(status_code=400, detail="fact_check requires fact")

    return kwargs


async def _post_with_resilience(endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
    if _circuit_breaker.is_open():
        raise HTTPException(status_code=503, detail="Fact-check upstream circuit open")

    api_key = os.getenv("FACT_CHECKER_API_KEY")
    headers = {"X-API-KEY": api_key} if api_key else {}
    timeout = httpx.Timeout(REQUEST_TIMEOUT_SEC)

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(endpoint, json=body, headers=headers)

            if response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"Upstream server error {response.status_code}",
                    request=response.request,
                    response=response,
                )

            response.raise_for_status()
            _circuit_breaker.record_success()
            return response.json()
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            last_error = exc
            _circuit_breaker.record_failure()
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SEC * (2**attempt))
                continue
            break
        except Exception as exc:
            last_error = exc
            _circuit_breaker.record_failure()
            break

    logger.error("Fact-check upstream request failed after retries: %s", last_error)
    raise HTTPException(status_code=502, detail=f"External fact-check error: {last_error}")


def _normalize_fact_check_response(response_payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(response_payload or {})
    normalized_verdict = _normalize_verdict(normalized.get("verdict"))
    normalized["verdict"] = normalized_verdict

    try:
        normalized_confidence = float(normalized.get("confidence", 0.0))
    except Exception:
        normalized_confidence = 0.0
    normalized["confidence"] = max(0.0, min(1.0, normalized_confidence))
    return normalized

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register active fact-check tool surface with MCP Bus.
    client = MCPBusClient(base_url=MCP_BUS_URL)
    agent_address = f"http://localhost:{PORT}"
    tools = [
        "verify_article",
        "verify_claim",
        "fact_check",
    ]

    client.register_agent(
        agent_name="fact_checker",
        agent_address=agent_address,
        tools=tools,
    )
    yield

app = FastAPI(lifespan=lifespan)

@app.post("/{tool_name}")
async def proxy_tool(tool_name: str, payload: dict):
    target_endpoint = "/fact_check"

    if tool_name == "verify_article":
        article_id = _extract_article_id(payload)
        article = _load_article_for_fact_check(article_id)
        fact_input = (article.get("summary") or article.get("content") or article.get("title") or "").strip()
        if not fact_input:
            raise HTTPException(status_code=422, detail=f"Article {article_id} has no fact-checkable text")

        context_parts = [
            f"title={article.get('title') or ''}",
            f"url={article.get('url') or ''}",
            f"source_id={article.get('source_id')}",
            f"article_id={article_id}",
        ]
        check_body = {
            "fact": fact_input[:8000],
            "context": " | ".join(context_parts),
            "sources": [article.get("url")] if article.get("url") else [],
            "options": {"mode": "verify_article", "article_id": article_id},
        }

        external_url = f"{EXTERNAL_URL}{target_endpoint}"
        raw_response = await _post_with_resilience(external_url, check_body)
        response = _normalize_fact_check_response(raw_response)

        verdict = response.get("verdict", "Uncertain")
        fact_check_status = _status_from_verdict(verdict)
        factual_accuracy_score = _score_from_verdict(verdict)
        details = {
            "verdict": verdict,
            "confidence": response.get("confidence", 0.0),
            "explanation": response.get("explanation", ""),
            "source": "fact_checker_shim",
            "checked_at": datetime.now(UTC).isoformat(),
            "trusted_sources": response.get("trusted_sources", []),
            "misleading_sources": response.get("misleading_sources", []),
        }

        _persist_article_fact_check(
            article_id=article_id,
            fact_check_status=fact_check_status,
            factual_accuracy_score=factual_accuracy_score,
            fact_check_details=details,
        )

        return {
            "status": "success",
            "article_id": article_id,
            "fact_check_status": fact_check_status,
            "factual_accuracy_score": factual_accuracy_score,
            "fact_check_details": details,
        }

    supported_tools = {"fact_check", "verify_claim"}
    if tool_name not in supported_tools:
        raise HTTPException(status_code=404, detail=f"Unsupported tool: {tool_name}")

    check_body = _build_fact_check_payload(tool_name, payload)
    external_url = f"{EXTERNAL_URL}{target_endpoint}"
    raw_response = await _post_with_resilience(external_url, check_body)
    return _normalize_fact_check_response(raw_response)

# Health check
@app.get("/health")
def health():
    return {
        "status": "ok",
        "mode": "proxy",
        "target": EXTERNAL_URL,
        "circuit_open": _circuit_breaker.is_open(),
        "circuit_failures": _circuit_breaker.failure_count,
    }
