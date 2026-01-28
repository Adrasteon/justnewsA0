"""
GPU Orchestrator Engine - Core logic for GPU management and model preloading.

This module contains the sophisticated GPU orchestration functionality including:
- NVML integration for detailed GPU monitoring
- Model preloading with background job management
- GPU lease allocation and management
- MPS (Multi-Process Service) detection and configuration
- Comprehensive telemetry and health monitoring

Integration note:
 - For automatic telemetry capture when a GPU is active, this repo includes
     `scripts/perf/gpu_activity_agent.py` and `scripts/perf/gpu_telemetry_exporter.py`.
     See `docs/gpu_telemetry_integration.md` for recommended deployment and systemd examples.
"""

import json
import multiprocessing as mp
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # NVML bindings became optional once we moved to the conda-provided nvidia-ml-py package
    import pynvml  # type: ignore

    _HAS_PYNVML = True
except (
    ModuleNotFoundError
):  # pragma: no cover - exercised implicitly when NVML bindings are absent
    pynvml = None  # type: ignore
    _HAS_PYNVML = False
from datetime import UTC

from fastapi import HTTPException
from prometheus_client import Counter, Gauge, Histogram

from common.metrics import JustNewsMetrics
from common.tracing import inject_trace_context
from database.utils.migrated_database_utils import create_database_service

# Constants
GPU_ORCHESTRATOR_PORT = int(os.environ.get("GPU_ORCHESTRATOR_PORT", "8008"))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
SAFE_MODE = os.environ.get("SAFE_MODE", "false").lower() == "true"
ENABLE_NVML = os.environ.get("ENABLE_NVML", "false").lower() == "true"
_SKIP_BOOTSTRAP = os.environ.get("GPU_ORCHESTRATOR_SKIP_BOOTSTRAP", "").lower() in (
    "1",
    "true",
    "yes",
)

# Global state
_START_TIME = time.time()
READINESS = False
POLICY = {
    "max_memory_per_agent_mb": 4096,
    "allow_fractional_shares": False,
    "kill_on_oom": False,
}
ALLOCATIONS: dict[str, dict[str, Any]] = {}
_MODEL_PRELOAD_STATE = {
    "started_at": None,
    "completed_at": None,
    "in_progress": False,
    "summary": {"total": 0, "done": 0, "failed": 0},
    "per_agent": {},
}

# NVML state
_NVML_SUPPORTED = False
_NVML_INIT_ERROR: str | None = None
_NVML_HANDLE_CACHE: dict[int, Any] = {}


