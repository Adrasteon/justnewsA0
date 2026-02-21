"""
Workflow Engine for the Orchestrator.

Executes the main orchestration loop.
"""

import asyncio
import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, List

from common.observability import get_logger
from .runtime_config import extract_owner_overrides
from .policies import (
    WorkflowPolicy,
    IngestionToAnalysisPolicy,
    AnalysisToEmbeddingPolicy,
    AnalysisToSummaryPolicy,
    AnalysisToFactCheckPolicy,
    IncrementalClusteringPolicy,
    ClusterToSynthesisPolicy,
    HeavyClusterRetryPolicy,
    SynthesisToCritiquePolicy,
    SynthesisToPublishingPolicy,
)
from .resources import ResourceMonitor

logger = get_logger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}

class OrchestratorEngine:
    def __init__(self):
        self.running = False
        self.resource_monitor = ResourceMonitor()
        self.policies: List[WorkflowPolicy] = []
        self.runtime_store = None
        self.runtime_config_version = 0
        self.last_runtime_sync_at: str | None = None
        self.last_runtime_apply_status: dict[str, Any] = {"status": "not_initialized"}
        self.autonomic_mode = str(os.environ.get("AUTONOMIC_MODE", "disabled")).strip().lower()
        if self.autonomic_mode not in {"disabled", "shadow", "active"}:
            self.autonomic_mode = "disabled"
        self.autonomic_decisions_enabled = _env_bool(
            "AUTONOMIC_DECISIONS_ENABLED", default=False
        )
        self.autonomic_cooldown_seconds = max(
            1, int(os.environ.get("AUTONOMIC_DECISION_COOLDOWN_SECONDS", "60"))
        )
        self.autonomic_budget_window_seconds = max(
            30, int(os.environ.get("AUTONOMIC_DECISION_BUDGET_WINDOW_SECONDS", "300"))
        )
        self.autonomic_max_actions_per_window = max(
            1, int(os.environ.get("AUTONOMIC_MAX_ACTIONS_PER_WINDOW", "4"))
        )
        self.learning_enabled = _env_bool("AUTONOMIC_LEARNING_ENABLED", default=True)
        self.bandit_enabled = _env_bool("AUTONOMIC_BANDIT_ENABLED", default=False)
        self.auto_rollback_enabled = _env_bool(
            "AUTONOMIC_AUTO_ROLLBACK_ENABLED", default=False
        )
        self.shadow_score_window = max(
            20, int(os.environ.get("AUTONOMIC_SHADOW_SCORE_WINDOW", "120"))
        )
        self.bandit_epsilon = min(
            1.0,
            max(0.0, float(os.environ.get("AUTONOMIC_BANDIT_EPSILON", "0.1"))),
        )
        self.slo_max_tick_error_rate = min(
            1.0,
            max(
                0.0,
                float(os.environ.get("AUTONOMIC_SLO_MAX_TICK_ERROR_RATE", "0.2")),
            ),
        )
        self.slo_max_stall_seconds = max(
            60,
            int(os.environ.get("AUTONOMIC_SLO_MAX_STALL_SECONDS", "900")),
        )
        self.alert_staleness_seconds = max(
            10,
            int(os.environ.get("AUTONOMIC_ALERT_STALENESS_SECONDS", "180")),
        )
        self.alert_propagation_lag_seconds = max(
            1,
            int(os.environ.get("AUTONOMIC_ALERT_PROPAGATION_LAG_SECONDS", "5")),
        )
        self.autonomic_allowed_keys = {
            "orchestrator.polling_interval_seconds",
            "orchestrator.max_concurrent_tasks",
        }
        denylist_raw = os.environ.get(
            "AUTONOMIC_DENYLIST_KEYS",
            "analyst.workers,analyst.model.name,mcp_bus.call.max_retries,mcp_bus.call.read_timeout_sec,fact_checker.search.max_queries,fact_checker.search.deep_crawl_timeout_sec",
        )
        self.autonomic_denylist_keys = {
            item.strip() for item in denylist_raw.split(",") if item.strip()
        }
        self._autonomic_recent_action_epochs: list[float] = []
        self._autonomic_last_action_epoch: float | None = None
        self._autonomic_last_apply_version: int | None = None
        self._autonomic_last_apply_at: str | None = None
        self._autonomic_last_rollback: dict[str, Any] | None = None
        self._autonomic_last_decision: dict[str, Any] | None = None
        self._autonomic_decision_history: list[dict[str, Any]] = []
        stall_threshold_seconds = int(
            os.environ.get("AUTONOMIC_STALL_THRESHOLD_SECONDS", "300")
        )
        self.telemetry: dict[str, Any] = {
            "tick": {
                "count": 0,
                "error_count": 0,
                "last_started_at": None,
                "last_completed_at": None,
                "last_duration_ms": 0.0,
                "last_error": None,
            },
            "policies": {},
            "progress": {
                "last_progress_at": None,
                "stall_threshold_seconds": max(stall_threshold_seconds, 30),
            },
        }
        self._last_resource_stats = None
        self._last_resource_healthy = True
        self._active_alerts: dict[str, Any] = {}
        self._bandit_state: dict[str, Any] = {
            "arms": {
                "hold": {"pulls": 0, "reward_sum": 0.0},
                "scale_down": {"pulls": 0, "reward_sum": 0.0},
                "scale_up": {"pulls": 0, "reward_sum": 0.0},
            },
            "last_selected_arm": None,
            "last_reward": None,
        }
        self._load_config()
        self._init_policies()

    def _policy_batch_limit(self, policy_name: str, default_limit: int) -> int:
        capped_default_map = {
            "ingestion_to_analysis": 6,
            "analysis_to_fact_check": 4,
            "incremental_clustering": 8,
            "cluster_to_synthesis": 4,
            "synthesis_to_publishing": 6,
        }
        fallback = min(default_limit, capped_default_map.get(policy_name, default_limit))
        env_key = f"ORCH_POLICY_LIMIT_{policy_name.upper()}"
        raw = os.environ.get(env_key)
        if raw is None:
            return max(1, fallback)
        try:
            return max(1, min(default_limit, int(raw)))
        except Exception:
            return max(1, fallback)

    def _load_config(self):
        self.mcp_bus_url = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
        
        # Default Config
        self.config = {
            "polling_interval_seconds": 10,
            "max_concurrent_tasks": 5,
            "resource_limits": {
                "max_cpu_percent": 95,
                "max_memory_percent": 98,
                "max_gpu_utilization": 95,
                "max_gpu_memory_percent": 95
            }
        }
        
        # Override from system_config.json if available
        try:
            config_path = os.path.join(os.getcwd(), "config", "system_config.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    sys_config = json.load(f)
                    orch_config = sys_config.get("orchestrator", {})
                    self.config.update(orch_config)
        except Exception as e:
            logger.warning(f"Failed to load system_config.json: {e}")

    def _init_policies(self):
        # Register enabled policies
        self.policies.append(IngestionToAnalysisPolicy(self.mcp_bus_url))
        self.policies.append(AnalysisToEmbeddingPolicy(self.mcp_bus_url))
        self.policies.append(AnalysisToSummaryPolicy(self.mcp_bus_url))
        self.policies.append(AnalysisToFactCheckPolicy(self.mcp_bus_url))
        self.policies.append(IncrementalClusteringPolicy(self.mcp_bus_url))
        self.policies.append(ClusterToSynthesisPolicy(self.mcp_bus_url))
        self.policies.append(SynthesisToCritiquePolicy(self.mcp_bus_url))
        self.policies.append(SynthesisToPublishingPolicy(self.mcp_bus_url))
        self.policies.append(HeavyClusterRetryPolicy(self.mcp_bus_url))
        for policy in self.policies:
            self._ensure_policy_telemetry(policy.name())
        logger.info(f"Initialized {len(self.policies)} policies.")

    def _ensure_policy_telemetry(self, policy_name: str) -> dict[str, Any]:
        policy_map = self.telemetry.setdefault("policies", {})
        policy_map.setdefault(
            policy_name,
            {
                "check_count": 0,
                "execute_count": 0,
                "success_count": 0,
                "error_count": 0,
                "total_items_seen": 0,
                "last_queue_depth": 0,
                "last_checked_at": None,
                "last_check_ms": 0.0,
                "last_execute_ms": 0.0,
                "last_success_at": None,
                "last_success_at_epoch": None,
                "last_error": None,
                "last_error_at": None,
            },
        )
        return policy_map[policy_name]

    def attach_runtime_store(self, runtime_store: Any) -> None:
        self.runtime_store = runtime_store
        self._sync_runtime_config(force=True)

    def _sync_runtime_config(self, force: bool = False) -> None:
        if self.runtime_store is None:
            return

        try:
            state = self.runtime_store.get_state()
            version = int(state.get("version", 0))
            if not force and version <= int(self.runtime_config_version):
                return

            owner_overrides = extract_owner_overrides(
                state.get("overrides", {}), "workflow_orchestrator"
            )
            apply_result = self.apply_runtime_overrides(owner_overrides)
            self.runtime_config_version = version
            self.last_runtime_sync_at = _utc_now()
            self.last_runtime_apply_status = {
                "status": "ok",
                "version": version,
                "owner": "workflow_orchestrator",
                "applied_keys": sorted(apply_result.get("applied", {}).keys()),
                "ignored_keys": sorted(apply_result.get("ignored", {}).keys()),
                "synced_at": self.last_runtime_sync_at,
            }
        except Exception as exc:
            self.last_runtime_sync_at = _utc_now()
            self.last_runtime_apply_status = {
                "status": "error",
                "version": self.runtime_config_version,
                "owner": "workflow_orchestrator",
                "error": str(exc),
                "synced_at": self.last_runtime_sync_at,
            }
            logger.warning("Runtime config sync failed: %s", exc)

    def apply_runtime_overrides(self, overrides: dict[str, Any]) -> dict[str, Any]:
        """Apply runtime override keys owned by workflow orchestrator."""
        applied: dict[str, Any] = {}
        ignored: dict[str, Any] = {}

        for key, value in overrides.items():
            if not key.startswith("orchestrator."):
                ignored[key] = value
                continue

            suffix = key.split("orchestrator.", 1)[1]
            if not suffix:
                ignored[key] = value
                continue

            path_parts = suffix.split(".")
            target = self.config
            try:
                for part in path_parts[:-1]:
                    existing = target.get(part)
                    if not isinstance(existing, dict):
                        target[part] = {}
                    target = target[part]
                target[path_parts[-1]] = value
                applied[key] = value
            except Exception:
                ignored[key] = value

        if applied:
            logger.info(
                "Applied runtime overrides to orchestrator: %s",
                ", ".join(sorted(applied.keys())),
            )

        return {"applied": applied, "ignored": ignored}

    def _compute_autonomic_action(self) -> dict[str, Any]:
        now_epoch = time.time()
        reason = "no_action"
        proposed_patch: dict[str, Any] = {}

        current_poll = int(self.config.get("polling_interval_seconds", 10))
        current_tasks = int(self.config.get("max_concurrent_tasks", 5))
        resource_limits = self.config.get("resource_limits", {})
        resource_stats = self._last_resource_stats or self.resource_monitor.get_stats()

        cpu_percent = float(resource_stats.cpu_percent)
        memory_percent = float(resource_stats.memory_percent)
        gpu_util = (
            float(resource_stats.gpu_utilization)
            if resource_stats.gpu_utilization is not None
            else None
        )

        cpu_limit = float(resource_limits.get("max_cpu_percent", 95))
        mem_limit = float(resource_limits.get("max_memory_percent", 98))
        gpu_limit = float(resource_limits.get("max_gpu_utilization", 95))

        pressure_detected = (
            cpu_percent >= (cpu_limit - 2)
            or memory_percent >= (mem_limit - 2)
            or (gpu_util is not None and gpu_util >= (gpu_limit - 2))
        )

        progress_info = self.telemetry.get("progress", {})
        last_progress_at = progress_info.get("last_progress_at")
        stall_threshold = int(progress_info.get("stall_threshold_seconds", 300))
        seconds_since_last_progress = None
        if last_progress_at:
            try:
                parsed = datetime.fromisoformat(last_progress_at.replace("Z", "+00:00"))
                seconds_since_last_progress = max(
                    0.0,
                    now_epoch - parsed.astimezone(timezone.utc).timestamp(),
                )
            except Exception:
                seconds_since_last_progress = None

        stalled = bool(
            seconds_since_last_progress is not None
            and seconds_since_last_progress > stall_threshold
        )

        if pressure_detected:
            reason = "resource_pressure"
            proposed_patch["orchestrator.max_concurrent_tasks"] = max(1, current_tasks - 1)
            proposed_patch["orchestrator.polling_interval_seconds"] = min(30, current_poll + 1)
        elif stalled and self._last_resource_healthy:
            reason = "downstream_stall_recovery"
            proposed_patch["orchestrator.polling_interval_seconds"] = max(1, current_poll - 1)
            proposed_patch["orchestrator.max_concurrent_tasks"] = min(30, current_tasks + 1)
        else:
            reason = "stable_no_change"

        return {
            "reason": reason,
            "proposed_patch": proposed_patch,
            "inputs": {
                "current_polling_interval_seconds": current_poll,
                "current_max_concurrent_tasks": current_tasks,
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "gpu_utilization": gpu_util,
                "resource_healthy": self._last_resource_healthy,
                "seconds_since_last_progress": round(seconds_since_last_progress, 3)
                if seconds_since_last_progress is not None
                else None,
                "stall_threshold_seconds": stall_threshold,
                "stalled": stalled,
            },
        }

    def _run_autonomic_decision_cycle(self) -> None:
        now_epoch = time.time()
        decision = {
            "timestamp": _utc_now(),
            "mode": self.autonomic_mode,
            "enabled": self.autonomic_decisions_enabled,
            "reason": None,
            "proposed_patch": {},
            "guardrails": {},
            "result": {"status": "noop"},
        }

        if not self.autonomic_decisions_enabled:
            decision["reason"] = "feature_flag_disabled"
            decision["result"] = {"status": "skipped"}
            self._record_autonomic_decision(decision)
            return

        if self.autonomic_mode == "disabled":
            decision["reason"] = "mode_disabled"
            decision["result"] = {"status": "skipped"}
            self._record_autonomic_decision(decision)
            return

        action = self._compute_autonomic_action()
        decision["reason"] = action.get("reason")
        decision["proposed_patch"] = dict(action.get("proposed_patch", {}))
        decision["inputs"] = action.get("inputs", {})

        if not decision["proposed_patch"]:
            decision["result"] = {"status": "noop", "message": "no bounded action"}
            self._record_autonomic_decision(decision)
            return

        window_start = now_epoch - self.autonomic_budget_window_seconds
        self._autonomic_recent_action_epochs = [
            ts for ts in self._autonomic_recent_action_epochs if ts >= window_start
        ]

        cooldown_ok = (
            self._autonomic_last_action_epoch is None
            or (now_epoch - self._autonomic_last_action_epoch) >= self.autonomic_cooldown_seconds
        )
        budget_ok = (
            len(self._autonomic_recent_action_epochs) < self.autonomic_max_actions_per_window
        )

        unknown_or_blocked_keys = [
            key
            for key in decision["proposed_patch"].keys()
            if key not in self.autonomic_allowed_keys or key in self.autonomic_denylist_keys
        ]
        denylist_ok = len(unknown_or_blocked_keys) == 0

        decision["guardrails"] = {
            "cooldown_seconds": self.autonomic_cooldown_seconds,
            "cooldown_ok": cooldown_ok,
            "budget_window_seconds": self.autonomic_budget_window_seconds,
            "max_actions_per_window": self.autonomic_max_actions_per_window,
            "actions_in_window": len(self._autonomic_recent_action_epochs),
            "budget_ok": budget_ok,
            "denylist_ok": denylist_ok,
            "blocked_keys": unknown_or_blocked_keys,
            "allowed_keys": sorted(self.autonomic_allowed_keys),
        }

        if not (cooldown_ok and budget_ok and denylist_ok):
            decision["result"] = {
                "status": "blocked",
                "message": "guardrail block",
            }
            self._record_autonomic_decision(decision)
            return

        if self.autonomic_mode == "shadow":
            decision["result"] = {
                "status": "shadow",
                "message": "decision recorded without apply",
            }
            self._record_autonomic_decision(decision)
            return

        if self.runtime_store is None:
            decision["result"] = {
                "status": "blocked",
                "message": "runtime_store_unavailable",
            }
            self._record_autonomic_decision(decision)
            return

        apply_result = self.runtime_store.apply_patch(
            decision["proposed_patch"],
            reason=f"autonomic:{decision['reason']}",
            actor="autonomic_controller",
        )
        if apply_result.get("status") == "ok":
            self._autonomic_last_action_epoch = now_epoch
            self._autonomic_recent_action_epochs.append(now_epoch)
            self._autonomic_last_apply_version = int(apply_result.get("version", 0))
            self._autonomic_last_apply_at = _utc_now()
            self._sync_runtime_config(force=True)

        decision["result"] = {
            "status": apply_result.get("status"),
            "apply_result": apply_result,
        }
        self._record_autonomic_decision(decision)

    def _record_autonomic_decision(self, decision: dict[str, Any]) -> None:
        self._autonomic_last_decision = decision
        self._autonomic_decision_history.append(decision)
        if len(self._autonomic_decision_history) > 50:
            self._autonomic_decision_history = self._autonomic_decision_history[-50:]

        if decision.get("mode") == "shadow":
            logger.info(
                "Autonomic shadow decision recorded: status=%s reason=%s patch=%s",
                decision.get("result", {}).get("status"),
                decision.get("reason"),
                decision.get("proposed_patch", {}),
            )

        self.telemetry.setdefault("autonomic", {})
        self.telemetry["autonomic"].update(
            {
                "decisions_total": self.telemetry.get("autonomic", {}).get("decisions_total", 0)
                + 1,
                "last_decision": decision,
                "history_tail": self._autonomic_decision_history[-10:],
            }
        )

        if self.learning_enabled and self.autonomic_mode == "shadow":
            self._record_shadow_mode_score(decision)

    def _record_shadow_mode_score(self, decision: dict[str, Any]) -> None:
        autonomic_telemetry = self.telemetry.setdefault("autonomic", {})
        learning = autonomic_telemetry.setdefault("learning", {})
        shadow = learning.setdefault(
            "shadow_mode",
            {
                "sample_count": 0,
                "score_window": self.shadow_score_window,
                "scores_recent": [],
                "avg_score_recent": 0.0,
                "last_score": 0.0,
                "last_inputs": {},
            },
        )

        inputs = decision.get("inputs", {}) if isinstance(decision, dict) else {}
        score = 1.0
        if not bool(inputs.get("resource_healthy", True)):
            score -= 0.35
        if bool(inputs.get("stalled", False)):
            score -= 0.45
        if decision.get("result", {}).get("status") == "blocked":
            score -= 0.1
        if decision.get("reason") == "stable_no_change":
            score += 0.05

        score = round(max(0.0, min(1.0, score)), 4)
        scores_recent = list(shadow.get("scores_recent", []))
        scores_recent.append(score)
        scores_recent = scores_recent[-self.shadow_score_window :]

        shadow["sample_count"] = int(shadow.get("sample_count", 0)) + 1
        shadow["scores_recent"] = scores_recent
        shadow["last_score"] = score
        shadow["last_inputs"] = inputs
        shadow["avg_score_recent"] = round(sum(scores_recent) / len(scores_recent), 4)

        if self.bandit_enabled:
            self._update_bandit_state(score)

    def _update_bandit_state(self, reward: float) -> None:
        arms = self._bandit_state.setdefault("arms", {})
        if not arms:
            return

        arm_names = sorted(arms.keys())
        pick_explore = random.random() < self.bandit_epsilon
        if pick_explore:
            selected_arm = random.choice(arm_names)
        else:
            selected_arm = max(
                arm_names,
                key=lambda arm: (
                    float(arms[arm].get("reward_sum", 0.0))
                    / max(1, int(arms[arm].get("pulls", 0)))
                ),
            )

        arm_state = arms[selected_arm]
        arm_state["pulls"] = int(arm_state.get("pulls", 0)) + 1
        arm_state["reward_sum"] = round(
            float(arm_state.get("reward_sum", 0.0)) + float(reward),
            4,
        )
        arm_state["avg_reward"] = round(
            float(arm_state.get("reward_sum", 0.0))
            / max(1, int(arm_state.get("pulls", 0))),
            4,
        )
        self._bandit_state["last_selected_arm"] = selected_arm
        self._bandit_state["last_reward"] = round(float(reward), 4)

    def _update_hardening_signals(self) -> None:
        alerts: dict[str, Any] = {}
        now_epoch = time.time()

        if self.last_runtime_sync_at:
            try:
                sync_epoch = datetime.fromisoformat(
                    str(self.last_runtime_sync_at).replace("Z", "+00:00")
                ).astimezone(timezone.utc).timestamp()
                age_seconds = max(0.0, now_epoch - sync_epoch)
                if age_seconds > self.alert_staleness_seconds:
                    alerts["runtime_config_stale"] = {
                        "severity": "warning",
                        "age_seconds": round(age_seconds, 3),
                        "threshold_seconds": self.alert_staleness_seconds,
                    }
            except Exception:
                pass

        if self.last_runtime_apply_status.get("status") == "error":
            alerts["runtime_apply_failure"] = {
                "severity": "critical",
                "detail": self.last_runtime_apply_status,
            }

        if self._autonomic_last_apply_at and self.last_runtime_sync_at:
            try:
                apply_epoch = datetime.fromisoformat(
                    str(self._autonomic_last_apply_at).replace("Z", "+00:00")
                ).astimezone(timezone.utc).timestamp()
                sync_epoch = datetime.fromisoformat(
                    str(self.last_runtime_sync_at).replace("Z", "+00:00")
                ).astimezone(timezone.utc).timestamp()
                propagation_lag = max(0.0, sync_epoch - apply_epoch)
                if propagation_lag > self.alert_propagation_lag_seconds:
                    alerts["apply_propagation_lag"] = {
                        "severity": "warning",
                        "lag_seconds": round(propagation_lag, 3),
                        "threshold_seconds": self.alert_propagation_lag_seconds,
                    }
            except Exception:
                pass

        self._active_alerts = alerts

    def _maybe_auto_rollback_on_slo_breach(self) -> None:
        if not self.auto_rollback_enabled:
            return
        if self.runtime_store is None:
            return
        if self._autonomic_last_apply_version is None:
            return

        tick_count = int(self.telemetry.get("tick", {}).get("count", 0))
        tick_errors = int(self.telemetry.get("tick", {}).get("error_count", 0))
        error_rate = (float(tick_errors) / float(tick_count)) if tick_count > 0 else 0.0

        progress = self.telemetry.get("progress", {})
        last_progress_at = progress.get("last_progress_at")
        seconds_since_last_progress = 0.0
        if last_progress_at:
            try:
                last_epoch = datetime.fromisoformat(
                    str(last_progress_at).replace("Z", "+00:00")
                ).astimezone(timezone.utc).timestamp()
                seconds_since_last_progress = max(0.0, time.time() - last_epoch)
            except Exception:
                seconds_since_last_progress = 0.0

        hard_breach = (
            error_rate > self.slo_max_tick_error_rate
            or seconds_since_last_progress > self.slo_max_stall_seconds
        )
        if not hard_breach:
            return

        if self._autonomic_last_rollback and int(
            self._autonomic_last_rollback.get("inverse_of_apply_version", -1)
        ) == int(self._autonomic_last_apply_version):
            return

        rollback_result = self.runtime_store.rollback_apply_version(
            self._autonomic_last_apply_version,
            reason="autonomic:auto_rollback_slo_breach",
            actor="autonomic_controller",
        )
        if rollback_result.get("status") == "ok":
            self._sync_runtime_config(force=True)

        self._autonomic_last_rollback = {
            "timestamp": _utc_now(),
            "error_rate": round(error_rate, 4),
            "seconds_since_last_progress": round(seconds_since_last_progress, 3),
            "thresholds": {
                "max_tick_error_rate": self.slo_max_tick_error_rate,
                "max_stall_seconds": self.slo_max_stall_seconds,
            },
            "result": rollback_result,
            "inverse_of_apply_version": self._autonomic_last_apply_version,
        }

    async def start(self):
        """Start the orchestration loop."""
        self.running = True
        logger.info("Orchestrator Engine started.")
        asyncio.create_task(self._run_loop())

    async def stop(self):
        """Stop the orchestration loop."""
        self.running = False
        logger.info("Orchestrator Engine stopping...")

    async def _run_loop(self):
        while self.running:
            start_time = time.time()
            self.telemetry["tick"]["count"] += 1
            self.telemetry["tick"]["last_started_at"] = _utc_now()
            try:
                await self._process_tick()
            except Exception as e:
                self.telemetry["tick"]["error_count"] += 1
                self.telemetry["tick"]["last_error"] = str(e)
                logger.error(f"Error in orchestration loop: {e}", exc_info=True)
            finally:
                elapsed_ms = max(0.0, (time.time() - start_time) * 1000.0)
                self.telemetry["tick"]["last_duration_ms"] = round(elapsed_ms, 3)
                self.telemetry["tick"]["last_completed_at"] = _utc_now()
            
            # Sleep remainder of interval
            elapsed = time.time() - start_time
            sleep_time = max(1.0, self.config["polling_interval_seconds"] - elapsed)
            await asyncio.sleep(sleep_time)

    async def _process_tick(self):
        self._sync_runtime_config()

        # 1. Check Resources
        thresholds = self.config["resource_limits"]
        self._last_resource_stats = self.resource_monitor.get_stats()
        self._last_resource_healthy = self.resource_monitor.check_health(thresholds)

        # In shadow mode, emit a decision snapshot before potentially long policy
        # execution so telemetry endpoints always have a recent last_decision.
        if (
            self.autonomic_mode == "shadow"
            and self.autonomic_decisions_enabled
            and self._autonomic_last_decision is None
        ):
            self._run_autonomic_decision_cycle()

        if not self._last_resource_healthy:
            logger.info("Resources saturated. Skipping tick.")
            self._run_autonomic_decision_cycle()
            return

        # 2. Iterate Policies
        max_tasks = self.config["max_concurrent_tasks"]
        
        for policy in self.policies:
            policy_name = policy.name()
            policy_telemetry = self._ensure_policy_telemetry(policy_name)
            check_started = time.time()
            # We treat max_tasks as a per-policy limit for simplicity v1
            try:
                policy_limit = self._policy_batch_limit(policy_name, max_tasks)
                items = policy.check_condition(limit=policy_limit)
                policy_telemetry["check_count"] += 1
                policy_telemetry["last_checked_at"] = _utc_now()
                policy_telemetry["last_check_ms"] = round(
                    (time.time() - check_started) * 1000.0, 3
                )
                policy_telemetry["last_limit"] = int(policy_limit)
                policy_telemetry["last_queue_depth"] = len(items)
                policy_telemetry["total_items_seen"] += len(items)
                if items:
                    logger.info(
                        "Policy '%s' matched %s items (limit=%s).",
                        policy_name,
                        len(items),
                        policy_limit,
                    )
                    execute_started = time.time()
                    await policy.execute(items)
                    policy_telemetry["execute_count"] += 1
                    policy_telemetry["success_count"] += 1
                    policy_telemetry["last_execute_ms"] = round(
                        (time.time() - execute_started) * 1000.0, 3
                    )
                    policy_telemetry["last_success_at"] = _utc_now()
                    policy_telemetry["last_success_at_epoch"] = time.time()
                    self.telemetry["progress"]["last_progress_at"] = (
                        policy_telemetry["last_success_at"]
                    )
                else:
                    # Debug log only to avoid spam
                    # logger.debug(f"Policy '{policy.name()}' matched 0 items.")
                    pass
            except Exception as e:
                policy_telemetry["error_count"] += 1
                policy_telemetry["last_error"] = str(e)
                policy_telemetry["last_error_at"] = _utc_now()
                logger.error(f"Policy '{policy_name}' failure: {e}")

        self._run_autonomic_decision_cycle()
        self._update_hardening_signals()
        self._maybe_auto_rollback_on_slo_breach()

    def get_status_snapshot(self) -> dict[str, Any]:
        now_epoch = time.time()
        stall_threshold = int(
            self.telemetry.get("progress", {}).get("stall_threshold_seconds", 300)
        )
        last_progress_at = self.telemetry.get("progress", {}).get("last_progress_at")
        seconds_since_last_progress = None
        if last_progress_at:
            try:
                parsed = datetime.fromisoformat(last_progress_at.replace("Z", "+00:00"))
                seconds_since_last_progress = max(
                    0.0,
                    now_epoch
                    - parsed.astimezone(timezone.utc).timestamp(),
                )
            except Exception:
                seconds_since_last_progress = None

        is_stalled = bool(
            seconds_since_last_progress is not None
            and seconds_since_last_progress > stall_threshold
        )

        stalled_policies: list[str] = []
        for policy_name, policy_data in self.telemetry.get("policies", {}).items():
            queue_depth = int(policy_data.get("last_queue_depth", 0) or 0)
            if queue_depth <= 0:
                continue
            last_success_epoch = policy_data.get("last_success_at_epoch")
            if last_success_epoch is None:
                stalled_policies.append(policy_name)
                continue
            if (now_epoch - float(last_success_epoch)) > stall_threshold:
                stalled_policies.append(policy_name)

        resource_stats = self._last_resource_stats or self.resource_monitor.get_stats()
        resource_signals = {
            "healthy": self._last_resource_healthy,
            "thresholds": self.config.get("resource_limits", {}),
            "stats": {
                "cpu_percent": resource_stats.cpu_percent,
                "memory_percent": resource_stats.memory_percent,
                "gpu_utilization": resource_stats.gpu_utilization,
                "gpu_memory_percent": resource_stats.gpu_memory_percent,
            },
        }

        return {
            "autonomic": {
                "mode": self.autonomic_mode,
                "decisions_enabled": self.autonomic_decisions_enabled,
                "learning_enabled": self.learning_enabled,
                "bandit_enabled": self.bandit_enabled,
                "auto_rollback_enabled": self.auto_rollback_enabled,
                "runtime_config_version": self.runtime_config_version,
                "last_runtime_sync_at": self.last_runtime_sync_at,
                "last_runtime_apply_status": self.last_runtime_apply_status,
                "last_apply_version": self._autonomic_last_apply_version,
                "last_apply_at": self._autonomic_last_apply_at,
                "last_rollback": self._autonomic_last_rollback,
                "last_decision": self._autonomic_last_decision,
                "decision_history_tail": self._autonomic_decision_history[-10:],
                "guardrails": {
                    "cooldown_seconds": self.autonomic_cooldown_seconds,
                    "budget_window_seconds": self.autonomic_budget_window_seconds,
                    "max_actions_per_window": self.autonomic_max_actions_per_window,
                    "allowed_keys": sorted(self.autonomic_allowed_keys),
                    "denylist_keys": sorted(self.autonomic_denylist_keys),
                },
                "learning": self.telemetry.get("autonomic", {}).get("learning", {}),
                "bandit": self._bandit_state,
                "slo_thresholds": {
                    "max_tick_error_rate": self.slo_max_tick_error_rate,
                    "max_stall_seconds": self.slo_max_stall_seconds,
                },
            },
            "telemetry": self.telemetry,
            "signals": {
                "resource": resource_signals,
                "downstream_stall": {
                    "stall_threshold_seconds": stall_threshold,
                    "seconds_since_last_progress": round(seconds_since_last_progress, 3)
                    if seconds_since_last_progress is not None
                    else None,
                    "is_stalled": is_stalled,
                    "stalled_policies": stalled_policies,
                    "last_progress_at": last_progress_at,
                },
                "alerts": self._active_alerts,
            },
        }
