import asyncio
import csv
import json
import os
import random
import sqlite3
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from common.metrics import JustNewsMetrics
from common.observability import get_logger

# Allow overriding DB path via env var so service can be started from any cwd or env
DB_PATH = os.environ.get(
    "HITL_DB_PATH", os.path.join(os.path.dirname(__file__), "hitl_staging.db")
)
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000").rstrip("/")
HITL_AGENT_NAME = os.environ.get("HITL_AGENT_NAME", "hitl_service")
HITL_SERVICE_ADDRESS = os.environ.get(
    "HITL_SERVICE_ADDRESS",
    f"http://localhost:{os.environ.get('HITL_SERVICE_PORT', '8040')}",
)
HITL_FORWARD_AGENT = os.environ.get("HITL_FORWARD_AGENT")
HITL_FORWARD_TOOL = os.environ.get("HITL_FORWARD_TOOL")
HITL_FORWARD_ENABLED = bool(HITL_FORWARD_AGENT and HITL_FORWARD_TOOL)
HITL_CANDIDATE_FORWARD_AGENT = os.environ.get("HITL_CANDIDATE_FORWARD_AGENT")
HITL_CANDIDATE_FORWARD_TOOL = os.environ.get("HITL_CANDIDATE_FORWARD_TOOL")
HITL_CANDIDATE_FORWARD_ENABLED = bool(
    HITL_CANDIDATE_FORWARD_AGENT and HITL_CANDIDATE_FORWARD_TOOL
)
HITL_TRAINING_FORWARD_AGENT = os.environ.get("HITL_TRAINING_FORWARD_AGENT")
HITL_TRAINING_FORWARD_TOOL = os.environ.get("HITL_TRAINING_FORWARD_TOOL")
HITL_TRAINING_FORWARD_ENABLED = bool(
    HITL_TRAINING_FORWARD_AGENT and HITL_TRAINING_FORWARD_TOOL
)
HITL_FORWARD_MAX_RETRIES = int(os.environ.get("HITL_FORWARD_MAX_RETRIES", "3"))
HITL_FORWARD_RETRY_BACKOFF_SECONDS = float(
    os.environ.get("HITL_FORWARD_RETRY_BACKOFF_SECONDS", "1.5")
)
HITL_FORWARD_HEALTHCHECK_INTERVAL_SECONDS = int(
    os.environ.get("HITL_FORWARD_HEALTHCHECK_INTERVAL_SECONDS", "60")
)
HITL_PRIORITY_SITES = {
    item.strip()
    for item in os.environ.get("HITL_PRIORITY_SITES", "").split(",")
    if item.strip()
}
HITL_QA_BACKLOG_ALERT_THRESHOLD = int(
    os.environ.get("HITL_QA_BACKLOG_ALERT_THRESHOLD", "50")
)
HITL_QA_MONITOR_INTERVAL_SECONDS = int(
    os.environ.get("HITL_QA_MONITOR_INTERVAL_SECONDS", "60")
)
HITL_QA_FAILURE_RATE_ALERT_THRESHOLD = float(
    os.environ.get("HITL_QA_FAILURE_RATE_ALERT_THRESHOLD", "0.05")
)
HITL_QA_FAILURE_MIN_SAMPLE = int(os.environ.get("HITL_QA_FAILURE_MIN_SAMPLE", "20"))
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
INDEX_FILE_PATH = os.path.join(STATIC_DIR, "index.html")

logger = get_logger(__name__)

app = FastAPI(
    title="HITL Service",
    description="Human-in-the-loop candidate labeling for the crawler pipeline",
    version="0.1.0",
)

metrics = JustNewsMetrics("hitl_service")
app.middleware("http")(metrics.request_middleware)


@app.get("/health")
async def health_check():
    """Health check endpoint for system probing."""
    return {"status": "ok", "service": "hitl_service"}


if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning(
        "Static directory %s not found; HITL UI assets unavailable", STATIC_DIR
    )