class GPUOrchestratorEngine:
    """Core engine for GPU orchestration and management."""

    def __init__(self, bootstrap_external_services: bool | None = None):
        self.logger = self._setup_logging()
        self.metrics = JustNewsMetrics("gpu_orchestrator")
        self._initialize_metrics()

        bootstrap = bootstrap_external_services
        if bootstrap is None:
            bootstrap = not _SKIP_BOOTSTRAP
        self._bootstrap_external = bootstrap

        # Worker pool management: track spawned adapter worker pools
        # Structure: {pool_id: {"model": str, "adapter": str|None, "num_workers": int, "procs": [Process], "started_at": float}}
        self._WORKER_POOLS: dict[str, dict] = {}

        # Default optional services to None; tests can inject fakes when bootstrap is skipped.
        self.db_service = None
        self.redis_client = None

        # Reclaim / DLQ configuration (always set so tests can exercise behavior)
        self._job_retry_max = int(os.environ.get("ORCH_JOB_RETRY_MAX", "5"))
        self._claim_idle_ms = int(os.environ.get("ORCH_CLAIM_IDLE_MS", str(60 * 1000)))
        self._reclaim_interval_s = int(os.environ.get("ORCH_RECLAIM_INTERVAL_S", "30"))

        # Leader election state (always initialized)
        self._leader_lock_name = os.environ.get(
            "GPU_ORCHESTRATOR_LEADER_LOCK", "gpu_orchestrator_leader"
        )
        self._leader_try_timeout = int(
            os.environ.get("GPU_ORCHESTRATOR_LEADER_TRY_TIMEOUT", "1")
        )
        self.is_leader = False

        # Ensure VLLM and related attributes exist even in lightweight test mode
        self._vllm_process = None
        # Allow tests to pre-set _vllm_enabled; only set from env if not already present
        if not hasattr(self, '_vllm_enabled'):
            self._vllm_enabled = os.environ.get("VLLM_ENABLED", "false").lower() == "true"
        self._model_spec = None
        self.vllm_restart_counter = Counter(
            "gpu_orchestrator_vllm_restarts_total",
            "Total number of vLLM managed restarts",
            registry=self.metrics.registry,
        )
        self.vllm_oom_counter = Counter(
            "gpu_orchestrator_vllm_ooms_total",
            "Total number of vLLM OOM events observed",
            registry=self.metrics.registry,
        )
        self.vllm_status_gauge = Gauge(
            "gpu_orchestrator_vllm_status",
            "Current vLLM status: 0=stopped,1=starting,2=running,3=degraded",
            registry=self.metrics.registry,
        )

        # make instance file path writable so tests can monkeypatch engine.__file__
        self.__file__ = __file__

        # If vLLM is enabled, attempt to load canonical spec and start it; run even in lightweight mode
        if self._vllm_enabled and not SAFE_MODE:
            # Start optional metrics pusher if configured (best-effort)
            try:
                pushgw = os.environ.get("METRICS_PUSHGATEWAY_URL")
                push_interval = int(os.environ.get("METRICS_PUSH_INTERVAL_SECONDS", "30"))
                if pushgw:
                    t = threading.Thread(target=self._metrics_pusher_loop, args=(pushgw, push_interval), daemon=True)
                    t.start()
            except Exception as e:
                self.logger.warning(f"Failed to start metrics pusher: {e}")

            # If a canonical spec exists in config, prefer orchestrator-managed start
            try:
                cfg_file = Path(getattr(self, '__file__', __file__)).resolve().parents[2] / "config" / "vllm_mistral_7b.yaml"
                if cfg_file.exists():
                    try:
                        import yaml

                        cfg = yaml.safe_load(cfg_file.read_text())
                        model_cfg = cfg.get("model", {})
                        runtime = cfg.get("runtime", {})
                        service = cfg.get("service", {})
                        spec = self.ModelSpec(
                            id=model_cfg.get("id"),
                            dtype=model_cfg.get("dtype", "bf16"),
                            max_length=model_cfg.get("max_length", 4096),
                            max_batch_size=model_cfg.get("max_batch_size", 4),
                            max_tokens_per_request=model_cfg.get("max_tokens_per_request", 1024),
                            num_workers=model_cfg.get("num_workers", 1),
                            gpu_memory_util=runtime.get("gpu_memory_util", 0.75),
                            py_torch_alloc_conf=runtime.get("py_torch_alloc_conf", "expandable_segments:True"),
                            service_unit=service.get("systemd_unit"),
                            memory_max=service.get("memory_max"),
                            cpu_quota=service.get("cpu_quota"),
                        )
                        self.logger.info("Loaded canonical model spec from config/vllm_mistral_7b.yaml")
                        self.ensure_model_installed(spec)
                        # Only start if it is safe to do so
                        if self.can_start_model(spec):
                            self.start_model(spec)
                        else:
                            self.logger.warning("Insufficient GPU headroom to start the canonical model; not starting automatically")
                    except Exception as e:
                        self.logger.warning(f"Failed to load canonical vllm spec: {e}")
                else:
                    self._start_vllm_server()
            except Exception as e:
                self.logger.error(f"Failed to start VLLM server: {e}")

        if not self._bootstrap_external:
            self.logger.info(
                "GPU Orchestrator running in lightweight test mode; external services will not auto-bootstrap."
            )
            return

        # Start background lifecycle enforcer thread
        try:
            t = threading.Thread(target=self._background_policy_enforcer, daemon=True)
            t.start()
            self.logger.debug("Worker pool lifecycle enforcer started")
        except Exception as e:
            self.logger.warning(f"Failed to start lifecycle enforcer: {e}")

        # Optional MariaDB service used for persistence of leases and pools
        try:
            self.db_service = create_database_service()
        except Exception:
            self.db_service = None

        # Backwards-compatibility shim: ensure the db_service exposes a minimal
        # API that unit tests which patch create_database_service may rely on.
        try:
            from database.utils.migrated_database_utils import ensure_service_compat

            if self.db_service is not None:
                self.db_service = ensure_service_compat(self.db_service)
        except Exception:
            # Defensive: do not fail init if we cannot patch the fake service
            self.logger.debug("Failed to install db_service compatibility shims")

        # Optional Redis client for streams
        try:
            import redis

            redis_url = os.environ.get("REDIS_URL", None)
            if redis_url:
                self.redis_client = redis.from_url(redis_url)
            else:
                self.redis_client = redis.Redis()
        except Exception:
            self.redis_client = None

        # Start background reclaimer loop if redis available
        try:
            if self.redis_client:
                t = threading.Thread(target=self._reclaimer_loop, daemon=True)
                t.start()
        except Exception:
            self.logger.debug("Failed to start reclaimer loop")

        # Rehydrate any persisted worker pool records so state survives restarts
        try:
            if self.db_service:
                self._rehydrate_worker_pools_from_db()
        except Exception:
            self.logger.debug("Failed to rehydrate worker pools from DB (continuing)")

        # Start background election loop
        try:
            t = threading.Thread(target=self._leader_election_loop, daemon=True)
            t.start()
        except Exception:
            self.logger.debug("Failed to start leader election loop")

        # VLLM server management (attributes initialized earlier to support lightweight/test mode)
        self._vllm_process = None
        self._vllm_enabled = os.environ.get("VLLM_ENABLED", "false").lower() == "true"
        self._model_spec = None

        # vLLM configuration/start block moved to execute earlier so tests and lightweight modes can exercise startup logic
        # (originally here, moved to before the lightweight return to support tests that re-run __init__)
        # NOTE: if you need to change vLLM boot behavior update the copy above the early return.


    def get_metrics_text(self) -> str:
        """Return collected Prometheus metrics in text format."""
        try:
            return self.metrics.get_metrics()
        except Exception:
            return ""

    def _metrics_pusher_loop(self, pushgw: str, interval: int) -> None:
        """Background loop that pushes metrics to a Prometheus Pushgateway if configured."""
        try:
            from prometheus_client import push_to_gateway
        except Exception:
            self.logger.warning("prometheus_client.push_to_gateway not available; metrics push disabled")
            return

        job = f"gpu_orchestrator_{os.uname().nodename}"
        self.logger.info(f"Starting metrics pusher to {pushgw} (interval={interval}s)")
        while True:
            try:
                push_to_gateway(pushgw, job=job, registry=self.metrics.registry)
            except Exception as e:
                self.logger.debug(f"Metrics push failed: {e}")
            time.sleep(interval)

        # Register cleanup on exit
        import atexit

        atexit.register(self.cleanup)

    def _setup_logging(self):
        """Set up logging for the GPU orchestrator."""
        import logging

        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(__name__)

    def _initialize_metrics(self):
        """Initialize Prometheus metrics."""
        # Uptime gauge
        self.uptime_gauge = Gauge(
            "gpu_orchestrator_uptime_seconds",
            "GPU orchestrator uptime in seconds",
            ["agent", "agent_display_name"],
            registry=self.metrics.registry,
        )
        self.uptime_gauge.labels(
            agent=self.metrics.agent_name, agent_display_name=self.metrics.display_name
        ).set(time.time() - _START_TIME)

        # MPS enabled gauge
        self.mps_enabled_gauge = Gauge(
            "gpu_orchestrator_mps_enabled",
            "Whether NVIDIA MPS is enabled (1) or disabled (0)",
            ["agent", "agent_display_name"],
            registry=self.metrics.registry,
        )

        # Lease expired counter
        self.lease_expired_counter = Counter(
            "gpu_orchestrator_lease_expired_total",
            "Total number of GPU leases that have expired",
            ["agent", "agent_display_name"],
            registry=self.metrics.registry,
        )

        # NVML supported gauge
        self.nvml_supported_gauge = Gauge(
            "gpu_orchestrator_nvml_supported",
            "Whether NVML is supported and enabled (1) or not (0)",
            ["agent", "agent_display_name"],
            registry=self.metrics.registry,
        )

        # Job queue metrics
        self.stream_length_gauge = Gauge(
            "gpu_orchestrator_stream_length",
            "Number of messages in Redis stream",
            ["stream"],
            registry=self.metrics.registry,
        )

        self.pending_jobs_gauge = Gauge(
            "gpu_orchestrator_pending_jobs",
            "Number of pending jobs in consumer group",
            ["stream", "group"],
            registry=self.metrics.registry,
        )

        self.job_processing_duration_histogram = Histogram(
            "gpu_orchestrator_job_processing_duration_seconds",
            "Time taken to process jobs",
            ["job_type"],
            registry=self.metrics.registry,
        )

        self.job_retry_counter = Counter(
            "gpu_orchestrator_job_retries_total",
            "Total number of job retries",
            ["job_type"],
            registry=self.metrics.registry,
        )

        # Reclaimer metrics
        self.reclaimer_runs = Counter(
            "gpu_orchestrator_reclaimer_runs_total",
            "Total number of reclaimer passes executed",
            registry=self.metrics.registry,
        )

        self.reclaimer_errors = Counter(
            "gpu_orchestrator_reclaimer_errors_total",
            "Total number of errors observed during reclaimer passes",
            registry=self.metrics.registry,
        )

        self.reclaimer_requeued = Counter(
            "gpu_orchestrator_reclaimer_requeued_total",
            "Total number of messages requeued by the reclaimer",
            registry=self.metrics.registry,
        )

        self.reclaimer_dlq = Counter(
            "gpu_orchestrator_reclaimer_dlq_total",
            "Total number of messages moved to DLQ by the reclaimer",
            registry=self.metrics.registry,
        )

    def _get_safe_cursor(self, dictionary: bool | None = None, per_call: bool = False, buffered: bool = False):
        """Helper to obtain a (cursor, conn) pair from db_service in a robust way.

        Tries db_service.get_safe_cursor(...) first and falls back to using
        `mb_conn` or `get_connection()` when test fakes don't provide
        a well-formed get_safe_cursor implementation.
        """
        if not getattr(self, "db_service", None):
            raise RuntimeError("No db_service available")
        try:
            pair = self.db_service.get_safe_cursor(per_call=per_call, dictionary=dictionary, buffered=buffered)
            if isinstance(pair, tuple) and len(pair) == 2:
                return pair
        except Exception:
            pass
        # Fallback: prefer explicit mb_conn if present (common in unit tests)
        conn = getattr(self.db_service, "mb_conn", None)
        if conn is None and callable(getattr(self.db_service, "get_connection", None)):
            try:
                conn = self.db_service.get_connection()
            except Exception:
                conn = None
        if conn is None:
            conn = self.db_service
        cursor = conn.cursor()
        return cursor, conn


    def initialize_nvml(self) -> None:
        """Initialize NVML for GPU monitoring."""
        global _NVML_SUPPORTED, _NVML_INIT_ERROR

        if not ENABLE_NVML:
            self.logger.info("NVML is disabled via environment variable.")
            return

        if not _HAS_PYNVML:
            _NVML_SUPPORTED = False
            _NVML_INIT_ERROR = "pynvml module not available"
            self.logger.info(
                "NVML requested but pynvml is not installed. Install nvidia-ml-py to enable NVML metrics."
            )
            return

        try:
            pynvml.nvmlInit()
            _NVML_SUPPORTED = True
            self.logger.debug("NVML initialized successfully.")

            # Populate handle cache
            device_count = pynvml.nvmlDeviceGetCount()
            for i in range(device_count):
                _NVML_HANDLE_CACHE[i] = pynvml.nvmlDeviceGetHandleByIndex(i)

            # Log detailed GPU information
            for i in range(device_count):
                handle = _NVML_HANDLE_CACHE[i]
                name = pynvml.nvmlDeviceGetName(handle)
                # Ensure name is decoded properly if it's bytes
                if isinstance(name, bytes):
                    name_str = name.decode('utf-8')
                else:
                    name_str = str(name)
                
                memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                self.logger.debug(f"Device {i}: {name_str}")
                self.logger.debug(f"  Total memory: {memory_info.total / 1024**2} MB")
                self.logger.debug(f"  Used memory: {memory_info.used / 1024**2} MB")
                self.logger.debug(f"  Free memory: {memory_info.free / 1024**2} MB")

        except Exception as e:
            _NVML_SUPPORTED = False
            _NVML_INIT_ERROR = str(e)
            self.logger.error(f"NVML initialization failed: {e}")

    def get_nvml_handle(self, index: int) -> Any | None:
        """Get NVML handle for a GPU index."""
        return _NVML_HANDLE_CACHE.get(index)

    # -------------------------------
    # Model Specification & Management
    # -------------------------------

    @dataclass
    class ModelSpec:
        id: str
        dtype: str = "bf16"
        max_length: int = 4096
        max_batch_size: int = 4
        max_tokens_per_request: int = 1024
        num_workers: int = 1
        gpu_memory_util: float = 0.75
        py_torch_alloc_conf: str = "expandable_segments:True"
        service_unit: str | None = None
        memory_max: str | None = None
        cpu_quota: str | None = None
        adapter_paths: list[str] = field(default_factory=list)

    def ensure_model_installed(self, spec: "GPUOrchestratorEngine.ModelSpec") -> Path | None:
        """Check ModelStore or HF availability for the given spec. Returns a Path if a local path is resolved."""
        try:
            from models import model_loader

            path = model_loader._resolve_model_store_path(agent=None, model_id=spec.id)
            if path and path.exists():
                self.logger.info(f"Model {spec.id} resolved in ModelStore at {path}")
                # Collect adapters from AGENT_MODEL_MAP.json if present
                try:
                    import json
                    am_base = Path(getattr(self, '__file__', __file__)).resolve().parents[2]
                    am = am_base / "AGENT_MODEL_MAP.json"
                    if am.exists():
                        j = json.loads(am.read_text())
                        adapters = []
                        for _agent, arr in j.get("agents", {}).items():
                            for item in arr:
                                if item.get("base_ref") and item.get("base_ref").startswith("mistral-7b"):
                                    adapters.append(item.get("adapter_model_store_path"))
                        spec.adapter_paths = adapters
                except Exception:
                    self.logger.debug("Failed to collect adapters from AGENT_MODEL_MAP.json")
                return path
            self.logger.info(f"Model {spec.id} not found in ModelStore; will rely on HF id or repo path")
        except Exception:
            self.logger.debug("ModelStore integration not available or failed to resolve model")
        # Even if ModelStore resolution fails, attempt to collect adapters from AGENT_MODEL_MAP.json
        try:
            import json
            am_base = Path(getattr(self, '__file__', __file__)).resolve().parents[2]
            am = am_base / "AGENT_MODEL_MAP.json"
            if am.exists():
                j = json.loads(am.read_text())
                adapters = []
                for _agent, arr in j.get("agents", {}).items():
                    for item in arr:
                        if item.get("base_ref") and item.get("base_ref").startswith("mistral-7b"):
                            adapters.append(item.get("adapter_model_store_path"))
                spec.adapter_paths = adapters
        except Exception:
            self.logger.debug("Failed to collect adapters from AGENT_MODEL_MAP.json")
        return None

    def _free_gpu_memory_mb(self, index: int = 0) -> int:
        """Return free GPU memory in MB using NVML if enabled, otherwise via nvidia-smi parsing."""
        try:
            if _NVML_SUPPORTED and index in _NVML_HANDLE_CACHE:
                handle = _NVML_HANDLE_CACHE[index]
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                return int(mem.free / 1024**2)
        except Exception:
            pass
        # Fallback: use nvidia-smi query
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True)
            lines = r.stdout.strip().splitlines()
            if lines:
                val = int(lines[index].strip())
                return val
        except Exception:
            pass
        return 0

    def can_start_model(self, spec: "GPUOrchestratorEngine.ModelSpec", index: int = 0) -> bool:
        """Decide whether there is enough free GPU + host memory to start the model."""
        free_mb = self._free_gpu_memory_mb(index)
        # conservative threshold: require at least 10% of total or a fixed minimum
        required_mb = int((spec.gpu_memory_util * free_mb) if free_mb else 0)
        # also enforce an absolute minimum headroom (200MB)
        headroom_mb = 200
        ok = free_mb - required_mb >= headroom_mb
        self.logger.debug(f"can_start_model: free_mb={free_mb} required_mb={required_mb} ok={ok}")
        return ok

    def start_model(self, spec: "GPUOrchestratorEngine.ModelSpec") -> bool:
        """Start a managed model either via systemd unit or falling back to local vLLM process."""
        self._model_spec = spec
        # Prefer systemd unit if specified
        if spec.service_unit:
            try:
                subprocess.run(["systemctl", "--user", "start", spec.service_unit], check=True)
                self.vllm_status_gauge.set(2)
                self.logger.info(f"Started model service {spec.service_unit}")
                # Start monitor thread
                t = threading.Thread(target=self.monitor_model, args=(spec,), daemon=True)
                t.start()
                return True
            except Exception as e:
                self.logger.warning(f"Failed to start systemd unit {spec.service_unit}: {e}")
        # Fallback: start vllm server via existing helper
        try:
            # set env for the subprocess
            os.environ["VLLM_MODEL"] = spec.id
            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = spec.py_torch_alloc_conf
            os.environ["VLLM_GPU_MEMORY_UTIL"] = str(spec.gpu_memory_util)
            # If adapters were resolved via ModelStore, set VLLM_ADAPTER_PATHS
            if getattr(spec, 'adapter_paths', None):
                os.environ["VLLM_ADAPTER_PATHS"] = ":".join(spec.adapter_paths)
            self._start_vllm_server()
            self.vllm_status_gauge.set(2)
            t = threading.Thread(target=self.monitor_model, args=(spec,), daemon=True)
            t.start()
            return True
        except Exception as e:
            self.logger.error(f"Failed to start vLLM fallback process: {e}")
            self.vllm_status_gauge.set(0)
            return False

    def stop_model(self, spec: "GPUOrchestratorEngine.ModelSpec") -> bool:
        """Stop the managed model gracefully; prefer systemd stop if available."""
        if spec.service_unit:
            try:
                subprocess.run(["systemctl", "--user", "stop", spec.service_unit], check=True)
                self.vllm_status_gauge.set(0)
                return True
            except Exception as e:
                self.logger.warning(f"Failed to stop systemd unit {spec.service_unit}: {e}")
        # Fallback: terminate process if we started it
        try:
            if self._vllm_process:
                self._vllm_process.terminate()
                self._vllm_process.wait(timeout=10)
                self._vllm_process = None
            self.vllm_status_gauge.set(0)
            return True
        except Exception as e:
            self.logger.error(f"Failed to stop vLLM process: {e}")
            return False

    def _detect_oom_in_log(self, log_path: Path) -> bool:
        """Scan log for known CUDA OOM signatures. Returns True if detected."""
        try:
            text = log_path.read_text()
            if "CUDA out of memory" in text or "Tried to allocate" in text or "CUDA error: out of memory" in text:
                return True
        except Exception:
            pass
        return False

    def monitor_model(self, spec: "GPUOrchestratorEngine.ModelSpec") -> None:
        """Monitor model logs and process state; implement OOM detection and restart/backoff."""
        restart_count = 0
        # Use shorter backoffs and polling in lightweight/test mode to make unit tests fast
        backoff_s = 0.1 if not self._bootstrap_external else 1
        max_restarts = 5
        log_path = Path("/home/adra/JustNews/run/vllm_mistral.log")
        poll_interval = 0.1 if not self._bootstrap_external else 5
        self.logger.info("Starting model monitor thread")
        while True:
            try:
                if self._detect_oom_in_log(log_path):
                    self.vllm_oom_counter.inc()
                    restart_count += 1
                    self.logger.warning(f"OOM detected for model {spec.id}; restart_count={restart_count}")
                    if restart_count > max_restarts:
                        self.logger.error("Exceeded max restart attempts; marking model as degraded")
                        self.vllm_status_gauge.set(3)
                        return
                    # stop, sleep backoff, and start again
                    self.stop_model(spec)
                    time.sleep(backoff_s)
                    backoff_s = min(backoff_s * 2, 300)
                    self.vllm_restart_counter.inc()
                    self.start_model(spec)
                time.sleep(poll_interval)
            except Exception as e:
                self.logger.error(f"Error in model monitor loop: {e}")
                time.sleep(poll_interval)

    def _start_vllm_server(self) -> None:
        """Start VLLM inference server for Mistral-7B with LoRA adapter support."""
        # Allow tests and local dev to skip starting an external VLLM server by
        # setting VLLM_SKIP_START=1 in the environment. This avoids launching
        # subprocesses during unit tests and prevents permission/startup errors
        # on machines where vLLM isn't installed.
        if os.environ.get("VLLM_SKIP_START", "0") == "1":
            self.logger.info("Skipping VLLM server start because VLLM_SKIP_START=1")
            return

        if self._vllm_process is not None:
            self.logger.warning("VLLM server already running")
            return

        # Check for existing VLLM processes
        try:
            result = subprocess.run(
                ["pgrep", "-f", "vllm.entrypoints.openai.api_server"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                existing_pids = result.stdout.strip().split("\n")
                self.logger.warning(f"Found existing VLLM processes: {existing_pids}")
                self.logger.info(
                    "Killing existing VLLM processes before starting new one"
                )
                for pid in existing_pids:
                    try:
                        subprocess.run(["kill", "-9", pid], check=False)
                        self.logger.info(f"Killed VLLM process {pid}")
                    except Exception as e:
                        self.logger.warning(f"Failed to kill process {pid}: {e}")
                # Wait for processes to die
                time.sleep(3)
        except Exception as e:
            self.logger.warning(f"Error checking for existing VLLM processes: {e}")

        vllm_model = os.environ.get("VLLM_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")
        vllm_port = int(os.environ.get("VLLM_PORT", "7060"))
        vllm_host = os.environ.get("VLLM_HOST", "127.0.0.1")
        vllm_max_len = int(os.environ.get("VLLM_MAX_MODEL_LEN", "4096"))
        vllm_gpu_util = float(os.environ.get("VLLM_GPU_MEMORY_UTIL", "0.75"))
        vllm_enable_lora = os.environ.get("VLLM_ENABLE_LORA", "true").lower() == "true"

        # Build LoRA module list from MODEL_STORE_ROOT
        lora_modules = []
        if vllm_enable_lora:
            model_store = Path(
                os.environ.get("MODEL_STORE_ROOT", "/home/adra/JustNews/model_store")
            )
            adapter_dirs = [
                "journalist/adapters/mistral_journalist_v1",
                "chief_editor/adapters/mistral_chief_editor_v1",
                "reasoning/adapters/mistral_reasoning_v1",
                "analyst/adapters/mistral_analyst_v1",
                "synthesizer/adapters/mistral_synth_v1",
                "fact_checker/adapters/mistral_fact_checker_v1",
                "critic/adapters/mistral_critic_v1",
            ]
            for adapter_dir in adapter_dirs:
                adapter_path = model_store / adapter_dir
                if adapter_path.exists():
                    adapter_name = adapter_dir.split("/")[
                        -1
                    ]  # e.g., mistral_journalist_v1
                    lora_modules.append(f"{adapter_name}={adapter_path}")

        # Use the same Python that's running this service
        python_bin = os.environ.get("PYTHON_BIN", sys.executable)

        cmd = [
            python_bin,
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--model",
            vllm_model,
            "--host",
            vllm_host,
            "--port",
            str(vllm_port),
            "--max-model-len",
            str(vllm_max_len),
            "--gpu-memory-utilization",
            str(vllm_gpu_util),
            "--disable-log-requests",
            "--trust-remote-code",
        ]

        if vllm_enable_lora and lora_modules:
            cmd.extend(["--enable-lora"])
            for lora_module in lora_modules:
                cmd.extend(["--lora-modules", lora_module])

        self.logger.info(
            f"Starting VLLM server: {vllm_model} on {vllm_host}:{vllm_port}"
        )
        self.logger.info(f"LoRA adapters: {len(lora_modules)} modules")

        # Start VLLM as subprocess
        log_dir = Path(os.environ.get("JUSTNEWS_ROOT", "/home/adra/JustNews")) / "run"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "vllm_mistral_7b.log"

        with open(log_file, "w") as f:
            self._vllm_process = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

        self.logger.info(
            f"VLLM server started with PID {self._vllm_process.pid}, log: {log_file}"
        )

        # Wait a bit for server to start
        time.sleep(5)

        # Check if process is still running
        if self._vllm_process.poll() is not None:
            raise RuntimeError(f"VLLM server failed to start, check {log_file}")

    def _stop_vllm_server(self) -> None:
        """Stop VLLM inference server."""
        if self._vllm_process is None:
            self.logger.info("No VLLM process tracked, checking for orphaned processes")
            # Still check for orphaned VLLM processes
            try:
                result = subprocess.run(
                    ["pgrep", "-f", "vllm.entrypoints.openai.api_server"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    orphaned_pids = result.stdout.strip().split("\n")
                    self.logger.warning(
                        f"Found orphaned VLLM processes: {orphaned_pids}"
                    )
                    for pid in orphaned_pids:
                        try:
                            subprocess.run(["kill", "-15", pid], check=False)
                            self.logger.info(
                                f"Sent SIGTERM to orphaned VLLM process {pid}"
                            )
                        except Exception as e:
                            self.logger.warning(
                                f"Failed to kill orphaned process {pid}: {e}"
                            )
                    time.sleep(2)
                    # Force kill if still alive
                    result = subprocess.run(
                        ["pgrep", "-f", "vllm.entrypoints.openai.api_server"],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        remaining_pids = result.stdout.strip().split("\n")
                        for pid in remaining_pids:
                            try:
                                subprocess.run(["kill", "-9", pid], check=False)
                                self.logger.info(f"Force killed VLLM process {pid}")
                            except Exception as e:
                                self.logger.warning(
                                    f"Failed to force kill process {pid}: {e}"
                                )
            except Exception as e:
                self.logger.warning(f"Error checking for orphaned VLLM processes: {e}")
            return

        self.logger.info(f"Stopping VLLM server (PID {self._vllm_process.pid})")
        try:
            self._vllm_process.terminate()
            self._vllm_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.logger.warning("VLLM server did not terminate, killing")
            self._vllm_process.kill()
            self._vllm_process.wait()
        except Exception as e:
            self.logger.error(f"Error stopping VLLM server: {e}")
        finally:
            self._vllm_process = None

        self.logger.info("VLLM server stopped")

    def cleanup(self) -> None:
        """Cleanup method called on shutdown to ensure VLLM is stopped."""
        if self._vllm_enabled:
            try:
                self.logger.info("GPU Orchestrator cleanup: stopping VLLM server")
                self._stop_vllm_server()
            except Exception as e:
                self.logger.error(f"Error during cleanup: {e}")

    def get_vllm_status(self) -> dict[str, Any]:
        """Get VLLM server status."""
        if not self._vllm_enabled:
            return {"enabled": False, "running": False}

        running = self._vllm_process is not None and self._vllm_process.poll() is None
        pid = self._vllm_process.pid if self._vllm_process else None

        # Try to check endpoint health
        vllm_url = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:7060/v1")
        healthy = False
        if running:
            try:
                import requests

                response = requests.get(
                    f"{vllm_url.replace('/v1', '')}/health", timeout=2
                )
                healthy = response.status_code == 200
            except Exception:
                pass

        return {
            "enabled": self._vllm_enabled,
            "running": running,
            "healthy": healthy,
            "pid": pid,
            "endpoint": vllm_url,
        }

    def _run_nvidia_smi(self) -> str | None:
        """Run nvidia-smi and return CSV output."""
        cmd = [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits",
        ]
        try:
            output = subprocess.check_output(
                cmd, stderr=subprocess.STDOUT, text=True, timeout=3
            )
            return output
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ) as e:
            self.logger.debug(f"nvidia-smi unavailable or failed: {e}")
            return None

    def _parse_nvidia_smi_csv(self, csv_text: str) -> list[dict[str, Any]]:
        """Parse nvidia-smi CSV output into GPU info dicts."""
        gpus: list[dict[str, Any]] = []
        for line in csv_text.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 7:
                continue
            try:
                gpus.append(
                    {
                        "index": int(parts[0]),
                        "name": parts[1],
                        "memory_total_mb": float(parts[2]),
                        "memory_used_mb": float(parts[3]),
                        "utilization_gpu_pct": float(parts[4]),
                        "temperature_c": float(parts[5]),
                        "power_draw_w": float(parts[6]),
                        "memory_utilization_pct": (
                            (float(parts[3]) / float(parts[2]) * 100.0)
                            if float(parts[2]) > 0
                            else 0.0
                        ),
                    }
                )
            except ValueError:
                continue
        return gpus

    def _get_nvml_enrichment(self, gpus: list[dict[str, Any]]) -> None:
        """Enrich GPU info with NVML data."""
        if not ENABLE_NVML or SAFE_MODE or not _NVML_SUPPORTED or not _HAS_PYNVML:
            return

        try:
            for g in gpus:
                idx = g.get("index")
                if idx is not None:
                    try:
                        handle = self.get_nvml_handle(idx)
                        if handle:
                            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                            g["nvml_gpu_util_pct"] = getattr(util, "gpu", None)
                            g["nvml_mem_used_mb"] = round(mem.used / 1024**2, 2)
                            g["nvml_mem_total_mb"] = round(mem.total / 1024**2, 2)
                            g["nvml_mem_util_pct"] = round(
                                (mem.used / mem.total * 100.0) if mem.total else 0.0, 2
                            )
                    except Exception as e:
                        g["nvml_error"] = str(e)
        except Exception as e:
            self.logger.warning(f"NVML enrichment error: {e}")

    def get_gpu_snapshot(self) -> dict[str, Any]:
        """Return a conservative, read-only snapshot of GPU state."""
        smi = self._run_nvidia_smi()
        if smi is None:
            return {
                "gpus": [],
                "available": False,
                "message": "nvidia-smi not available",
            }

        gpus = self._parse_nvidia_smi_csv(smi)
        self._get_nvml_enrichment(gpus)

        return {
            "gpus": gpus,
            "available": True,
            "nvml_enriched": bool(ENABLE_NVML and not SAFE_MODE and _NVML_SUPPORTED),
            "nvml_supported": _NVML_SUPPORTED,
        }

    def _detect_mps(self) -> dict[str, Any]:
        """Detect NVIDIA MPS status."""
        pipe_dir = os.environ.get("CUDA_MPS_PIPE_DIRECTORY", "/tmp/nvidia-mps")
        control_process = False
        enabled = False

        try:
            out = subprocess.run(
                ["pgrep", "-x", "nvidia-cuda-mps-control"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1,
            )
            control_process = out.returncode == 0
        except Exception:
            control_process = False

        try:
            if pipe_dir and os.path.exists(pipe_dir):
                enabled = True
        except Exception:
            enabled = False

        enabled = enabled or control_process
        return {
            "enabled": bool(enabled),
            "pipe_dir": pipe_dir,
            "control_process": bool(control_process),
        }

    def get_comprehensive_gpu_info(self) -> dict[str, Any]:
        """Get comprehensive GPU information including MPS status."""
        data = self.get_gpu_snapshot()
        mps = self._detect_mps()
        data["mps_enabled"] = bool(mps.get("enabled", False))
        data["mps"] = mps

        # Update MPS metrics
        self.mps_enabled_gauge.labels(
            agent=self.metrics.agent_name, agent_display_name=self.metrics.display_name
        ).set(1 if data["mps_enabled"] else 0)

        return data

    def _purge_expired_leases(self) -> None:
        """Remove expired GPU leases."""
        now = time.time()
        expired = []
        for token, alloc in ALLOCATIONS.items():
            if now - alloc.get("timestamp", 0) > 3600:  # 1 hour TTL
                expired.append(token)

        for token in expired:
            ALLOCATIONS.pop(token, None)

        if expired:
            self.lease_expired_counter.labels(
                agent=self.metrics.agent_name,
                agent_display_name=self.metrics.display_name,
            ).inc(len(expired))

        # Also purge expired leases from persistent DB (best-effort)
        try:
            if self.db_service:
                cursor, conn = self._get_safe_cursor(per_call=True, buffered=True)
                try:
                    cursor.execute(
                        "DELETE FROM orchestrator_leases WHERE expires_at IS NOT NULL AND expires_at < NOW()"
                    )
                    conn.commit()
                finally:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass
        except Exception:
            # Non-fatal - leave in-memory cleanup as primary
            self.logger.debug("Failed to purge expired leases from DB (continuing)")

    def _validate_lease_request(self, req: dict[str, Any]) -> str | None:
        """Validate lease request parameters."""
        if req.get("min_memory_mb") is not None and req["min_memory_mb"] < 0:
            return "min_memory_mb must be >= 0"
        return None

    def _allocate_gpu(self, req: dict[str, Any]) -> tuple[bool, int | None]:
        """Allocate GPU based on request."""
        snapshot = self.get_gpu_snapshot()
        if not snapshot.get("available") or not snapshot.get("gpus"):
            return False, None

        candidates = []
        for g in snapshot["gpus"]:
            if (
                req.get("min_memory_mb")
                and (g["memory_total_mb"] - g["memory_used_mb"]) < req["min_memory_mb"]
            ):
                continue
            candidates.append(g)

        if candidates:
            return True, sorted(candidates, key=lambda x: x["memory_used_mb"])[0][
                "index"
            ]
        return False, None

    def lease_gpu(self, agent: str, min_memory_mb: int | None = 0) -> dict[str, Any]:
        """Obtain a GPU lease."""
        self._purge_expired_leases()

        if SAFE_MODE:
            return {"granted": False, "note": "SAFE_MODE", "agent": agent}

        req = {"agent": agent, "min_memory_mb": min_memory_mb}
        err = self._validate_lease_request(req)
        if err:
            raise HTTPException(status_code=400, detail=err)

        success, gpu_index = self._allocate_gpu(req)
        token = str(uuid.uuid4())
        allocation = {
            "agent": agent,
            "gpu": gpu_index if success else "cpu",
            "token": token,
            "timestamp": time.time(),
        }
        ALLOCATIONS[token] = allocation
        # Persist lease to DB (best-effort) with a default TTL (1h)
        try:
            if self.db_service:
                ttl = int(os.environ.get("GPU_ORCHESTRATOR_LEASE_TTL", "3600"))
                cursor, conn = self._get_safe_cursor(per_call=True, buffered=True)
                # Use FROM_UNIXTIME for created_at handling where helpful, but simple NOW()/DATE_ADD is fine
                try:
                    cursor.execute(
                        "INSERT INTO orchestrator_leases (token, agent_name, gpu_index, mode, created_at, expires_at, last_heartbeat, metadata) VALUES (%s,%s,%s,%s,NOW(),DATE_ADD(NOW(), INTERVAL %s SECOND),NOW(),%s)",
                        (
                            token,
                            agent,
                            gpu_index if success else None,
                            "gpu" if success else "cpu",
                            ttl,
                            json.dumps(allocation),
                        ),
                    )
                    conn.commit()
                finally:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass
        except Exception as e:
            self.logger.debug(f"Failed to persist lease to DB (non-fatal): {e}")
        return {"granted": True, **allocation}

    def claim_job_and_lease(
        self, job_id: str, agent: str, min_memory_mb: int | None = 0
    ) -> dict[str, Any]:
        """Atomically mark a job as claimed and create a GPU lease in the DB.

        This method uses a DB transaction and SELECT ... FOR UPDATE semantics to
        avoid races between multiple consumers trying to claim the same job.

        Returns a dict: {claimed: bool, reason: str? , token: str?, allocation: dict?}
        """
        if SAFE_MODE:
            return {"claimed": False, "reason": "SAFE_MODE"}

        if not getattr(self, "db_service", None):
            # Fall back to non-transactional path if no DB available
            # mark the job claimed (best-effort) and obtain a lease using existing method
            try:
                cursor = None
                if self.db_service:
                    cursor, conn = self._get_safe_cursor(per_call=True, buffered=True)
                    try:
                        cursor.execute(
                            "SELECT status FROM orchestrator_jobs WHERE job_id=%s",
                            (job_id,),
                        )
                        r = cursor.fetchone()
                    finally:
                        try:
                            cursor.close()
                        except Exception:
                            pass
                        try:
                            if conn:
                                conn.close()
                        except Exception:
                            pass
                    if not r or r[0] != "pending":
                        return {
                            "claimed": False,
                            "reason": "not_pending_or_missing",
                            "status": (r[0] if r else None),
                        }
                # Proceed with updating and leasing best-effort
                if self.db_service:
                    cursor, conn = self._get_safe_cursor(per_call=True, buffered=True)
                    try:
                        cursor.execute(
                            "UPDATE orchestrator_jobs SET status=%s, updated_at=NOW() WHERE job_id=%s",
                            ("claimed", job_id),
                        )
                        conn.commit()
                    finally:
                        try:
                            cursor.close()
                        except Exception:
                            pass
                        try:
                            conn.close()
                        except Exception:
                            pass
            except Exception:
                # Best effort — continue to attempt a lease and return accordingly
                pass

            lease = self.lease_gpu(agent, min_memory_mb)
            if lease.get("granted"):
                return {
                    "claimed": True,
                    "token": lease.get("token"),
                    "allocation": lease,
                }
            return {"claimed": False, "reason": "lease_failed"}

        # DB backed path: do SELECT FOR UPDATE and perform update + insert within a single transaction
        # use a dedicated per-call connection for the transactional path
        # Prefer using a test-provided mb_conn (common in unit tests) if present; fall back to get_connection()
        conn = getattr(self.db_service, "mb_conn", None)
        if conn is None and callable(getattr(self.db_service, "get_connection", None)):
            try:
                conn = self.db_service.get_connection()
            except Exception:
                conn = None
        try:
            cursor = conn.cursor()
            # begin transaction
            # Use a portable BEGIN TRANSACTION which works for MySQL and SQLite
            cursor.execute("BEGIN")

            try:
                # Try SELECT ... FOR UPDATE first — this is the preferred, transactional
                # approach on databases that support it.
                cursor.execute(
                    "SELECT status FROM orchestrator_jobs WHERE job_id=%s FOR UPDATE",
                    (job_id,),
                )
                r = cursor.fetchone()
                if not r:
                    cursor.execute("ROLLBACK")
                    cursor.close()
                    return {"claimed": False, "reason": "not_found"}

                status = r[0]
                if status != "pending":
                    cursor.execute("ROLLBACK")
                    cursor.close()
                    return {"claimed": False, "reason": "not_pending", "status": status}
            except Exception:
                # Some DB backends (notably sqlite in our tests) don't support SELECT ... FOR UPDATE.
                # Fall back to an optimistic UPDATE that only claims if the status was pending.
                try:
                    upd_cur = conn.cursor()
                    upd_cur.execute(
                        "UPDATE orchestrator_jobs SET status=%s, updated_at=NOW() WHERE job_id=%s AND status=%s",
                        ("claimed", job_id, "pending"),
                    )
                    rowcount = getattr(upd_cur, "rowcount", None)
                    upd_cur.close()

                    if rowcount is not None and rowcount == 0:
                        cursor.execute("ROLLBACK")
                        cursor.close()
                        return {"claimed": False, "reason": "not_pending"}
                    # else assume we updated successfully and continue
                except Exception as e:
                    try:
                        cursor.execute("ROLLBACK")
                    except Exception:
                        pass
                    cursor.close()
                    return {"claimed": False, "reason": "not_locked", "error": str(e)}

            # mark job claimed
            cursor.execute(
                "UPDATE orchestrator_jobs SET status=%s, updated_at=NOW() WHERE job_id=%s",
                ("claimed", job_id),
            )

            # allocate a GPU SYNTHETICALLY (call internal allocator that doesn't touch DB)
            success, gpu_index = self._allocate_gpu({"min_memory_mb": min_memory_mb})
            token = str(uuid.uuid4())
            ttl = int(os.environ.get("GPU_ORCHESTRATOR_LEASE_TTL", "3600"))
            allocation = {
                "agent": agent,
                "gpu": gpu_index if success else "cpu",
                "token": token,
                "timestamp": time.time(),
            }

            # persist lease row (co-located in same transaction)
            # Compute created_at / expires_at in Python for DB portability (works on MySQL & SQLite)
            from datetime import datetime, timedelta

            created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            expires_at = (datetime.now(UTC) + timedelta(seconds=ttl)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            cursor.execute(
                "INSERT INTO orchestrator_leases (token, agent_name, gpu_index, mode, created_at, expires_at, last_heartbeat, metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    token,
                    agent,
                    gpu_index if success else None,
                    "gpu" if success else "cpu",
                    created_at,
                    expires_at,
                    created_at,
                    json.dumps(allocation),
                ),
            )

            # commit transaction
            conn.commit()
            cursor.close()
            try:
                conn.close()
            except Exception:
                pass

            # update in-memory allocations
            ALLOCATIONS[token] = allocation

            return {"claimed": True, "token": token, "allocation": allocation}
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                cursor.close()
            except Exception:
                pass
            self.logger.debug(f"claim_job_and_lease failed: {e}")
            return {"claimed": False, "reason": "internal_error", "error": str(e)}

    def release_gpu_lease(self, token: str) -> dict[str, Any]:
        """Release a GPU lease."""
        self._purge_expired_leases()
        alloc = ALLOCATIONS.pop(token, None)
        if not alloc:
            raise HTTPException(status_code=404, detail="unknown_token")
        # Also remove persistent lease row (best-effort)
        try:
            if self.db_service:
                cursor, conn = self._get_safe_cursor(per_call=True, buffered=True)
                try:
                    cursor.execute(
                        "DELETE FROM orchestrator_leases WHERE token = %s", (token,)
                    )
                    conn.commit()
                finally:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass
        except Exception:
            self.logger.debug("Failed to remove lease row from DB (non-fatal)")
        return {"released": True, "token": token}

    def heartbeat_lease(self, token: str) -> bool:
        """Update last_heartbeat for lease token in DB (best-effort)."""
        try:
            # Update in-memory timestamp if present
            if token in ALLOCATIONS:
                ALLOCATIONS[token]["timestamp"] = time.time()
            if self.db_service:
                cursor, conn = self._get_safe_cursor(per_call=True, buffered=True)
                try:
                    cursor.execute(
                        "UPDATE orchestrator_leases SET last_heartbeat = NOW() WHERE token = %s",
                        (token,),
                    )
                    conn.commit()
                finally:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass
            return True
        except Exception as e:
            self.logger.debug(f"Failed to heartbeat lease in DB: {e}")
            return False

    def get_allocations(self) -> dict[str, Any]:
        """Get current allocations."""
        self._purge_expired_leases()
        return {"allocations": ALLOCATIONS}

    def update_policy(self, update: dict[str, Any]) -> dict[str, Any]:
        """Update GPU policy."""
        if SAFE_MODE:
            return {
                **POLICY,
                "note": "SAFE_MODE enabled: policy updates accepted but not enacted",
            }

        changed = False
        if "max_memory_per_agent_mb" in update:
            POLICY["max_memory_per_agent_mb"] = int(update["max_memory_per_agent_mb"])
            changed = True
        if "allow_fractional_shares" in update:
            POLICY["allow_fractional_shares"] = bool(update["allow_fractional_shares"])
            changed = True
        if "kill_on_oom" in update:
            POLICY["kill_on_oom"] = bool(update["kill_on_oom"])
            changed = True

        if changed:
            self.logger.info(f"Updated GPU policy: {POLICY}")
        return POLICY

    # Default pool lifecycle policy values (configurable via env or API)
    def _pool_policy_defaults(self):
        # Merge defaults from system configuration if available
        defaults = {
            "min_warm_workers_per_pool": int(os.environ.get("GPU_POOL_MIN_WARM", "0")),
            "max_total_workers": int(os.environ.get("GPU_POOL_MAX_TOTAL", "8")),
            "pool_idle_timeout_s": int(
                os.environ.get("GPU_POOL_IDLE_TIMEOUT_S", "300")
            ),
            "enforce_period_s": int(os.environ.get("GPU_POOL_POLICY_PERIOD_S", "10")),
        }
        try:
            # runtime import of config module so tests can monkeypatch
            from config.core import get_gpu_config

            gconf = get_gpu_config()
            if gconf:
                defaults["min_warm_workers_per_pool"] = gconf.get(
                    "min_warm_workers_per_pool", defaults["min_warm_workers_per_pool"]
                )
                defaults["max_total_workers"] = gconf.get(
                    "max_total_workers", defaults["max_total_workers"]
                )
                defaults["pool_idle_timeout_s"] = gconf.get(
                    "pool_idle_timeout_s", defaults["pool_idle_timeout_s"]
                )
                defaults["enforce_period_s"] = gconf.get(
                    "enforce_period_s", defaults["enforce_period_s"]
                )
        except Exception:
            pass
        return defaults

    def get_pool_policy(self) -> dict[str, Any]:
        if not hasattr(self, "_POOL_POLICY"):
            self._POOL_POLICY = self._pool_policy_defaults()
        return self._POOL_POLICY

    def set_pool_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        cur = self.get_pool_policy()
        cur.update(policy)
        self._POOL_POLICY = cur
        # Trigger immediate enforcement so policy changes take effect promptly
        try:
            self._enforce_pool_policy_once()
        except Exception:
            pass

        # Audit policy change immediately so tests and operators can inspect
        # policy updates even when the API route isn't used.
        try:
            self._audit_policy_event("policy_update", policy)
        except Exception:
            self.logger.debug("Failed to audit pool policy update")

        return self._POOL_POLICY

    def _enforce_pool_policy_once(self) -> None:
        """Perform one enforcement pass (evict pools if over configured limits).

        This is a synchronous variant used to trigger immediate enforcement after
        policy updates or during tests/ops where waiting for the background
        enforcer is undesirable.
        """
        try:
            policy = self.get_pool_policy()
            total = sum(p.get("num_workers", 0) for p in self._WORKER_POOLS.values())
            max_total = policy.get("max_total_workers", 8)

            if total > max_total:
                ordered = sorted(
                    self._WORKER_POOLS.items(),
                    key=lambda kv: kv[1].get("started_at", 0),
                )
                for pool_id, meta in ordered:
                    if total <= max_total:
                        break
                    try:
                        self.stop_worker_pool(pool_id)
                        total -= meta.get("num_workers", 0)
                        self.worker_pool_evictions_counter.labels(
                            reason="over_total_sync"
                        ).inc()
                    except Exception:
                        pass

                if total > max_total:
                    for pool_id, meta in ordered:
                        if total <= max_total:
                            break
                        try:
                            self.stop_worker_pool(pool_id)
                            total -= meta.get("num_workers", 0)
                            self.worker_pool_evictions_counter.labels(
                                reason="over_total_force_sync"
                            ).inc()
                        except Exception:
                            pass
        except Exception:
            pass

    def _background_policy_enforcer(self):
        """Background thread that enforces pool lifecycle policies periodically."""
        while True:
            try:
                # Only the leader should actively enforce pool lifecycle policies.
                if not getattr(self, "is_leader", False):
                    # still update metrics snapshot but skip enforcement
                    self.worker_pools_gauge.labels(
                        agent=self.metrics.agent_name,
                        agent_display_name=self.metrics.display_name,
                    ).set(len(self._WORKER_POOLS))
                    time.sleep(self.get_pool_policy().get("enforce_period_s", 10))
                    continue

                policy = self.get_pool_policy()
                self.logger.debug(f"Policy enforcer tick: policy={policy}")
                # Compute total configured workers
                total = sum(
                    p.get("num_workers", 0) for p in self._WORKER_POOLS.values()
                )
                self.logger.debug(
                    f"Policy enforcer tick: current_total_workers={total}, pools={list(self._WORKER_POOLS.keys())}"
                )
                max_total = policy.get("max_total_workers", 8)

                # Evict least-recently used pools if over max_total
                if total > max_total:
                    # sort by started_at ascending
                    ordered = sorted(
                        self._WORKER_POOLS.items(),
                        key=lambda kv: kv[1].get("started_at", 0),
                    )
                    evicted = 0
                    for pool_id, meta in ordered:
                        if total <= max_total:
                            break
                        # skip pools with min_warm requirement
                        min_warm = policy.get("min_warm_workers_per_pool", 0)
                        if meta.get("num_workers", 0) <= min_warm:
                            continue
                        # evict whole pool
                        try:
                            self.logger.info(
                                f"Evicting worker pool {pool_id} to reduce total workers"
                            )
                            self.stop_worker_pool(pool_id)
                            total -= meta.get("num_workers", 0)
                            evicted += 1
                            self.worker_pool_evictions_counter.labels(
                                reason="over_total"
                            ).inc()
                        except Exception:
                            pass

                    # Fallback: if total still above threshold, evict pools regardless of min_warm to make progress
                    if total > max_total:
                        for pool_id, meta in ordered:
                            if total <= max_total:
                                break
                            try:
                                self.logger.info(
                                    f"Force-evicting worker pool {pool_id} to enforce limit"
                                )
                                self.stop_worker_pool(pool_id)
                                total -= meta.get("num_workers", 0)
                                self.worker_pool_evictions_counter.labels(
                                    reason="over_total_force"
                                ).inc()
                            except Exception:
                                pass

                # Evict pools that have been idle longer than pool_idle_timeout_s
                now = time.time()
                idle_timeout = policy.get("pool_idle_timeout_s", 300)
                for pool_id, meta in list(self._WORKER_POOLS.items()):
                    started = meta.get("started_at", now)
                    running = sum(1 for p in meta.get("procs", []) if p.is_alive())
                    # if no running workers and older than timeout, evict
                    if running == 0 and (now - started) > idle_timeout:
                        try:
                            self.stop_worker_pool(pool_id)
                            self.worker_pool_evictions_counter.labels(
                                reason="idle_timeout"
                            ).inc()
                        except Exception:
                            pass

                # update metrics per pool
                self.worker_pools_gauge.labels(
                    agent=self.metrics.agent_name,
                    agent_display_name=self.metrics.display_name,
                ).set(len(self._WORKER_POOLS))
                for pid, meta in self._WORKER_POOLS.items():
                    self.worker_pool_workers_gauge.labels(pool_id=pid).set(
                        meta.get("num_workers", 0)
                    )
                    running = sum(1 for p in meta.get("procs", []) if p.is_alive())
                    self.worker_pool_running_workers_gauge.labels(pool_id=pid).set(
                        running
                    )
                    if meta.get("started_at"):
                        self.worker_pool_started_timestamp.labels(pool_id=pid).set(
                            meta.get("started_at")
                        )

                # Update stream metrics
                self._update_stream_metrics()

                # Run autoscaling logic
                self._run_autoscaler()

            except Exception:
                pass

            # Sleep until next enforcement
            period = self.get_pool_policy().get("enforce_period_s", 10)
            time.sleep(period)

    def try_acquire_leader_lock(self, timeout: int | None = None) -> bool:
        """Attempt to acquire a MariaDB GET_LOCK for leader role.

        Returns True if lock acquired and False otherwise.
        This uses a dedicated connection stored in `self._leader_conn` to ensure
        the lock persists for the lifetime of the leadership.
        """
        if not self.db_service:
            return False
        try:
            if timeout is None:
                timeout = self._leader_try_timeout

            # Reuse existing connection if healthy
            conn = getattr(self, '_leader_conn', None)
            if conn:
                try:
                    # Do not reconnect automatically; we want to know if it dropped
                    conn.ping(reconnect=False)
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = None
            
            if not conn:
                # Create new dedicated connection
                _, conn = self._get_safe_cursor(per_call=True, buffered=True)
                _.close() # We only need the connection object
                self._leader_conn = conn
            
            cursor = self._leader_conn.cursor()
            try:
                cursor.execute(
                    "SELECT GET_LOCK(%s,%s)", (self._leader_lock_name, int(timeout))
                )
                res = cursor.fetchone()
            finally:
                try:
                    cursor.close()
                except Exception:
                    pass
                # Do NOT close conn; we must hold it to keep the lock
            
            locked = bool(res and int(res[0]) == 1)
            if locked:
                self.is_leader = True
                self.logger.info("Acquired leader lock")
            return locked
        except Exception as e:
            self.logger.debug(f"Leader lock attempt failed: {e}")
            # On error, clean up connection
            conn = getattr(self, '_leader_conn', None)
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
                self._leader_conn = None
            return False

    def release_leader_lock(self) -> bool:
        """Release the MariaDB GET_LOCK if held.

        Returns True if the lock was released, False on failure.
        """
        if not self.db_service:
            return False
            
        conn = getattr(self, '_leader_conn', None)
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (self._leader_lock_name,))
                res = cursor.fetchone()
            finally:
                try:
                    cursor.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass
                self._leader_conn = None

            released = bool(res and res[0] == 1)
            if released:
                self.is_leader = False
                self.logger.info("Released leader lock")
            return released
        except Exception as e:
            self.logger.debug(f"Failed to release leader lock: {e}")
            return False

    def _leader_election_loop(self):
        """Background loop that acquires leadership when possible and yields when lost."""
        # Small startup pause to avoid immediate DB probes racing with synchronous
        # test actions in unit tests that expect to control cursor call sequencing.
        # This gives the main thread a short window to run synchronous operations
        # before the background election loop starts probing the DB.
        try:
            # Give a larger window to let synchronous unit tests run before
            # the background election loop probes the DB. This reduces flakiness
            # in tests that control cursor call sequencing.
            time.sleep(
                float(os.environ.get("GPU_ORCHESTRATOR_LEADER_START_DELAY_S", "0.5"))
            )
        except Exception:
            pass
        # If we don't have a DB connection, do nothing.
        while True:
            try:
                if not getattr(self, "is_leader", False):
                    got = self.try_acquire_leader_lock(timeout=self._leader_try_timeout)
                    if got:
                        # When becoming leader, reconcile state immediately (best-effort)
                        try:
                            self._rehydrate_worker_pools_from_db()
                        except Exception:
                            pass
                else:
                    # we are leader; verify connection still healthy (best-effort)
                    try:
                        # Check the actual leader connection, not a new one
                        if (
                            not hasattr(self, "_leader_conn")
                            or self._leader_conn is None
                        ):
                            raise Exception("No leader connection found")

                        # Use the raw connection to ping
                        # This verifies the session holding the lock is still alive
                        self._leader_conn.ping(reconnect=False, attempts=1, delay=0)
                    except Exception:
                        # lost DB connection -> lose leadership
                        self.logger.warning(
                            "Leader DB connection lost, relinquishing leadership"
                        )
                        self.release_leader_lock()
                        self.is_leader = False
                time.sleep(int(os.environ.get("GPU_ORCHESTRATOR_LEADER_LOOP_S", "2")))
            except Exception:
                # don't crash the loop
                time.sleep(2)

    def get_policy(self) -> dict[str, Any]:
        """Get current policy."""
        return POLICY

    # Model preloading functionality
    def _project_root(self) -> str:
        """Get project root directory."""
        try:
            return str(Path(__file__).resolve().parents[2])
        except Exception:
            return os.getcwd()

    def _read_agent_model_map(self) -> dict[str, Any]:
        """Read agent model map from JSON file."""
        try:
            project_root = Path(self._project_root())
            model_map_path = project_root / "AGENT_MODEL_MAP.json"

            if not model_map_path.exists():
                self.logger.warning(f"Model map file not found: {model_map_path}")
                return {}

            import json

            with open(model_map_path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            # Legacy structure: treat as agents dict
            return {"agents": data}
        except Exception as e:
            self.logger.error(f"Failed to read agent model map: {e}")
            return {}

    def _agents_section(self, model_map: dict[str, Any]) -> dict[str, Any]:
        agents_cfg = model_map.get("agents")
        if agents_cfg is not None and isinstance(agents_cfg, dict):
            return agents_cfg
        # Legacy fallback: treat top-level keys as agents except metadata keys
        legacy = {}
        for key, value in model_map.items():
            if key == "base_models":
                continue
            legacy[key] = value
        return legacy

    def _normalize_agent_entries(
        self, model_map: dict[str, Any], agent: str
    ) -> list[dict[str, Any]]:
        agents_cfg = self._agents_section(model_map)
        raw_entries = agents_cfg.get(agent, [])
        if not isinstance(raw_entries, list):
            raw_entries = [raw_entries]
        normalized: list[dict[str, Any]] = []
        for idx, item in enumerate(raw_entries):
            if isinstance(item, dict):
                spec = dict(item)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                spec = {
                    "type": item[0],
                    "legacy_model_id": item[1],
                }
            else:
                spec = {"legacy_model_id": item}
            spec.setdefault(
                "id",
                spec.get("adapter_name")
                or spec.get("legacy_model_id")
                or f"{agent}-{idx}",
            )
            normalized.append(spec)
        return normalized

    def _validate_and_load_model(
        self, agent: str, spec: dict[str, Any], strict: bool
    ) -> tuple[bool, str | None]:
        """Validate and load a model entry for an agent."""
        try:
            # If VLLM is enabled and this is an adapter-based model, just verify adapter exists
            if self._vllm_enabled and spec.get("base_ref"):
                adapter_name = spec.get("adapter_name")
                adapter_path_str = spec.get("adapter_model_store_path")

                if adapter_path_str:
                    model_store = Path(
                        os.environ.get(
                            "MODEL_STORE_ROOT", "/home/adra/JustNews/model_store"
                        )
                    )
                    adapter_path = model_store / adapter_path_str

                    if adapter_path.exists():
                        self.logger.info(
                            "VLLM mode: Verified adapter exists for agent %s (adapter=%s)",
                            agent,
                            adapter_name,
                        )
                        return True, None
                    else:
                        if strict:
                            raise FileNotFoundError(
                                f"Adapter not found at {adapter_path}"
                            )
                        else:
                            self.logger.warning(
                                f"Adapter not found at {adapter_path}, continuing in non-strict mode"
                            )
                            return True, None

                # Fallback: just mark as valid since VLLM will handle it
                self.logger.info(
                    f"VLLM mode: Skipping full model load for agent {agent}"
                )
                return True, None

            if spec.get("base_ref"):
                from agents.common.model_loader import load_transformers_with_adapter

                adapter_name = spec.get("adapter_name")
                self.logger.info(
                    "Validating base model + adapter for agent %s (adapter=%s, strict=%s)",
                    agent,
                    adapter_name or spec.get("base_ref"),
                    strict,
                )
                load_transformers_with_adapter(agent, adapter_name=adapter_name)
                return True, None

            legacy_model_id = spec.get("legacy_model_id") or spec.get("model_id")
            if not legacy_model_id:
                raise ValueError("AGENT_MODEL_MAP entry is missing a model identifier")

            model_type = spec.get("type")
            if not model_type:
                model_type = (
                    "sentence-transformers"
                    if str(legacy_model_id).startswith("sentence-transformers/")
                    else "transformers"
                )

            self.logger.info(
                "Validating and loading model %s (type=%s) for agent %s (strict=%s)",
                legacy_model_id,
                model_type,
                agent,
                strict,
            )
            if model_type == "sentence-transformers":
                from agents.common.model_loader import load_sentence_transformer

                load_sentence_transformer(legacy_model_id, agent=agent)
            else:
                from agents.common.model_loader import load_transformers_model

                load_transformers_model(legacy_model_id, agent=agent)
            return True, None
        except Exception as e:
            self.logger.error(
                f"Error validating/loading model entry for agent {agent}: {e}"
            )
            return False, str(e)

    def _preload_worker(
        self, selected_agents: list[str] | None, strict_override: bool | None
    ) -> None:
        """Background worker for model preloading."""
        try:
            model_map = self._read_agent_model_map()
            agents_cfg = self._agents_section(model_map)
            agents = selected_agents or list(agents_cfg.keys())

            agent_specs: dict[str, list[dict[str, Any]]] = {}
            for agent in agents:
                specs = self._normalize_agent_entries(model_map, agent)
                # Attach manifest/metadata for new-format entries (best-effort)
                enriched_specs: list[dict[str, Any]] = []
                for spec in specs:
                    if spec.get("base_ref"):
                        try:
                            from agents.common.model_loader import (
                                get_agent_model_metadata,
                            )

                            meta = get_agent_model_metadata(
                                agent, spec.get("adapter_name")
                            )
                            if meta:
                                spec = {**spec, "_model_metadata": meta}
                                variant = self._select_variant_for_spec(spec)
                                if variant:
                                    spec["_selected_variant"] = variant
                                    spec["_variant_vram_mb"] = self._variant_vram_mb(
                                        spec, variant
                                    )
                        except Exception as exc:
                            self.logger.debug(
                                "Failed to collect model metadata for agent=%s: %s",
                                agent,
                                exc,
                            )
                    enriched_specs.append(spec)
                agent_specs[agent] = enriched_specs

            # Initialize status entries
            for a in agents:
                models = agent_specs.get(a, [])
                _MODEL_PRELOAD_STATE["per_agent"][a] = {}
                for spec in models:
                    entry_id = spec.get("id")
                    _MODEL_PRELOAD_STATE["per_agent"][a][entry_id] = {
                        "status": "pending",
                        "error": None,
                        "duration_s": None,
                        "variant": spec.get("_selected_variant"),
                        "approx_vram_mb": spec.get("_variant_vram_mb"),
                    }

            total = sum(len(agent_specs.get(a, [])) for a in agents)
            _MODEL_PRELOAD_STATE["summary"]["total"] = total

            strict_env = os.environ.get("STRICT_MODEL_STORE", "0").lower() in (
                "1",
                "true",
                "yes",
            )
            strict = strict_override if strict_override is not None else strict_env

            # Preload models
            for a in agents:
                for spec in agent_specs.get(a, []):
                    entry_id = spec.get("id")
                    st = _MODEL_PRELOAD_STATE["per_agent"][a][entry_id]
                    st["status"] = "loading"
                    t0 = time.time()
                    ok, err = self._validate_and_load_model(a, spec, strict)
                    if ok:
                        st["status"] = "ok"
                        st["duration_s"] = time.time() - t0
                        _MODEL_PRELOAD_STATE["summary"]["done"] += 1
                    else:
                        st["status"] = "error"
                        st["error"] = err
                        st["duration_s"] = time.time() - t0
                        _MODEL_PRELOAD_STATE["summary"]["failed"] += 1

        except Exception as e:
            self.logger.error(f"Model preload worker crashed: {e}")
        finally:
            _MODEL_PRELOAD_STATE["in_progress"] = False
            _MODEL_PRELOAD_STATE["completed_at"] = time.time()

    def start_model_preload(
        self,
        agents: list[str] | None = None,
        refresh: bool = False,
        strict: bool | None = None,
    ) -> dict[str, Any]:
        """Start model preload job."""
        # Check if job already completed and not refreshing
        if (
            _MODEL_PRELOAD_STATE.get("started_at")
            and not _MODEL_PRELOAD_STATE.get("in_progress")
            and not refresh
        ):
            failed = _MODEL_PRELOAD_STATE.get("summary", {}).get("failed", 0)
            all_ready = failed == 0 and _MODEL_PRELOAD_STATE["summary"].get(
                "done", 0
            ) == _MODEL_PRELOAD_STATE["summary"].get("total", 0)

            state = {**_MODEL_PRELOAD_STATE, "all_ready": all_ready}

            # Build error list
            errors = []
            for a, models in _MODEL_PRELOAD_STATE.get("per_agent", {}).items():
                for mid, st in models.items():
                    if st.get("status") == "error":
                        errors.append(
                            {"agent": a, "model": mid, "error": st.get("error")}
                        )
            state["errors"] = errors

            if failed > 0:
                raise HTTPException(status_code=503, detail=state)
            return state

        # Start new preload job
        _MODEL_PRELOAD_STATE["started_at"] = time.time()
        _MODEL_PRELOAD_STATE["in_progress"] = True
        _MODEL_PRELOAD_STATE["completed_at"] = None

        # Reset summary for new job
        _MODEL_PRELOAD_STATE["summary"] = {"total": 0, "done": 0, "failed": 0}

        thread = threading.Thread(
            target=self._preload_worker, args=(agents, strict), daemon=True
        )
        thread.start()

        return {**_MODEL_PRELOAD_STATE, "all_ready": False}

    def get_model_preload_status(self) -> dict[str, Any]:
        """Get model preload status."""
        failed = _MODEL_PRELOAD_STATE.get("summary", {}).get("failed", 0)
        done = _MODEL_PRELOAD_STATE.get("summary", {}).get("done", 0)
        total = _MODEL_PRELOAD_STATE.get("summary", {}).get("total", 0)

        all_ready = (
            failed == 0
            and done == total
            and not _MODEL_PRELOAD_STATE.get("in_progress", False)
        )

        # Build error list
        errors = []
        if _MODEL_PRELOAD_STATE.get("per_agent"):
            for agent, models in _MODEL_PRELOAD_STATE["per_agent"].items():
                for model_id, status in models.items():
                    if status.get("status") == "error":
                        errors.append(
                            {
                                "agent": agent,
                                "model": model_id,
                                "error": status.get("error"),
                            }
                        )

        return {
            "all_ready": all_ready,
            "in_progress": _MODEL_PRELOAD_STATE.get("in_progress", False),
            "summary": _MODEL_PRELOAD_STATE.get("summary", {}),
            "errors": errors,
            "started_at": _MODEL_PRELOAD_STATE.get("started_at"),
            "completed_at": _MODEL_PRELOAD_STATE.get("completed_at"),
        }

    def _allow_quantized_variants(self) -> bool:
        return os.environ.get("GPU_ALLOW_QUANTIZED", "1").lower() not in {
            "0",
            "false",
            "no",
        }

    def _select_variant_for_spec(self, spec: dict[str, Any]) -> str | None:
        if spec.get("_selected_variant"):
            return spec["_selected_variant"]
        if spec.get("variant_preference"):
            return spec["variant_preference"]
        metadata = spec.get("_model_metadata") or {}
        manifest = metadata.get("manifest") if isinstance(metadata, dict) else None
        if not manifest:
            return None
        if self._allow_quantized_variants():
            for variant in manifest.get("quantized_variants", []) or []:
                if variant.get("recommended"):
                    return variant.get("name")
            variants = manifest.get("quantized_variants") or []
            if variants:
                return variants[0].get("name")
        return "fp16"

    def _variant_vram_mb(
        self, spec: dict[str, Any], variant: str | None
    ) -> float | None:
        metadata = spec.get("_model_metadata") or {}
        manifest = metadata.get("manifest") if isinstance(metadata, dict) else None
        if not manifest:
            return None
        if not variant or variant == "fp16":
            return manifest.get("approx_vram_mb")
        for candidate in manifest.get("quantized_variants", []) or []:
            if candidate.get("name") == variant:
                return candidate.get("approx_vram_mb")
        return manifest.get("approx_vram_mb")

    # --- Worker pool management -------------------------------------------------
    def start_agent_worker_pool(
        self,
        agent: str,
        adapter_name: str | None = None,
        *,
        pool_id: str | None = None,
        num_workers: int = 1,
        hold_seconds: int = 600,
        requestor: dict | None = None,
    ) -> dict[str, Any]:
        """Start a worker pool using AGENT_MODEL_MAP metadata."""
        try:
            from agents.common.model_loader import get_agent_model_metadata
        except Exception as exc:
            raise RuntimeError("model loader unavailable") from exc

        metadata = get_agent_model_metadata(agent, adapter_name)
        if not metadata:
            raise ValueError(f"Unknown model metadata for agent={agent}")

        version_dir = metadata.get("version_dir")
        base_info = metadata.get("base_info", {})
        model_ref = str(version_dir) if version_dir else base_info.get("hf_id")
        if not model_ref:
            raise ValueError(f"Missing base model reference for agent={agent}")

        adapter_path = metadata.get("adapter_path")
        entry = metadata.get("entry", {}) or {}
        spec = {**entry, "_model_metadata": metadata}
        variant = self._select_variant_for_spec(spec)

        resolved_pool_id = pool_id or f"{agent}-{adapter_name or 'base'}"
        adapter_str = str(adapter_path) if adapter_path else None
        return self.start_worker_pool(
            pool_id=resolved_pool_id,
            model_id=str(model_ref),
            adapter=adapter_str,
            num_workers=num_workers,
            hold_seconds=hold_seconds,
            requestor=requestor,
            variant=variant,
        )

    def _spawn_pool_worker(
        self,
        model_id: str | None,
        adapter: str | None,
        hold_seconds: int,
        variant: str | None = None,
    ):
        """Process entrypoint that loads base model and adapter then sleeps for hold_seconds.

        Note: in RE_RANKER_TEST_MODE this function will avoid heavy loads and simply sleep.
        """
        # Local import to avoid heavy deps at module import time in tests
        if os.environ.get("RE_RANKER_TEST_MODE", "1") in ("1", "true"):
            # test mode: minimal work and hold
            time.sleep(hold_seconds)
            return

        try:
            import torch
            from transformers import (
                AutoModelForCausalLM,
                AutoTokenizer,
                BitsAndBytesConfig,
            )

            if variant == "fp16":
                model = AutoModelForCausalLM.from_pretrained(
                    model_id,
                    dtype=getattr(torch, "float16", None),
                    device_map="auto",
                )
            elif variant == "bnb-4bit-qlora":
                bnb = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=getattr(torch, "float16", None),
                    bnb_4bit_quant_type="nf4",
                )
                model = AutoModelForCausalLM.from_pretrained(
                    model_id, quantization_config=bnb, device_map="auto"
                )
            else:  # default to 8-bit
                bnb = BitsAndBytesConfig(
                    load_in_8bit=True,
                    bnb_8bit_use_double_quant=True,
                    bnb_8bit_compute_dtype=getattr(torch, "float16", None),
                )
                model = AutoModelForCausalLM.from_pretrained(
                    model_id, quantization_config=bnb, device_map="auto"
                )
            _tok = AutoTokenizer.from_pretrained(model_id)

            if adapter:
                try:
                    from peft import PeftModel

                    model = PeftModel.from_pretrained(model, adapter)
                except Exception:
                    # adapter not available or failed – proceed
                    pass

            time.sleep(hold_seconds)

        except Exception:
            # Fail fast but keep process alive a short while so parent can introspect
            time.sleep(min(hold_seconds, 3))

    def start_worker_pool(
        self,
        pool_id: str,
        model_id: str | None,
        adapter: str | None,
        num_workers: int = 1,
        hold_seconds: int = 600,
        requestor: dict | None = None,
        variant: str | None = None,
    ) -> dict[str, Any]:
        """Start a named pool of warm workers for a given base model + adapter.

        This is intended for interactive dev/test and to allow GPU Orchestrator to
        keep a set of worker processes warm and ready. Pools are idempotent – attempting
        to start an already-running pool will return its existing state.
        """
        if pool_id in self._WORKER_POOLS:
            return {**self._WORKER_POOLS[pool_id], "note": "already_running"}

        # Validate args
        if num_workers < 1:
            raise ValueError("num_workers must be >= 1")

        procs: list[mp.Process] = []
        for _ in range(num_workers):
            p = mp.Process(
                target=self._spawn_pool_worker,
                args=(model_id, adapter, hold_seconds, variant),
                daemon=True,
            )
            p.start()
            procs.append(p)
            time.sleep(0.2)

        self._WORKER_POOLS[pool_id] = {
            "model": model_id,
            "adapter": adapter,
            "num_workers": num_workers,
            "procs": procs,
            "started_at": time.time(),
            "hold_seconds": hold_seconds,
            "variant": variant,
        }

        # Audit with optional requestor
        self._audit_worker_pool_event(
            "start",
            pool_id,
            model_id,
            adapter,
            num_workers,
            requestor=requestor,
            variant=variant,
        )
        # Persist worker pool row to DB (best-effort)
        try:
            if self.db_service:
                cursor, conn = self._get_safe_cursor(per_call=True, buffered=True)
                try:
                    cursor.execute(
                        "INSERT INTO worker_pools (pool_id, agent_name, model_id, adapter, desired_workers, spawned_workers, started_at, status, hold_seconds, metadata) VALUES (%s,%s,%s,%s,%s,%s,NOW(),%s,%s,%s)",
                        (
                            pool_id,
                            requestor.get("user") if requestor else None,
                            model_id,
                            adapter,
                            num_workers,
                            num_workers,
                            "running",
                            hold_seconds,
                            json.dumps({"variant": variant}),
                        ),
                    )
                    conn.commit()
                finally:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass
        except Exception:
            self.logger.debug("Failed to persist worker_pool to DB (non-fatal)")
        return {
            "pool_id": pool_id,
            "num_workers": num_workers,
            "status": "started",
            "variant": variant,
        }

    def stop_worker_pool(self, pool_id: str) -> dict[str, Any]:
        """Terminate a previously started pool and reap processes."""
        pool = self._WORKER_POOLS.get(pool_id)
        if not pool:
            raise ValueError("unknown_pool")

        procs = pool.get("procs", [])
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        # wait join
        for p in procs:
            try:
                p.join(timeout=1.0)
            except Exception:
                pass

        self._WORKER_POOLS.pop(pool_id, None)
        self._audit_worker_pool_event("stop", pool_id, None, None, 0, requestor=None)
        # Mark persistent pool as stopped (best-effort)
        try:
            if self.db_service:
                cursor, conn = self._get_safe_cursor(per_call=True, buffered=True)
                try:
                    cursor.execute(
                        "UPDATE worker_pools SET status=%s, spawned_workers=0 WHERE pool_id=%s",
                        ("stopped", pool_id),
                    )
                    conn.commit()
                finally:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass
        except Exception:
            self.logger.debug("Failed to update worker_pool status in DB (non-fatal)")
        return {"pool_id": pool_id, "status": "stopped"}

    def list_worker_pools(self) -> list[dict[str, Any]]:
        """Return summary of active pools."""
        out = []
        for pid, meta in list(self._WORKER_POOLS.items()):
            running = sum(1 for p in meta.get("procs", []) if p.is_alive())
            out.append(
                {
                    "pool_id": pid,
                    "model": meta.get("model"),
                    "adapter": meta.get("adapter"),
                    "configured_workers": meta.get("num_workers"),
                    "running_workers": running,
                    "started_at": meta.get("started_at"),
                    "variant": meta.get("variant"),
                }
            )
        return out

    def hot_swap_pool_adapter(
        self,
        pool_id: str,
        new_adapter: str | None,
        requestor: dict | None = None,
        wait_seconds: int = 10,
    ) -> dict[str, Any]:
        """Hot-swap adapter for a named pool: start new workers with new adapter, then stop old workers.

        This performs a blue-green style swap to avoid downtime: it spawns the same
        number of new workers, waits for a short warm period, then terminates the old ones.
        """
        meta = self._WORKER_POOLS.get(pool_id)
        if not meta:
            raise ValueError("unknown_pool")

        num_workers = meta.get("num_workers", 1)
        model = meta.get("model")

        # Start a temporary replacement pool id
        _temp_id = f"{pool_id}__swap_{int(time.time())}"
        procs: list[mp.Process] = []
        for _ in range(num_workers):
            p = mp.Process(
                target=self._spawn_pool_worker,
                args=(
                    model,
                    new_adapter,
                    meta.get("hold_seconds", 600),
                    meta.get("variant"),
                ),
                daemon=True,
            )
            p.start()
            procs.append(p)
            time.sleep(0.2)

        # Wait for a short warm period
        time.sleep(min(wait_seconds, 30))

        # stop old pool
        old_procs = meta.get("procs", [])
        for p in old_procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in old_procs:
            try:
                p.join(timeout=1.0)
            except Exception:
                pass

        # Replace metadata
        self._WORKER_POOLS[pool_id] = {
            "model": model,
            "adapter": new_adapter,
            "num_workers": num_workers,
            "procs": procs,
            "started_at": time.time(),
            "hold_seconds": meta.get("hold_seconds", 600),
            "variant": meta.get("variant"),
        }

        # audit swap
        self._audit_worker_pool_event(
            "swap_adapter",
            pool_id,
            model,
            new_adapter,
            num_workers,
            requestor=requestor,
            variant=meta.get("variant"),
        )
        return {"pool_id": pool_id, "status": "swapped", "new_adapter": new_adapter}

    def _audit_worker_pool_event(
        self,
        action: str,
        pool_id: str,
        model_id: str | None,
        adapter: str | None,
        num_workers: int,
        requestor: dict | None = None,
        variant: str | None = None,
    ):
        try:
            audit_dir = Path("logs/audit")
            audit_dir.mkdir(parents=True, exist_ok=True)
            entry = {
                "timestamp": time.time(),
                "action": action,
                "pool_id": pool_id,
                "model_id": model_id,
                "adapter": adapter,
                "num_workers": num_workers,
            }
            if variant:
                entry["variant"] = variant
            if requestor:
                entry["requestor"] = requestor
            # optionally include requestor identity when available (controller should add 'requestor' key)
            # Write as JSON line
            with open(audit_dir / "gpu_orchestrator_worker_pools.jsonl", "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            # Do not fail the operation if auditing fails
            self.logger.warning("Failed to write worker pool audit entry")

    def _audit_policy_event(
        self, action: str, detail: dict, requestor: dict | None = None
    ):
        try:
            audit_dir = Path("logs/audit")
            audit_dir.mkdir(parents=True, exist_ok=True)
            entry = {
                "timestamp": time.time(),
                "action": action,
                "detail": detail,
            }
            if requestor:
                entry["requestor"] = requestor

            with open(audit_dir / "gpu_orchestrator_pool_policy.jsonl", "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            self.logger.warning("Failed to write policy audit entry")

    def _rehydrate_worker_pools_from_db(self) -> None:
        """Load persisted worker pools from DB into memory without spawning processes.

        This is a best-effort, read-only hydration used during startup so the orchestrator
        can represent existing pools and reconcile them later.
        """
        try:
            cursor, conn = self._get_safe_cursor(dictionary=True, per_call=True, buffered=True)
            try:
                cursor.execute(
                    "SELECT pool_id, agent_name, model_id, adapter, desired_workers, spawned_workers, started_at, status, hold_seconds, metadata FROM worker_pools WHERE status IN ('starting','running','draining')"
                )
                rows = cursor.fetchall()
            finally:
                try:
                    cursor.close()
                except Exception:
                    pass
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass

            for r in rows:
                pid = r.get("pool_id")
                # We don't (re)spawn processes here — just restore metadata for reconciliation
                self._WORKER_POOLS[pid] = {
                    "model": r.get("model_id"),
                    "adapter": r.get("adapter"),
                    "num_workers": int(r.get("desired_workers") or 0),
                    "procs": [],
                    "started_at": (
                        r.get("started_at").timestamp()
                        if getattr(r.get("started_at"), "timestamp", None)
                        else None
                    ),
                    "hold_seconds": int(r.get("hold_seconds") or 600),
                    "variant": (
                        r.get("metadata")
                        and (
                            json.loads(r.get("metadata")).get("variant")
                            if isinstance(r.get("metadata"), str)
                            else r.get("metadata", {}).get("variant")
                        )
                    )
                    or None,
                }

            # Update metrics
            self.worker_pools_gauge.labels(
                agent=self.metrics.agent_name,
                agent_display_name=self.metrics.display_name,
            ).set(len(self._WORKER_POOLS))
        except Exception as e:
            # Do not fail startup, just log
            self.logger.debug(f"Error rehydrating worker pools from DB: {e}")

    def get_mps_allocation_config(self) -> dict[str, Any]:
        """Get MPS allocation configuration."""
        try:
            import json

            project_root = Path(self._project_root())
            config_path = project_root / "config" / "gpu" / "mps_allocation_config.json"

            if not config_path.exists():
                return {
                    "error": "MPS allocation configuration not found",
                    "path": str(config_path),
                }

            with open(config_path) as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load MPS allocation config: {e}")
            return {"error": str(e)}

    def _run_autoscaler(self):
        """Run autoscaling logic based on historical metrics and current load."""
        try:
            # Get current pending jobs across all streams
            total_pending = 0
            streams = [
                os.environ.get("ORCH_STREAM_PREFIX", "stream:orchestrator:")
                + "inference_jobs",
                os.environ.get("ORCH_STREAM_PREFIX", "stream:orchestrator:")
                + "preloads",
            ]

            for stream in streams:
                try:
                    pending_info = self.redis_client.xpending(stream, "cg:inference")
                    if pending_info and len(pending_info) > 0:
                        pending_count = (
                            pending_info[0].get("pending", 0)
                            if isinstance(pending_info[0], dict)
                            else pending_info[0]
                        )
                        total_pending += pending_count
                except Exception:
                    pass

            # Autoscaling rules based on pending jobs
            policy = self.get_pool_policy()
            current_total_workers = sum(
                p.get("num_workers", 0) for p in self._WORKER_POOLS.values()
            )
            max_workers = policy.get("max_total_workers", 8)

            # Scale up if pending jobs > 50 and we have capacity
            if total_pending > 50 and current_total_workers < max_workers:
                self.logger.info(
                    f"Autoscaler: High pending jobs ({total_pending}), considering scale up"
                )
                # For now, just log - production would implement actual scaling
                # TODO: Implement intelligent pool scaling based on job types and model requirements

            # Scale down if pending jobs < 5 and we have excess capacity
            elif total_pending < 5 and current_total_workers > policy.get(
                "min_warm_workers_per_pool", 0
            ):
                self.logger.info(
                    f"Autoscaler: Low pending jobs ({total_pending}), considering scale down"
                )
                # TODO: Implement pool consolidation

            # Monitor processing times (from histogram if available)
            # TODO: Add rules based on job_processing_duration_histogram percentiles

        except Exception as e:
            self.logger.debug(f"Autoscaler error: {e}")

    # Job queue helpers
    def submit_job(
        self,
        job_id: str,
        job_type: str,
        payload: dict[str, Any],
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Persist a job row and push into Redis stream (fallback to DB-only if Redis unavailable)."""
        try:
            # Persist job to DB if available
            if self.db_service:
                try:
                    pair = self.db_service.get_safe_cursor(per_call=True, buffered=True)
                    if isinstance(pair, tuple) and len(pair) == 2:
                        cursor, conn = pair
                    else:
                        # Fallback to using mb_conn or get_connection for test fakes
                        conn = getattr(self.db_service, "mb_conn", None)
                        if conn is None and callable(getattr(self.db_service, "get_connection", None)):
                            conn = self.db_service.get_connection()
                        cursor = conn.cursor()
                except Exception:
                    # Defensive fallback for poorly-formed test doubles
                    conn = getattr(self.db_service, "mb_conn", None)
                    if conn is None and callable(getattr(self.db_service, "get_connection", None)):
                        conn = self.db_service.get_connection()
                    cursor = conn.cursor()
                try:
                    cursor.execute(
                        "INSERT INTO orchestrator_jobs (job_id, type, payload, status, attempts, created_at, timeout_seconds) VALUES (%s,%s,%s,%s,%s,NOW(),%s)",
                        (
                            job_id,
                            job_type,
                            json.dumps(payload),
                            "pending",
                            0,
                            timeout_seconds,
                        ),
                    )
                    conn.commit()
                finally:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass

            # Try to push to Redis stream if available
            if self.redis_client:
                try:
                    # stream name is type-based, fallback to generic inference_jobs
                    stream = os.environ.get(
                        "ORCH_STREAM_PREFIX", "stream:orchestrator:"
                    ) + (job_type or "inference_jobs")
                    # store payload as JSON string under 'payload'
                    fields = {
                        "job_id": job_id,
                        "type": job_type,
                        "payload": json.dumps(payload),
                    }
                    # Inject tracing context into the Redis message fields
                    inject_trace_context(fields)

                    if timeout_seconds is not None:
                        fields["timeout_seconds"] = str(timeout_seconds)
                    self.redis_client.xadd(stream, fields)
                except Exception:
                    # Non-fatal; keep job persisted in DB
                    self.logger.debug("Failed to write job to Redis stream (non-fatal)")

            return {"job_id": job_id, "status": "submitted"}
        except Exception as e:
            self.logger.error(f"Failed to submit job: {e}")
            raise

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Retrieve job record from DB if available, else return from in-memory cache if present."""
        try:
            if self.db_service:
                cursor, conn = self._get_safe_cursor(per_call=True, dictionary=True, buffered=True)
                try:
                    cursor.execute(
                        "SELECT job_id, type, payload, status, attempts, created_at, updated_at, last_error, timeout_seconds FROM orchestrator_jobs WHERE job_id=%s",
                        (job_id,),
                    )
                    row = cursor.fetchone()
                finally:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass
                if row:
                    # parse payload JSON
                    try:
                        row["payload"] = (
                            json.loads(row["payload"]) if row.get("payload") else {}
                        )
                    except Exception:
                        pass
                    return row
            # fallback not found
            return None
        except Exception as e:
            self.logger.debug(f"Failed to read job from DB: {e}")
            return None

    def _reclaimer_pass(self):
        """Single pass over orchestrator streams to reclaim or move stale pending messages using XAUTOCLAIM.

        For each stream we use XAUTOCLAIM to atomically claim messages that have been idle
        longer than _claim_idle_ms, increment attempts in the job table, and either requeue them
        or send to DLQ if attempts exceed threshold.
        """
        if not self.redis_client:
            return

        # Probe for xautoclaim support once and cache the result. Some redis clients
        # or server versions may not implement xautoclaim; fall back when missing.
        if getattr(self, "_redis_supports_xautoclaim", None) is None:
            try:
                self._redis_supports_xautoclaim = hasattr(
                    self.redis_client, "xautoclaim"
                )
            except Exception:
                # Be conservative and disable xautoclaim if probing fails
                self._redis_supports_xautoclaim = False

        streams = [
            os.environ.get("ORCH_STREAM_PREFIX", "stream:orchestrator:")
            + "inference_jobs",
            os.environ.get("ORCH_STREAM_PREFIX", "stream:orchestrator:") + "preloads",
        ]

        for s in streams:
            try:
                # Use XAUTOCLAIM for atomic claiming of idle messages
                # XAUTOCLAIM returns [next_start_id, [id1, fields1, id2, fields2, ...]]
                start_id = "0"  # Start from the beginning
                count = 10  # Process in batches to avoid blocking too long
                reclaimer_consumer = "reclaimer"

                while True:
                    try:
                        # Try XAUTOCLAIM first (Redis 6.2+) if supported by client/server
                        if self._redis_supports_xautoclaim is False:
                            raise AttributeError("xautoclaim not supported")

                        result = None
                        try:
                            result = self.redis_client.xautoclaim(
                                s,
                                "cg:inference",
                                reclaimer_consumer,
                                self._claim_idle_ms,
                                start_id,
                                count=count,
                            )
                        except AttributeError:
                            # client does not implement xautoclaim
                            raise
                        except Exception as e:
                            # If Redis returned an error, log and fall back once
                            self.logger.debug(
                                f"Redis xautoclaim failed (will fallback): {e}"
                            )
                            self._redis_supports_xautoclaim = False
                            raise
                        # If xautoclaim returned an empty / unexpected result structure,
                        # treat it as unsupported and fall back to the safer manual path.
                        if (
                            not result
                            or not isinstance(result, (list, tuple))
                            or len(result) < 2
                        ):
                            # Fallback to manual reclaiming process which uses xpending_range/xrange
                            self._redis_supports_xautoclaim = False
                            self._fallback_reclaimer_pass(s)
                            break

                        next_start_id, claimed_messages = result[0], result[1]

                        # claimed_messages is a list of [id, fields, id, fields, ...]
                        for i in range(0, len(claimed_messages), 2):
                            msg_id = claimed_messages[i]
                            fields = (
                                claimed_messages[i + 1]
                                if i + 1 < len(claimed_messages)
                                else {}
                            )

                            # Extract job_id, payload, and timeout
                            job_id = None
                            payload = None
                            timeout_seconds = None
                            if b"job_id" in fields or "job_id" in fields:
                                job_id = fields.get(b"job_id") or fields.get("job_id")
                                if isinstance(job_id, bytes):
                                    job_id = job_id.decode("utf-8")
                            pld = fields.get(b"payload") or fields.get("payload")
                            if pld:
                                if isinstance(pld, bytes):
                                    try:
                                        payload = json.loads(pld.decode("utf-8"))
                                    except Exception:
                                        payload = pld.decode("utf-8")
                                else:
                                    try:
                                        payload = json.loads(pld)
                                    except Exception:
                                        payload = pld
                            timeout_val = fields.get(b"timeout_seconds") or fields.get(
                                "timeout_seconds"
                            )
                            if timeout_val:
                                try:
                                    timeout_seconds = (
                                        int(timeout_val)
                                        if isinstance(timeout_val, (str, bytes))
                                        else timeout_val
                                    )
                                except Exception:
                                    timeout_seconds = None

                            # Fetch and increment attempts from DB
                            attempts = 0
                            if job_id and self.db_service:
                                try:
                                    cursor, conn = self._get_safe_cursor(per_call=True, buffered=True)
                                    try:
                                        cursor.execute(
                                            "SELECT attempts FROM orchestrator_jobs WHERE job_id=%s",
                                            (job_id,),
                                        )
                                        r = cursor.fetchone()
                                        if r:
                                            attempts = int(r[0])
                                    finally:
                                        try:
                                            cursor.close()
                                        except Exception:
                                            pass
                                        try:
                                            if conn:
                                                conn.close()
                                        except Exception:
                                            pass
                                except Exception:
                                    attempts = 0

                            attempts += 1

                            # Update attempts in DB
                            if job_id and self.db_service:
                                try:
                                    cursor, conn = self._get_safe_cursor(per_call=True, buffered=True)
                                    try:
                                        cursor.execute(
                                            "UPDATE orchestrator_jobs SET attempts=%s, updated_at=NOW() WHERE job_id=%s",
                                            (attempts, job_id),
                                        )
                                        conn.commit()
                                    finally:
                                        try:
                                            cursor.close()
                                        except Exception:
                                            pass
                                        try:
                                            conn.close()
                                        except Exception:
                                            pass
                                except Exception:
                                    pass

                                # If attempts exceeded retry threshold, move to DLQ; otherwise requeue
                                if attempts >= self._job_retry_max:
                                    dlq = s + ":dlq"
                                    try:
                                        dlq_fields = {
                                            "job_id": job_id or "",
                                            "payload": json.dumps(payload)
                                            if payload is not None
                                            else "",
                                        }
                                        if timeout_seconds is not None:
                                            dlq_fields["timeout_seconds"] = str(timeout_seconds)
                                        self.redis_client.xadd(dlq, dlq_fields)
                                    except Exception:
                                        pass
                                    # Mark job dead-lettered in DB and ack
                                    if job_id and self.db_service:
                                        try:
                                            cursor, conn = self._get_safe_cursor(per_call=True, buffered=True)
                                            try:
                                                cursor.execute(
                                                    "UPDATE orchestrator_jobs SET status=%s, last_error=%s, updated_at=NOW() WHERE job_id=%s",
                                                    (
                                                        "dead_letter",
                                                        "max_attempts_exceeded",
                                                        job_id,
                                                    ),
                                                )
                                                conn.commit()
                                            finally:
                                                try:
                                                    cursor.close()
                                                except Exception:
                                                    pass
                                                try:
                                                    conn.close()
                                                except Exception:
                                                    pass
                                        except Exception:
                                            pass
                                    try:
                                        self.redis_client.xack(s, "cg:inference", msg_id)
                                    except Exception:
                                        pass
                                    self.reclaimer_dlq.inc()
                                else:
                                    # Requeue message as a new message for processing
                                    try:
                                        requeue_fields = {
                                            "job_id": job_id or "",
                                            "type": fields.get(b"type")
                                            or fields.get("type")
                                            or "",
                                            "payload": json.dumps(payload)
                                            if payload is not None
                                            else "",
                                        }
                                        if timeout_seconds is not None:
                                            requeue_fields["timeout_seconds"] = str(
                                                timeout_seconds
                                            )
                                        self.redis_client.xadd(s, requeue_fields)
                                        self.redis_client.xack(s, "cg:inference", msg_id)
                                    except Exception:
                                        pass
                                    self.reclaimer_requeued.inc()

                        start_id = next_start_id
                        if start_id == "0":
                            break  # Finished processing all

                    except AttributeError:
                        # XAUTOCLAIM not available (client or server) — fallback to manual reclaiming
                        self.logger.debug(
                            "XAUTOCLAIM not available (client/server). Falling back to manual reclaiming"
                        )
                        self._redis_supports_xautoclaim = False
                        self._fallback_reclaimer_pass(s)
                        break
                    except Exception as e:
                        # Don't let a transient redis or parsing error kill the reclaimer loop.
                        self.logger.debug(f"Error during XAUTOCLAIM pass: {e}")
                        self.reclaimer_errors.inc()
                        # Fall back to the safer manual path to avoid missing messages
                        try:
                            self._fallback_reclaimer_pass(s)
                        except Exception:
                            self.logger.debug("Fallback reclaimer also failed")
                        break

            except Exception as e:
                # Log and increment error metric — continue to next stream
                self.logger.debug(f"Error iterating stream {s}: {e}")
                self.reclaimer_errors.inc()
                continue

        # Count successful pass
        self.reclaimer_runs.inc()

    def _fallback_reclaimer_pass(self, stream: str):
        """Fallback reclaimer using xpending_range for older Redis versions."""
        try:
            pending = []
            try:
                pending = self.redis_client.xpending_range(
                    stream, "cg:inference", "-", "+", count=100
                )
            except Exception:
                return

            for entry in pending:
                try:
                    msg_id = entry[0]
                    idle = int(entry[2]) if len(entry) > 2 else 0
                    if idle < self._claim_idle_ms:
                        continue

                    # Read full message
                    entries = self.redis_client.xrange(stream, min=msg_id, max=msg_id)
                    if not entries:
                        continue
                    _, fields = entries[0]

                    job_id = None
                    payload = None
                    timeout_seconds = None
                    if b"job_id" in fields or "job_id" in fields:
                        job_id = fields.get(b"job_id") or fields.get("job_id")
                        if isinstance(job_id, bytes):
                            job_id = job_id.decode("utf-8")
                    pld = fields.get(b"payload") or fields.get("payload")
                    if pld:
                        if isinstance(pld, bytes):
                            try:
                                payload = json.loads(pld.decode("utf-8"))
                            except Exception:
                                payload = pld.decode("utf-8")
                        else:
                            try:
                                payload = json.loads(pld)
                            except Exception:
                                payload = pld
                    timeout_val = fields.get(b"timeout_seconds") or fields.get(
                        "timeout_seconds"
                    )
                    if timeout_val:
                        try:
                            timeout_seconds = (
                                int(timeout_val)
                                if isinstance(timeout_val, (str, bytes))
                                else timeout_val
                            )
                        except Exception:
                            timeout_seconds = None

                    # Fetch and increment attempts
                    attempts = 0
                    if job_id and self.db_service:
                        try:
                            cursor, conn = self._get_safe_cursor(per_call=True, buffered=True)
                            try:
                                cursor.execute(
                                    "SELECT attempts FROM orchestrator_jobs WHERE job_id=%s",
                                    (job_id,),
                                )
                                r = cursor.fetchone()
                                if r:
                                    attempts = int(r[0])
                            finally:
                                try:
                                    cursor.close()
                                except Exception:
                                    pass
                                try:
                                    conn.close()
                                except Exception:
                                    pass
                        except Exception:
                            attempts = 0

                    attempts += 1

                    if job_id and self.db_service:
                        try:
                            cursor, conn = self._get_safe_cursor(per_call=True, buffered=True)
                            try:
                                cursor.execute(
                                    "UPDATE orchestrator_jobs SET attempts=%s, updated_at=NOW() WHERE job_id=%s",
                                    (attempts, job_id),
                                )
                                conn.commit()
                            finally:
                                try:
                                    cursor.close()
                                except Exception:
                                    pass
                                try:
                                    conn.close()
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    if attempts >= self._job_retry_max:
                        dlq = stream + ":dlq"
                        try:
                            dlq_fields = {
                                "job_id": job_id or "",
                                "payload": json.dumps(payload)
                                if payload is not None
                                else "",
                            }
                            if timeout_seconds is not None:
                                dlq_fields["timeout_seconds"] = str(timeout_seconds)
                            self.redis_client.xadd(dlq, dlq_fields)
                        except Exception:
                            pass
                        if job_id and self.db_service:
                            try:
                                cursor, conn = self.db_service.get_safe_cursor(
                                    per_call=True, buffered=True
                                )
                                try:
                                    cursor.execute(
                                        "UPDATE orchestrator_jobs SET status=%s, last_error=%s, updated_at=NOW() WHERE job_id=%s",
                                        (
                                            "dead_letter",
                                            "max_attempts_exceeded",
                                            job_id,
                                        ),
                                    )
                                    conn.commit()
                                finally:
                                    try:
                                        cursor.close()
                                    except Exception:
                                        pass
                                    try:
                                        conn.close()
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        try:
                            self.redis_client.xack(stream, "cg:inference", msg_id)
                        except Exception:
                            pass
                    else:
                        try:
                            requeue_fields = {
                                "job_id": job_id or "",
                                "type": fields.get(b"type") or fields.get("type") or "",
                                "payload": json.dumps(payload)
                                if payload is not None
                                else "",
                            }
                            if timeout_seconds is not None:
                                requeue_fields["timeout_seconds"] = str(timeout_seconds)
                            self.redis_client.xadd(stream, requeue_fields)
                            self.redis_client.xack(stream, "cg:inference", msg_id)
                        except Exception:
                            pass

                except Exception:
                    pass
        except Exception:
            pass

    def _reclaimer_loop(self):
        while True:
            try:
                self._reclaimer_pass()
            except Exception:
                pass
            time.sleep(self._reclaim_interval_s)


# Global engine instance
engine = GPUOrchestratorEngine()