def ensure_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hitl_candidates (
            id TEXT PRIMARY KEY,
            url TEXT,
            site_id TEXT,
            extracted_title TEXT,
            extracted_text TEXT,
            raw_html_ref TEXT,
            features TEXT,
            candidate_ts TEXT,
            crawler_job_id TEXT,
            status TEXT,
            ingestion_priority INTEGER DEFAULT 0,
            suggested_label TEXT,
            suggested_confidence REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hitl_labels (
            id TEXT PRIMARY KEY,
            candidate_id TEXT,
            label TEXT,
            cleaned_text TEXT,
            annotator_id TEXT,
            created_at TEXT,
            source TEXT,
            treat_as_valid INTEGER DEFAULT 0,
            needs_cleanup INTEGER DEFAULT 0,
            qa_sampled INTEGER DEFAULT 0,
            ingest_enqueued_at TEXT,
            ingestion_status TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hitl_qa_queue (
            id TEXT PRIMARY KEY,
            label_id TEXT,
            candidate_id TEXT,
            created_at TEXT,
            review_status TEXT,
            reviewer_id TEXT,
            notes TEXT,
            reviewed_at TEXT
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_hitl_candidates_status_ts ON hitl_candidates (status, candidate_ts)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_hitl_labels_created_at ON hitl_labels (created_at)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_hitl_qa_queue_status ON hitl_qa_queue (review_status, created_at)"
    )
    conn.commit()
    conn.close()
    update_queue_metrics()


class CandidateEvent(BaseModel):
    id: str | None = None
    url: str
    site_id: str | None = None
    extracted_title: str | None = None
    extracted_text: str | None = None
    raw_html_ref: str | None = None
    features: dict[str, Any] | None = None
    crawler_ts: str | None = None
    crawler_job_id: str | None = None


class LabelRequest(BaseModel):
    candidate_id: str
    label: str
    cleaned_text: str | None = None
    annotator_id: str | None = None


class ToolCallRequest(BaseModel):
    tool: str = Field(..., description="Name of the tool to invoke")
    args: list[Any] = Field(default_factory=list, description="Positional arguments")
    kwargs: dict[str, Any] = Field(
        default_factory=dict, description="Keyword arguments"
    )


class QAReviewRequest(BaseModel):
    qa_id: str
    reviewer_id: str
    status: str
    notes: str | None = None


class MCPBusClient:
    def __init__(
        self, base_url: str = MCP_BUS_URL, timeout: tuple[float, float] = (3.0, 15.0)
    ):
        self.base_url = base_url
        self.timeout = timeout

    def register_agent(self, agent_name: str, agent_address: str) -> dict[str, Any]:
        payload = {"name": agent_name, "address": agent_address}
        response = requests.post(
            f"{self.base_url}/register",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def call_tool(
        self,
        agent_name: str,
        tool_name: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "agent": agent_name,
            "tool": tool_name,
            "args": args or [],
            "kwargs": kwargs or {},
        }
        response = requests.post(
            f"{self.base_url}/call",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def list_agents(self) -> dict[str, str]:
        response = requests.get(f"{self.base_url}/agents", timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            return data
        return {}


mcp_client = MCPBusClient()


def update_queue_metrics() -> None:
    """Update Prometheus gauges reflecting queue backlogs."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM hitl_candidates WHERE status='pending'")
        pending = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM hitl_candidates WHERE status='in_review'")
        in_review = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM hitl_labels WHERE treat_as_valid=1 AND ingestion_status='pending'",
        )
        ingest_backlog = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM hitl_qa_queue WHERE review_status='pending'",
        )
        qa_pending = cur.fetchone()[0]
        conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to update queue metrics: %s", exc)
        return

    metrics.update_queue_size("hitl_pending_candidates", pending)
    metrics.update_queue_size("hitl_in_review_candidates", in_review)
    metrics.update_queue_size("hitl_ingest_backlog", ingest_backlog)
    metrics.update_queue_size("hitl_qa_pending", qa_pending)


def _check_agent_health(agent_address: str) -> bool:
    try:
        response = requests.get(f"{agent_address.rstrip('/')}/health", timeout=(3, 6))
        response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("Health check failed for %s: %s", agent_address, exc)
        return False


def _extract_payload(
    call: ToolCallRequest, default_key: str | None = None
) -> dict[str, Any]:
    if call.args:
        candidate_payload = call.args[0]
    elif default_key and default_key in call.kwargs:
        candidate_payload = call.kwargs[default_key]
    else:
        candidate_payload = call.kwargs

    if not isinstance(candidate_payload, dict):
        raise HTTPException(
            status_code=400, detail="Tool payload must be a JSON object"
        )
    return candidate_payload


async def tool_receive_candidate(call: ToolCallRequest) -> dict[str, Any]:
    payload = _extract_payload(call, default_key="candidate")
    try:
        event = CandidateEvent(**payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid candidate payload: {exc}"
        ) from exc

    candidate_id = insert_candidate(event)
    metrics.increment("hitl_mcp_candidate_events_total")
    asyncio.create_task(forward_candidate_event(candidate_id))

    return {"status": "accepted", "candidate_id": candidate_id}


async def tool_submit_label(call: ToolCallRequest) -> dict[str, Any]:
    payload = _extract_payload(call, default_key="label")
    try:
        label_req = LabelRequest(**payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid label payload: {exc}"
        ) from exc

    metrics.increment("hitl_mcp_label_events_total")
    result = store_label(label_req)
    if result.get("enqueue_ingest") and result.get("ingest_payload"):
        asyncio.create_task(
            dispatch_ingest(result["ingest_payload"], result["label_id"])
        )
    if result.get("training_payload"):
        asyncio.create_task(
            forward_training_label(result["training_payload"], result["label_id"])
        )
    return result


async def tool_fetch_stats(_call: ToolCallRequest) -> dict[str, Any]:
    return await api_stats()


TOOL_HANDLERS: dict[str, Callable[[ToolCallRequest], Awaitable[dict[str, Any]]]] = {
    "receive_candidate": tool_receive_candidate,
    "submit_label": tool_submit_label,
    "fetch_stats": tool_fetch_stats,
}


async def startup_event():
    ensure_db()
    asyncio.create_task(register_with_mcp_bus())
    asyncio.create_task(monitor_qa_health())


# Register startup handler via add_event_handler to avoid use of the deprecated
# @app.on_event decorator (typing_extensions warns about deprecation). This
# keeps behavior identical but avoids deprecation warnings during test runs.
app.add_event_handler("startup", startup_event)


async def register_with_mcp_bus() -> None:
    attempt = 0
    max_attempts = 8
    while attempt < max_attempts:
        try:
            logger.info(
                "Registering HITL service with MCP Bus at %s as %s",
                MCP_BUS_URL,
                HITL_AGENT_NAME,
            )
            await asyncio.to_thread(
                mcp_client.register_agent,
                HITL_AGENT_NAME,
                HITL_SERVICE_ADDRESS,
            )
            logger.info("HITL service successfully registered with MCP Bus")
            await validate_forward_targets(initial=True)
            asyncio.create_task(periodic_forward_agent_verification())
            return
        except Exception as exc:  # noqa: BLE001
            wait_time = min(60, 2**attempt)
            logger.warning(
                "Failed to register with MCP Bus (attempt %s/%s): %s - retrying in %ss",
                attempt + 1,
                max_attempts,
                exc,
                wait_time,
            )
            attempt += 1
            await asyncio.sleep(wait_time)
    logger.error(
        "Exceeded max attempts registering with MCP Bus; continuing without registration"
    )


async def periodic_forward_agent_verification() -> None:
    if not any(
        [
            HITL_FORWARD_ENABLED,
            HITL_CANDIDATE_FORWARD_ENABLED,
            HITL_TRAINING_FORWARD_ENABLED,
        ]
    ):
        return
    while True:
        await asyncio.sleep(max(30, HITL_FORWARD_HEALTHCHECK_INTERVAL_SECONDS))
        await validate_forward_targets()


async def validate_forward_targets(initial: bool = False) -> None:
    if not any(
        [
            HITL_FORWARD_ENABLED,
            HITL_CANDIDATE_FORWARD_ENABLED,
            HITL_TRAINING_FORWARD_ENABLED,
        ]
    ):
        return

    try:
        agents = await asyncio.to_thread(mcp_client.list_agents)
        registry_ok = True
    except Exception as exc:  # noqa: BLE001
        registry_ok = False
        logger.warning("Failed to retrieve MCP agent registry: %s", exc)
        metrics.gauge("hitl_forward_registry_available", 0)
        return

    metrics.gauge("hitl_forward_registry_available", 1 if registry_ok else 0)

    def _check_target(agent: str | None, gauge_name: str) -> bool:
        if not agent:
            metrics.gauge(gauge_name, 0)
            return False
        address = agents.get(agent)
        if not address:
            logger.warning(
                "Forward target agent '%s' is not registered with MCP Bus", agent
            )
            metrics.gauge(gauge_name, 0)
            return False
        healthy = _check_agent_health(address)
        metrics.gauge(gauge_name, 1 if healthy else 0)
        if not healthy:
            logger.warning(
                "Forward target agent '%s' failed health verification", agent
            )
        return healthy

    forward_ok = (
        _check_target(HITL_FORWARD_AGENT, "hitl_forward_agent_available")
        if HITL_FORWARD_ENABLED
        else False
    )
    candidate_ok = (
        _check_target(
            HITL_CANDIDATE_FORWARD_AGENT, "hitl_candidate_forward_agent_available"
        )
        if HITL_CANDIDATE_FORWARD_ENABLED
        else False
    )
    training_ok = (
        _check_target(
            HITL_TRAINING_FORWARD_AGENT, "hitl_training_forward_agent_available"
        )
        if HITL_TRAINING_FORWARD_ENABLED
        else False
    )

    if initial:
        logger.info(
            "Forward targets verified on startup: ingest=%s candidate=%s training=%s",
            forward_ok,
            candidate_ok,
            training_ok,
        )


async def monitor_qa_health() -> None:
    while True:
        await asyncio.sleep(max(30, HITL_QA_MONITOR_INTERVAL_SECONDS))
        pending = await asyncio.to_thread(get_qa_pending)
        metrics.gauge("hitl_qa_pending_total", pending)
        if pending >= HITL_QA_BACKLOG_ALERT_THRESHOLD:
            logger.warning(
                "QA backlog (%s) exceeds threshold (%s)",
                pending,
                HITL_QA_BACKLOG_ALERT_THRESHOLD,
            )

        qa_metrics = await asyncio.to_thread(get_qa_failure_metrics)
        rate = float(qa_metrics["rate"])
        total_reviews = int(qa_metrics["total"])
        metrics.gauge("hitl_qa_failure_rate", rate)
        metrics.gauge("hitl_qa_reviews_window", total_reviews)

        if (
            total_reviews >= HITL_QA_FAILURE_MIN_SAMPLE
            and rate >= HITL_QA_FAILURE_RATE_ALERT_THRESHOLD
        ):
            logger.warning(
                "QA failure rate %.2f (over %s reviews) exceeds threshold %.2f",
                rate,
                total_reviews,
                HITL_QA_FAILURE_RATE_ALERT_THRESHOLD,
            )


def calculate_ingestion_priority(evt: CandidateEvent) -> int:
    priority = 0
    features = evt.features or {}
    word_count = features.get("word_count") if isinstance(features, dict) else None
    if isinstance(word_count, (int, float)):
        if word_count < 250:
            priority += 3
        elif word_count < 600:
            priority += 1
    link_density = features.get("link_density") if isinstance(features, dict) else None
    if isinstance(link_density, (int, float)) and link_density < 0.5:
        priority += 1
    if evt.site_id and evt.site_id in HITL_PRIORITY_SITES:
        priority += 2
    return max(0, min(int(priority), 5))


def insert_candidate(evt: CandidateEvent) -> str:
    cid = evt.id or str(uuid.uuid4())
    priority = calculate_ingestion_priority(evt)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO hitl_candidates (
            id,
            url,
            site_id,
            extracted_title,
            extracted_text,
            raw_html_ref,
            features,
            candidate_ts,
            crawler_job_id,
            status,
            ingestion_priority
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            cid,
            evt.url,
            evt.site_id,
            evt.extracted_title,
            evt.extracted_text,
            evt.raw_html_ref,
            json.dumps(evt.features or {}),
            evt.crawler_ts or datetime.now(UTC).isoformat(),
            evt.crawler_job_id,
            "pending",
            priority,
        ),
    )
    conn.commit()
    conn.close()
    update_queue_metrics()
    return cid


def fetch_candidate(candidate_id: str) -> dict[str, Any] | None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id,url,site_id,extracted_title,extracted_text,raw_html_ref,features,candidate_ts,crawler_job_id FROM hitl_candidates WHERE id=?",
        (candidate_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "url": row[1],
        "site_id": row[2],
        "extracted_title": row[3],
        "extracted_text": row[4],
        "raw_html_ref": row[5],
        "features": json.loads(row[6] or "{}"),
        "candidate_ts": row[7],
        "crawler_job_id": row[8],
    }


def get_next_batch(batch: int = 10) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id,url,site_id,extracted_title,extracted_text,features,candidate_ts
        FROM hitl_candidates
        WHERE status='pending'
        ORDER BY ingestion_priority DESC, candidate_ts
        LIMIT ?
        """,
        (batch,),
    )
    rows = cur.fetchall()
    results = []
    for r in rows:
        cid, url, site_id, title, text, features, cts = r
        results.append(
            {
                "id": cid,
                "url": url,
                "site_id": site_id,
                "extracted_title": title,
                "extracted_text": text,
                "features": json.loads(features or "{}"),
                "candidate_ts": cts,
            }
        )
        cur2 = conn.cursor()
        cur2.execute("UPDATE hitl_candidates SET status='in_review' WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    update_queue_metrics()
    return results


def update_ingest_status(label_id: str, status: str, timestamp: str | None) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE hitl_labels SET ingestion_status=?, ingest_enqueued_at=? WHERE id=?",
        (status, timestamp, label_id),
    )
    conn.commit()
    conn.close()


def build_training_payload(
    label_id: str,
    req: LabelRequest,
    created_at: str,
    treat_as_valid: bool,
    needs_cleanup: bool,
    qa_sampled: bool,
    ingest_job_id: str | None,
    candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    """Construct the training-forward payload produced for every label."""
    payload: dict[str, Any] = {
        "label_id": label_id,
        "candidate_id": req.candidate_id,
        "label": req.label.lower(),
        "annotator_id": req.annotator_id,
        "source": "ui",
        "cleaned_text": req.cleaned_text,
        "treat_as_valid": treat_as_valid,
        "needs_cleanup": needs_cleanup,
        "qa_sampled": qa_sampled,
        "ingest_job_id": ingest_job_id,
        "created_at": created_at,
        "ingestion_status": "pending" if treat_as_valid else "skipped",
    }
    if candidate:
        payload["candidate"] = candidate
    else:
        payload["candidate"] = None
    return payload


def store_label(req: LabelRequest) -> dict[str, Any]:
    lid = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    label_low = req.label.lower()
    treat_as_valid_bool = label_low in ("valid_news", "messy_news")
    needs_cleanup_bool = label_low == "messy_news"
    qa_sampled_bool = random.random() < 0.05
    candidate = fetch_candidate(req.candidate_id)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO hitl_labels (id,candidate_id,label,cleaned_text,annotator_id,created_at,source,treat_as_valid,needs_cleanup,qa_sampled,ingest_enqueued_at,ingestion_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            lid,
            req.candidate_id,
            req.label,
            req.cleaned_text,
            req.annotator_id,
            now,
            "ui",
            1 if treat_as_valid_bool else 0,
            1 if needs_cleanup_bool else 0,
            1 if qa_sampled_bool else 0,
            None,
            "pending" if treat_as_valid_bool else "skipped",
        ),
    )
    # update candidate status
    cur.execute(
        "UPDATE hitl_candidates SET status='labeled' WHERE id=?", (req.candidate_id,)
    )
    qa_entry_id: str | None = None
    if qa_sampled_bool:
        qa_entry_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO hitl_qa_queue (id,label_id,candidate_id,created_at,review_status,reviewer_id,notes,reviewed_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                qa_entry_id,
                lid,
                req.candidate_id,
                now,
                "pending",
                None,
                None,
                None,
            ),
        )
    conn.commit()
    conn.close()
    update_queue_metrics()
    ingest_job_id = str(uuid.uuid4()) if treat_as_valid_bool else None
    ingest_payload = None
    if treat_as_valid_bool and candidate:
        ingest_payload = {
            "job_id": ingest_job_id,
            "candidate_id": req.candidate_id,
            "label_id": lid,
            "label": req.label,
            "needs_cleanup": needs_cleanup_bool,
            "annotator_id": req.annotator_id,
            "cleaned_text": req.cleaned_text,
            "candidate": candidate,
            "created_at": now,
        }

    training_payload = build_training_payload(
        lid,
        req,
        now,
        treat_as_valid_bool,
        needs_cleanup_bool,
        qa_sampled_bool,
        ingest_job_id,
        candidate,
    )
    metrics.increment("hitl_training_events_total")

    return {
        "label_id": lid,
        "enqueue_ingest": bool(treat_as_valid_bool and ingest_payload),
        "ingest_job_id": ingest_job_id,
        "ingest_payload": ingest_payload,
        "qa_sampled": qa_sampled_bool,
        "qa_queue_id": qa_entry_id,
        "training_payload": training_payload,
    }


async def dispatch_ingest(job_payload: dict[str, Any], label_id: str) -> str:
    if not HITL_FORWARD_ENABLED:
        update_ingest_status(label_id, "skipped", None)
        metrics.increment("hitl_ingest_dispatch_skipped_total")
        return "skipped"

    metrics.increment("hitl_ingest_dispatch_attempts_total")
    start_time = time.time()
    attempt = 0
    max_attempts = max(1, HITL_FORWARD_MAX_RETRIES)

    while attempt < max_attempts:
        attempt += 1
        try:
            await asyncio.to_thread(
                mcp_client.call_tool,
                HITL_FORWARD_AGENT,
                HITL_FORWARD_TOOL,
                [],
                job_payload,
            )
            ts = datetime.now(UTC).isoformat()
            update_ingest_status(label_id, "enqueued", ts)
            metrics.increment("hitl_ingest_dispatch_success_total")
            metrics.timing(
                "hitl_ingest_dispatch_duration_seconds", time.time() - start_time
            )
            update_queue_metrics()
            return "enqueued"
        except Exception as exc:  # noqa: BLE001
            metrics.increment("hitl_ingest_dispatch_failure_total")
            logger.error(
                "Ingest dispatch attempt %s/%s failed via MCP Bus: %s",
                attempt,
                max_attempts,
                exc,
            )
            if attempt < max_attempts:
                backoff = HITL_FORWARD_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)

    logger.error(
        "Exceeded ingest dispatch retries; marking label %s as error", label_id
    )
    update_ingest_status(label_id, "error", None)
    update_queue_metrics()
    return "error"


async def forward_training_label(payload: dict[str, Any], label_id: str) -> str:
    if not payload:
        metrics.increment("hitl_training_forward_skipped_total")
        return "skipped"

    if not HITL_TRAINING_FORWARD_ENABLED:
        metrics.increment("hitl_training_forward_skipped_total")
        return "skipped"

    metrics.increment("hitl_training_forward_attempts_total")
    start_time = time.time()
    attempt = 0
    max_attempts = max(1, HITL_FORWARD_MAX_RETRIES)

    while attempt < max_attempts:
        attempt += 1
        try:
            await asyncio.to_thread(
                mcp_client.call_tool,
                HITL_TRAINING_FORWARD_AGENT,
                HITL_TRAINING_FORWARD_TOOL,
                [],
                payload,
            )
            metrics.increment("hitl_training_forward_success_total")
            metrics.timing(
                "hitl_training_forward_duration_seconds", time.time() - start_time
            )
            return "sent"
        except Exception as exc:  # noqa: BLE001
            metrics.increment("hitl_training_forward_failure_total")
            logger.warning(
                "Training forward attempt %s/%s via MCP Bus failed: %s",
                attempt,
                max_attempts,
                exc,
            )
            if attempt < max_attempts:
                backoff = HITL_FORWARD_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)

    logger.error("Exceeded training forward retries for label %s", label_id)
    return "error"


async def forward_candidate_event(candidate_id: str) -> None:
    if not HITL_CANDIDATE_FORWARD_ENABLED:
        return
    candidate = await asyncio.to_thread(fetch_candidate, candidate_id)
    if not candidate:
        return
    metrics.increment("hitl_candidate_forward_attempts_total")
    attempt = 0
    max_attempts = max(1, HITL_FORWARD_MAX_RETRIES)
    while attempt < max_attempts:
        attempt += 1
        try:
            await asyncio.to_thread(
                mcp_client.call_tool,
                HITL_CANDIDATE_FORWARD_AGENT,
                HITL_CANDIDATE_FORWARD_TOOL,
                [],
                candidate,
            )
            metrics.increment("hitl_candidate_forward_success_total")
            return
        except Exception as exc:  # noqa: BLE001
            metrics.increment("hitl_candidate_forward_failure_total")
            logger.warning(
                "Candidate forward attempt %s/%s via MCP Bus failed: %s",
                attempt,
                max_attempts,
                exc,
            )
            if attempt < max_attempts:
                backoff = HITL_FORWARD_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)


def get_ingest_backlog() -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM hitl_labels WHERE treat_as_valid=1 AND ingestion_status='pending'",
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_qa_pending() -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM hitl_qa_queue WHERE review_status='pending'")
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_qa_failure_metrics(window_hours: int = 24) -> dict[str, int | float]:
    since = (datetime.now(UTC) - timedelta(hours=window_hours)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM hitl_qa_queue WHERE review_status IN ('pass','fail') AND reviewed_at IS NOT NULL AND reviewed_at >= ?",
        (since,),
    )
    total = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM hitl_qa_queue WHERE review_status='fail' AND reviewed_at IS NOT NULL AND reviewed_at >= ?",
        (since,),
    )
    failures = cur.fetchone()[0]
    conn.close()
    rate = (failures / total) if total else 0.0
    return {"total": total, "failures": failures, "rate": rate}


def fetch_qa_entries(
    status: str | None = "pending", limit: int = 50
) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    params: list[Any] = []
    status_clause = ""
    if status and status.lower() != "all":
        status_clause = "WHERE q.review_status = ?"
        params.append(status.lower())
    query = f"""
        SELECT
            q.id AS qa_id,
            q.label_id,
            q.candidate_id,
            q.created_at AS qa_created_at,
            q.review_status,
            q.reviewer_id,
            q.notes,
            q.reviewed_at,
            l.label,
            l.cleaned_text,
            l.annotator_id,
            l.created_at AS label_created_at,
            l.treat_as_valid,
            l.needs_cleanup,
            c.url,
            c.site_id,
            c.extracted_title,
            c.extracted_text,
            c.candidate_ts
        FROM hitl_qa_queue q
        LEFT JOIN hitl_labels l ON q.label_id = l.id
        LEFT JOIN hitl_candidates c ON q.candidate_id = c.id
        {status_clause}
        ORDER BY q.created_at
        LIMIT ?
    """
    params.append(limit)
    cur.execute(query, params)
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


@app.post("/api/candidates")
async def api_post_candidate(evt: CandidateEvent):
    cid = insert_candidate(evt)
    asyncio.create_task(forward_candidate_event(cid))
    return {"candidate_id": cid}


@app.get("/api/next")
async def api_get_next(annotator_id: str | None = None, batch: int = 10):
    batch = max(1, min(100, batch))
    results = get_next_batch(batch)
    return {"candidates": results, "count": len(results)}


@app.post("/api/label")
async def api_post_label(req: LabelRequest):
    # basic validation
    if req.label.lower() not in ("not_news", "messy_news", "valid_news"):
        raise HTTPException(status_code=400, detail="invalid label")
    out = store_label(req)
    if out.get("enqueue_ingest") and out.get("ingest_payload"):
        asyncio.create_task(dispatch_ingest(out["ingest_payload"], out["label_id"]))
    if out.get("training_payload"):
        asyncio.create_task(
            forward_training_label(out["training_payload"], out["label_id"])
        )
    return out


@app.post("/call")
async def api_tool_router(call: ToolCallRequest):
    handler = TOOL_HANDLERS.get(call.tool)
    if not handler:
        available = sorted(TOOL_HANDLERS.keys())
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"unknown tool '{call.tool}'",
                "available_tools": available,
            },
        )
    response = await handler(call)
    return {"status": "ok", "data": response}


@app.post("/api/qa/review")
async def api_post_qa_review(req: QAReviewRequest):
    status = req.status.lower()
    if status not in ("pass", "fail"):
        raise HTTPException(status_code=400, detail="invalid QA status")
    now = datetime.now(UTC).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE hitl_qa_queue
        SET review_status=?, reviewer_id=?, notes=?, reviewed_at=?
        WHERE id=?
        """,
        (status, req.reviewer_id, req.notes, now, req.qa_id),
    )
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="QA entry not found")
    conn.commit()
    conn.close()
    return {"qa_id": req.qa_id, "review_status": status}


@app.get("/api/qa/pending")
async def api_get_qa_pending(limit: int = 50):
    limit = max(1, min(limit, 500))
    entries = await asyncio.to_thread(fetch_qa_entries, "pending", limit)
    return {"items": entries, "count": len(entries)}


@app.get("/api/qa/history")
async def api_get_qa_history(status: str = "all", limit: int = 200):
    limit = max(1, min(limit, 1000))
    entries = await asyncio.to_thread(fetch_qa_entries, status, limit)
    return {"items": entries, "count": len(entries)}


@app.get("/api/qa/export")
async def api_get_qa_export(limit: int = 1000):
    limit = max(1, min(limit, 5000))
    entries = await asyncio.to_thread(fetch_qa_entries, "all", limit)

    def _iter_csv():
        buffer = StringIO()
        writer = csv.writer(buffer)
        header = [
            "qa_id",
            "label_id",
            "candidate_id",
            "qa_created_at",
            "review_status",
            "reviewer_id",
            "notes",
            "reviewed_at",
            "label",
            "cleaned_text",
            "annotator_id",
            "label_created_at",
            "treat_as_valid",
            "needs_cleanup",
            "url",
            "site_id",
            "extracted_title",
            "extracted_text",
            "candidate_ts",
        ]
        writer.writerow(header)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

        for item in entries:
            row = [
                item.get("qa_id"),
                item.get("label_id"),
                item.get("candidate_id"),
                item.get("qa_created_at"),
                item.get("review_status"),
                item.get("reviewer_id"),
                item.get("notes"),
                item.get("reviewed_at"),
                item.get("label"),
                item.get("cleaned_text"),
                item.get("annotator_id"),
                item.get("label_created_at"),
                item.get("treat_as_valid"),
                item.get("needs_cleanup"),
                item.get("url"),
                item.get("site_id"),
                item.get("extracted_title"),
                item.get("extracted_text"),
                item.get("candidate_ts"),
            ]
            writer.writerow(row)
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    filename = datetime.now(UTC).strftime("hitl_qa_export_%Y%m%dT%H%M%SZ.csv")
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(_iter_csv(), media_type="text/csv", headers=headers)


@app.get("/api/stats")
async def api_stats():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM hitl_candidates WHERE status='pending'")
    pending = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM hitl_candidates WHERE status='in_review'")
    in_review = cur.fetchone()[0]
    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    last_hour = (now - timedelta(hours=1)).isoformat()
    cur.execute(
        "SELECT COUNT(*) FROM hitl_labels WHERE created_at >= ?", (start_of_day,)
    )
    labels_today = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM hitl_labels WHERE created_at >= ?",
        (last_hour,),
    )
    labels_last_hour = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM hitl_labels WHERE qa_sampled=1 AND created_at >= ?",
        (start_of_day,),
    )
    qa_sampled_today = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM hitl_qa_queue WHERE review_status='pending'")
    qa_pending = cur.fetchone()[0]
    conn.close()
    ingest_queue_len = get_ingest_backlog()
    # compute latency stats separately to keep connection scope minimal
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT created_at, ingest_enqueued_at
        FROM hitl_labels
        WHERE ingest_enqueued_at IS NOT NULL
        ORDER BY ingest_enqueued_at DESC
        LIMIT 100
        """
    )
    rows = cur.fetchall()
    conn.close()
    latencies: list[float] = []
    for created_at, enqueued in rows:
        if not created_at or not enqueued:
            continue
        try:
            created_dt = datetime.fromisoformat(created_at)
            enqueued_dt = datetime.fromisoformat(enqueued)
        except ValueError:
            continue
        latencies.append((enqueued_dt - created_dt).total_seconds())
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    return {
        "pending": pending,
        "in_review": in_review,
        "ingest_queue_len": ingest_queue_len,
        "pending_total": pending + in_review,
        "labels_today": labels_today,
        "labels_last_hour": labels_last_hour,
        "qa_sampled_today": qa_sampled_today,
        "qa_pending": qa_pending,
        "avg_label_to_ingest_latency_seconds": round(avg_latency, 2),
    }


@app.get("/", include_in_schema=False)
async def serve_root():
    if os.path.isfile(INDEX_FILE_PATH):
        return FileResponse(INDEX_FILE_PATH, media_type="text/html")
    raise HTTPException(status_code=404, detail="HITL UI not found")
