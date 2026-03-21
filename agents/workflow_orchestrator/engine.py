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


AUTONOMIC_REASON_METADATA: dict[str, dict[str, str]] = {
    "stable_no_change": {
        "reason_code": "AUTO_NO_CHANGE_STABLE",
        "reason_detail": "System healthy and making progress; no bounded action required.",
        "expected_effect": "Hold current runtime settings.",
    },
    "resource_pressure": {
        "reason_code": "AUTO_SCALE_DOWN_RESOURCE_PRESSURE",
        "reason_detail": "Resource pressure detected near configured limits.",
        "expected_effect": "Reduce task pressure and slow polling to stabilize.",
    },
    "downstream_stall_recovery": {
        "reason_code": "AUTO_SCALE_UP_STALL_RECOVERY",
        "reason_detail": "Downstream progress stalled while resources remain healthy.",
        "expected_effect": "Increase task pressure and tighten polling to recover flow.",
    },
    "feature_flag_disabled": {
        "reason_code": "AUTO_DISABLED_BY_FLAG",
        "reason_detail": "Autonomic decisions are disabled by configuration.",
        "expected_effect": "No decisioning or actuation.",
    },
    "mode_disabled": {
        "reason_code": "AUTO_MODE_DISABLED",
        "reason_detail": "Autonomic mode set to disabled.",
        "expected_effect": "No decisioning or actuation.",
    },
    "oscillation_damping_hold": {
        "reason_code": "AUTO_DAMPING_HOLD",
        "reason_detail": "Transient pressure/stall signal did not meet damping threshold.",
        "expected_effect": "Hold current runtime settings to avoid oscillation.",
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        return default

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
        self.autonomic_action_streak_required = max(
            1,
            int(os.environ.get("AUTONOMIC_ACTION_STREAK_REQUIRED", "2")),
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
        self._autonomic_last_candidate_reason: str | None = None
        self._autonomic_candidate_reason_streak = 0
        self.pressure_weighted_ordering_enabled = _env_bool(
            "ORCH_PRESSURE_WEIGHTED_ORDERING_ENABLED", default=False
        )
        self.pressure_weighted_zero_score_floor = max(
            0.0,
            float(os.environ.get("ORCH_PRESSURE_WEIGHTED_ZERO_SCORE_FLOOR", "0.0")),
        )
        self.fairness_budget_enabled = _env_bool(
            "ORCH_FAIRNESS_BUDGET_ENABLED", default=True
        )
        self.fairness_idle_accrual = max(
            0.0,
            float(os.environ.get("ORCH_FAIRNESS_IDLE_ACCRUAL", "0.05")),
        )
        self.fairness_backlog_accrual = max(
            0.0,
            float(os.environ.get("ORCH_FAIRNESS_BACKLOG_ACCRUAL", "1.0")),
        )
        self.fairness_served_item_cost = max(
            0.0,
            float(os.environ.get("ORCH_FAIRNESS_SERVED_ITEM_COST", "1.0")),
        )
        self.fairness_starvation_boost = max(
            0.0,
            float(os.environ.get("ORCH_FAIRNESS_STARVATION_BOOST", "0.25")),
        )
        self.fairness_max_deficit = max(
            1.0,
            float(os.environ.get("ORCH_FAIRNESS_MAX_DEFICIT", "25.0")),
        )
        self.fairness_min_deficit = max(
            0.0,
            float(os.environ.get("ORCH_FAIRNESS_MIN_DEFICIT", "0.0")),
        )
        self.fairness_pressure_weight = max(
            0.0,
            float(os.environ.get("ORCH_FAIRNESS_PRESSURE_WEIGHT", "0.35")),
        )
        self.dynamic_policy_limits_enabled = _env_bool(
            "ORCH_DYNAMIC_POLICY_LIMITS_ENABLED", default=False
        )
        self.dynamic_policy_limit_up_delta = max(
            0,
            int(os.environ.get("ORCH_DYNAMIC_POLICY_LIMIT_UP_DELTA", "1")),
        )
        self.dynamic_policy_limit_down_delta = max(
            0,
            int(os.environ.get("ORCH_DYNAMIC_POLICY_LIMIT_DOWN_DELTA", "1")),
        )
        self.dynamic_policy_limit_cooldown_seconds = max(
            10,
            int(os.environ.get("ORCH_DYNAMIC_POLICY_LIMIT_COOLDOWN_SECONDS", "120")),
        )
        self.dynamic_policy_limit_scale_up_queue_depth = max(
            1,
            int(os.environ.get("ORCH_DYNAMIC_POLICY_LIMIT_SCALE_UP_QUEUE_DEPTH", "4")),
        )
        self.dynamic_policy_limit_scale_down_queue_depth = max(
            0,
            int(os.environ.get("ORCH_DYNAMIC_POLICY_LIMIT_SCALE_DOWN_QUEUE_DEPTH", "0")),
        )
        self.dynamic_policy_limit_max_error_rate = min(
            1.0,
            max(
                0.0,
                float(os.environ.get("ORCH_DYNAMIC_POLICY_LIMIT_MAX_ERROR_RATE", "0.20")),
            ),
        )
        self.dynamic_policy_limit_recent_error_cooldown_seconds = max(
            10,
            int(
                os.environ.get(
                    "ORCH_DYNAMIC_POLICY_LIMIT_RECENT_ERROR_COOLDOWN_SECONDS", "180"
                )
            ),
        )
        self.dynamic_policy_parallelism_enabled = _env_bool(
            "ORCH_DYNAMIC_POLICY_PARALLELISM_ENABLED", default=False
        )
        self.dynamic_policy_parallelism_up_delta = max(
            0,
            int(os.environ.get("ORCH_DYNAMIC_POLICY_PARALLELISM_UP_DELTA", "1")),
        )
        self.dynamic_policy_parallelism_down_delta = max(
            0,
            int(os.environ.get("ORCH_DYNAMIC_POLICY_PARALLELISM_DOWN_DELTA", "1")),
        )
        self.dynamic_policy_parallelism_cooldown_seconds = max(
            10,
            int(
                os.environ.get(
                    "ORCH_DYNAMIC_POLICY_PARALLELISM_COOLDOWN_SECONDS", "180"
                )
            ),
        )
        self.dynamic_policy_parallelism_scale_up_queue_depth = max(
            1,
            int(
                os.environ.get(
                    "ORCH_DYNAMIC_POLICY_PARALLELISM_SCALE_UP_QUEUE_DEPTH", "6"
                )
            ),
        )
        self.dynamic_policy_parallelism_scale_down_queue_depth = max(
            0,
            int(
                os.environ.get(
                    "ORCH_DYNAMIC_POLICY_PARALLELISM_SCALE_DOWN_QUEUE_DEPTH", "0"
                )
            ),
        )
        self.dynamic_policy_parallelism_max_error_rate = min(
            1.0,
            max(
                0.0,
                float(
                    os.environ.get(
                        "ORCH_DYNAMIC_POLICY_PARALLELISM_MAX_ERROR_RATE", "0.20"
                    )
                ),
            ),
        )
        self.dynamic_policy_parallelism_recent_error_cooldown_seconds = max(
            10,
            int(
                os.environ.get(
                    "ORCH_DYNAMIC_POLICY_PARALLELISM_RECENT_ERROR_COOLDOWN_SECONDS",
                    "180",
                )
            ),
        )
        self.dynamic_policy_parallelism_absolute_max = max(
            1,
            int(
                os.environ.get(
                    "ORCH_DYNAMIC_POLICY_PARALLELISM_ABSOLUTE_MAX", "4"
                )
            ),
        )
        self._dynamic_limit_state: dict[str, dict[str, Any]] = {}
        self._dynamic_parallelism_state: dict[str, dict[str, Any]] = {}
        self._fairness_state: dict[str, dict[str, Any]] = {}
        self._last_fairness_snapshot: dict[str, Any] = {
            "enabled": self.fairness_budget_enabled,
            "mode": "disabled",
            "policies": {},
            "computed_at": None,
        }
        self._last_policy_order_plan: dict[str, Any] = {
            "mode": "static",
            "ordered_policies": [],
            "scores": {},
            "fairness": self._last_fairness_snapshot,
            "computed_at": None,
        }
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

    def _reason_metadata(self, reason: str | None) -> dict[str, str]:
        if reason and reason in AUTONOMIC_REASON_METADATA:
            return AUTONOMIC_REASON_METADATA[reason]
        return {
            "reason_code": "AUTO_UNKNOWN_REASON",
            "reason_detail": "Reason not classified by current taxonomy.",
            "expected_effect": "No expectation available.",
        }

    def _build_queue_pressure_state(self) -> dict[str, Any]:
        now_epoch = time.time()
        policies: dict[str, Any] = {}
        total_queue_depth = 0
        max_queue_depth = 0
        hottest_policy = None
        hottest_pressure = -1.0

        for policy_name, policy_data in self.telemetry.get("policies", {}).items():
            queue_depth = int(policy_data.get("last_queue_depth", 0) or 0)
            total_queue_depth += queue_depth
            max_queue_depth = max(max_queue_depth, queue_depth)

            last_success_epoch = policy_data.get("last_success_at_epoch")
            queue_age_seconds = None
            if queue_depth > 0:
                if last_success_epoch is not None:
                    queue_age_seconds = max(0.0, now_epoch - float(last_success_epoch))
                else:
                    queue_age_seconds = 0.0

            check_count = int(policy_data.get("check_count", 0) or 0)
            error_count = int(policy_data.get("error_count", 0) or 0)
            error_rate = (float(error_count) / float(check_count)) if check_count > 0 else 0.0
            last_execute_ms = float(policy_data.get("last_execute_ms", 0.0) or 0.0)
            pressure_score = float(queue_depth) + ((queue_age_seconds or 0.0) / 30.0)

            if pressure_score > hottest_pressure:
                hottest_pressure = pressure_score
                hottest_policy = policy_name

            policies[policy_name] = {
                "queue_depth": queue_depth,
                "queue_age_seconds": round(queue_age_seconds, 3)
                if queue_age_seconds is not None
                else None,
                "error_rate": round(error_rate, 4),
                "last_execute_ms": round(last_execute_ms, 3),
                "pressure_score": round(pressure_score, 3),
            }

        return {
            "total_queue_depth": total_queue_depth,
            "max_queue_depth": max_queue_depth,
            "hottest_policy": hottest_policy,
            "hottest_pressure_score": round(hottest_pressure, 3)
            if hottest_pressure >= 0
            else None,
            "policies": policies,
        }

    def _estimate_decision_confidence(
        self,
        reason: str,
        proposed_patch: dict[str, Any],
        inputs: dict[str, Any],
    ) -> float:
        score = 0.55
        if reason == "stable_no_change":
            score += 0.2
        if reason == "oscillation_damping_hold":
            score += 0.1
        if inputs.get("resource_healthy", True):
            score += 0.1
        if inputs.get("stalled", False):
            score -= 0.15
        if not proposed_patch:
            score += 0.05
        return round(max(0.0, min(1.0, score)), 3)

    def _ensure_fairness_state(self, policy_name: str) -> dict[str, Any]:
        self._fairness_state.setdefault(
            policy_name,
            {
                "deficit": self.fairness_min_deficit,
                "served_total": 0,
                "starvation_ticks": 0,
                "last_served_at": None,
                "last_queue_depth": 0,
                "last_priority": 0.0,
            },
        )
        return self._fairness_state[policy_name]

    def _apply_fairness_budget(
        self,
        ordered: list[WorkflowPolicy],
        pressure_scores: dict[str, float],
        base_order: dict[str, int],
    ) -> list[WorkflowPolicy]:
        if not self.fairness_budget_enabled:
            self._last_fairness_snapshot = {
                "enabled": False,
                "mode": "disabled",
                "policies": {},
                "computed_at": _utc_now(),
            }
            return ordered

        policies_snapshot: dict[str, Any] = {}
        for policy in ordered:
            policy_name = policy.name()
            state = self._ensure_fairness_state(policy_name)
            policy_telemetry = self.telemetry.get("policies", {}).get(policy_name, {})
            last_queue_depth = int(policy_telemetry.get("last_queue_depth", 0) or 0)
            accrual = (
                self.fairness_backlog_accrual
                if last_queue_depth > 0
                else self.fairness_idle_accrual
            )

            state["last_queue_depth"] = last_queue_depth
            state["deficit"] = min(
                self.fairness_max_deficit,
                max(self.fairness_min_deficit, float(state.get("deficit", 0.0)) + accrual),
            )
            priority = float(state["deficit"]) + (
                self.fairness_pressure_weight * float(pressure_scores.get(policy_name, 0.0))
            )
            state["last_priority"] = round(priority, 4)
            policies_snapshot[policy_name] = {
                "deficit": round(float(state["deficit"]), 4),
                "queue_depth": last_queue_depth,
                "pressure_score": round(float(pressure_scores.get(policy_name, 0.0)), 4),
                "priority": round(priority, 4),
                "starvation_ticks": int(state.get("starvation_ticks", 0)),
                "served_total": int(state.get("served_total", 0)),
            }

        ordered = sorted(
            ordered,
            key=lambda policy: (
                -float(self._fairness_state[policy.name()].get("last_priority", 0.0)),
                base_order.get(policy.name(), 0),
            ),
        )
        self._last_fairness_snapshot = {
            "enabled": True,
            "mode": "deficit_weighted",
            "policies": policies_snapshot,
            "computed_at": _utc_now(),
        }
        return ordered

    def _record_fairness_consumption(self, policy_name: str, served_items: int, queue_depth: int) -> None:
        if not self.fairness_budget_enabled:
            return

        state = self._ensure_fairness_state(policy_name)
        deficit = float(state.get("deficit", self.fairness_min_deficit))
        if served_items > 0:
            deficit = max(
                self.fairness_min_deficit,
                deficit - (float(served_items) * self.fairness_served_item_cost),
            )
            state["served_total"] = int(state.get("served_total", 0)) + int(served_items)
            state["starvation_ticks"] = 0
            state["last_served_at"] = _utc_now()
        elif queue_depth > 0:
            starvation_ticks = int(state.get("starvation_ticks", 0)) + 1
            state["starvation_ticks"] = starvation_ticks
            deficit = min(
                self.fairness_max_deficit,
                deficit + (self.fairness_starvation_boost * float(starvation_ticks)),
            )
        else:
            state["starvation_ticks"] = 0

        state["deficit"] = min(
            self.fairness_max_deficit,
            max(self.fairness_min_deficit, deficit),
        )

    def _ordered_policies_for_tick(self) -> list[WorkflowPolicy]:
        ordered = list(self.policies)
        base_order = {policy.name(): idx for idx, policy in enumerate(self.policies)}
        queue_pressure = self._build_queue_pressure_state().get("policies", {})
        scores: dict[str, float] = {}
        for policy in ordered:
            name = policy.name()
            score = float((queue_pressure.get(name) or {}).get("pressure_score", 0.0) or 0.0)
            scores[name] = max(self.pressure_weighted_zero_score_floor, score)

        if not self.pressure_weighted_ordering_enabled:
            ordered = self._apply_fairness_budget(ordered, scores, base_order)
            mode = "static"
            if self.fairness_budget_enabled:
                mode = "static+fairness"
            self._last_policy_order_plan = {
                "mode": mode,
                "ordered_policies": [p.name() for p in ordered],
                "scores": {p.name(): round(scores.get(p.name(), 0.0), 3) for p in ordered},
                "fairness": self._last_fairness_snapshot,
                "computed_at": _utc_now(),
            }
            return ordered

        if all(score <= 0.0 for score in scores.values()):
            ordered = self._apply_fairness_budget(ordered, scores, base_order)
            mode = "weighted_fallback_static"
            if self.fairness_budget_enabled:
                mode = "weighted_fallback_static+fairness"
            self._last_policy_order_plan = {
                "mode": mode,
                "ordered_policies": [p.name() for p in ordered],
                "scores": {name: round(value, 3) for name, value in scores.items()},
                "fairness": self._last_fairness_snapshot,
                "computed_at": _utc_now(),
            }
            return ordered

        ordered = sorted(
            ordered,
            key=lambda policy: (
                -scores.get(policy.name(), 0.0),
                base_order.get(policy.name(), 0),
            ),
        )
        ordered = self._apply_fairness_budget(ordered, scores, base_order)
        mode = "weighted"
        if self.fairness_budget_enabled:
            mode = "weighted+fairness"
        self._last_policy_order_plan = {
            "mode": mode,
            "ordered_policies": [p.name() for p in ordered],
            "scores": {name: round(value, 3) for name, value in scores.items()},
            "fairness": self._last_fairness_snapshot,
            "computed_at": _utc_now(),
        }
        return ordered

    def _policy_batch_limit(self, policy_name: str, default_limit: int) -> int:
        capped_default_map = {
            "ingestion_to_analysis": 6,
            "analysis_to_summary": 3,
            "analysis_to_fact_check": 4,
            "incremental_clustering": 8,
            "cluster_to_synthesis": 4,
            "synthesis_to_publishing": 6,
        }
        fallback = min(default_limit, capped_default_map.get(policy_name, default_limit))
        env_key = f"ORCH_POLICY_LIMIT_{policy_name.upper()}"
        raw = os.environ.get(env_key)
        static_limit = max(1, fallback)
        if raw is None:
            return self._compute_dynamic_policy_limit(policy_name, static_limit, default_limit)
        try:
            static_limit = max(1, min(default_limit, int(raw)))
        except Exception:
            static_limit = max(1, fallback)

        return self._compute_dynamic_policy_limit(policy_name, static_limit, default_limit)

    def _compute_dynamic_policy_limit(
        self,
        policy_name: str,
        static_limit: int,
        absolute_max_limit: int,
    ) -> int:
        if not self.dynamic_policy_limits_enabled:
            return static_limit

        now_epoch = time.time()
        policy_telemetry = self.telemetry.get("policies", {}).get(policy_name, {})
        queue_depth = int(policy_telemetry.get("last_queue_depth", 0) or 0)
        check_count = int(policy_telemetry.get("check_count", 0) or 0)
        error_count = int(policy_telemetry.get("error_count", 0) or 0)
        error_rate = (float(error_count) / float(check_count)) if check_count > 0 else 0.0

        state = self._dynamic_limit_state.setdefault(
            policy_name,
            {
                "current_limit": int(static_limit),
                "last_adjust_epoch": None,
                "last_reason": "init",
                "min_cap": int(static_limit),
                "max_cap": int(static_limit),
            },
        )

        min_cap = max(1, int(static_limit) - int(self.dynamic_policy_limit_down_delta))
        max_cap = min(
            int(absolute_max_limit),
            int(static_limit) + int(self.dynamic_policy_limit_up_delta),
        )
        max_cap = max(min_cap, max_cap)

        current_limit = int(state.get("current_limit", static_limit) or static_limit)
        current_limit = max(min_cap, min(max_cap, current_limit))

        last_adjust_epoch = state.get("last_adjust_epoch")
        can_adjust = (
            last_adjust_epoch is None
            or (now_epoch - float(last_adjust_epoch)) >= self.dynamic_policy_limit_cooldown_seconds
        )

        recent_error = False
        last_error_at = policy_telemetry.get("last_error_at")
        if last_error_at:
            try:
                parsed = datetime.fromisoformat(str(last_error_at).replace("Z", "+00:00"))
                age_seconds = max(0.0, now_epoch - parsed.astimezone(timezone.utc).timestamp())
                recent_error = (
                    age_seconds < self.dynamic_policy_limit_recent_error_cooldown_seconds
                )
            except Exception:
                recent_error = False

        desired_limit = current_limit
        reason = "hold"
        if queue_depth >= self.dynamic_policy_limit_scale_up_queue_depth:
            if error_rate <= self.dynamic_policy_limit_max_error_rate and not recent_error:
                desired_limit = min(max_cap, current_limit + 1)
                reason = "scale_up_queue_pressure"
            else:
                reason = "hold_error_guardrail"
        elif queue_depth <= self.dynamic_policy_limit_scale_down_queue_depth:
            desired_limit = max(min_cap, current_limit - 1)
            reason = "scale_down_idle_queue"

        if desired_limit != current_limit:
            if can_adjust:
                current_limit = desired_limit
                state["last_adjust_epoch"] = now_epoch
            else:
                reason = "hold_cooldown"

        state["current_limit"] = int(current_limit)
        state["last_reason"] = str(reason)
        state["min_cap"] = int(min_cap)
        state["max_cap"] = int(max_cap)
        state["queue_depth"] = int(queue_depth)
        state["error_rate"] = round(float(error_rate), 4)
        state["recent_error"] = bool(recent_error)

        return int(current_limit)

    def _compute_dynamic_policy_parallelism(
        self,
        policy_name: str,
        observed_queue_depth: int,
    ) -> int | None:
        if not self.dynamic_policy_parallelism_enabled:
            return None

        default_parallelism = max(
            1,
            _env_int("ORCH_POLICY_EXECUTION_PARALLELISM_DEFAULT", 2),
        )
        env_key = f"ORCH_POLICY_EXECUTION_PARALLELISM_{policy_name.upper()}"
        static_parallelism = max(
            1,
            _env_int(env_key, default_parallelism),
        )

        now_epoch = time.time()
        policy_telemetry = self.telemetry.get("policies", {}).get(policy_name, {})
        check_count = int(policy_telemetry.get("check_count", 0) or 0)
        error_count = int(policy_telemetry.get("error_count", 0) or 0)
        error_rate = (float(error_count) / float(check_count)) if check_count > 0 else 0.0

        state = self._dynamic_parallelism_state.setdefault(
            policy_name,
            {
                "current_parallelism": int(static_parallelism),
                "last_adjust_epoch": None,
                "last_reason": "init",
                "min_cap": int(static_parallelism),
                "max_cap": int(static_parallelism),
            },
        )

        min_cap = max(1, int(static_parallelism) - int(self.dynamic_policy_parallelism_down_delta))
        max_cap = min(
            self.dynamic_policy_parallelism_absolute_max,
            int(static_parallelism) + int(self.dynamic_policy_parallelism_up_delta),
        )
        max_cap = max(min_cap, max_cap)

        current_parallelism = int(
            state.get("current_parallelism", static_parallelism) or static_parallelism
        )
        current_parallelism = max(min_cap, min(max_cap, current_parallelism))

        last_adjust_epoch = state.get("last_adjust_epoch")
        can_adjust = (
            last_adjust_epoch is None
            or (now_epoch - float(last_adjust_epoch))
            >= self.dynamic_policy_parallelism_cooldown_seconds
        )

        recent_error = False
        last_error_at = policy_telemetry.get("last_error_at")
        if last_error_at:
            try:
                parsed = datetime.fromisoformat(str(last_error_at).replace("Z", "+00:00"))
                age_seconds = max(0.0, now_epoch - parsed.astimezone(timezone.utc).timestamp())
                recent_error = (
                    age_seconds
                    < self.dynamic_policy_parallelism_recent_error_cooldown_seconds
                )
            except Exception:
                recent_error = False

        desired_parallelism = current_parallelism
        reason = "hold"
        queue_depth = max(0, int(observed_queue_depth))
        if queue_depth >= self.dynamic_policy_parallelism_scale_up_queue_depth:
            if error_rate <= self.dynamic_policy_parallelism_max_error_rate and not recent_error:
                desired_parallelism = min(max_cap, current_parallelism + 1)
                reason = "scale_up_queue_pressure"
            else:
                reason = "hold_error_guardrail"
        elif queue_depth <= self.dynamic_policy_parallelism_scale_down_queue_depth:
            desired_parallelism = max(min_cap, current_parallelism - 1)
            reason = "scale_down_idle_queue"

        if desired_parallelism != current_parallelism:
            if can_adjust:
                current_parallelism = desired_parallelism
                state["last_adjust_epoch"] = now_epoch
            else:
                reason = "hold_cooldown"

        state["current_parallelism"] = int(current_parallelism)
        state["last_reason"] = str(reason)
        state["min_cap"] = int(min_cap)
        state["max_cap"] = int(max_cap)
        state["queue_depth"] = int(queue_depth)
        state["error_rate"] = round(float(error_rate), 4)
        state["recent_error"] = bool(recent_error)
        os.environ[env_key] = str(current_parallelism)

        return int(current_parallelism)

    def _apply_timeout_backpressure(self, policy_name: str, policy_limit: int) -> int:
        """Reduce policy pull size after recent timeout-like failures."""
        if not _env_bool("ORCH_TIMEOUT_BACKPRESSURE_ENABLED", default=True):
            return policy_limit

        policy_telemetry = self.telemetry.get("policies", {}).get(policy_name, {})
        last_error = str(policy_telemetry.get("last_error") or "").lower()
        last_error_at = policy_telemetry.get("last_error_at")
        if not last_error or not last_error_at:
            return policy_limit

        markers = ("timeout", "timed out", "read timeout", "openai-infer-failed")
        if not any(marker in last_error for marker in markers):
            return policy_limit

        try:
            parsed = datetime.fromisoformat(str(last_error_at).replace("Z", "+00:00"))
            age_seconds = max(
                0.0,
                time.time() - parsed.astimezone(timezone.utc).timestamp(),
            )
        except Exception:
            return policy_limit

        window_seconds = max(
            30,
            _env_int("ORCH_TIMEOUT_BACKPRESSURE_WINDOW_SECONDS", 300),
        )
        if age_seconds > window_seconds:
            return policy_limit

        throttle_limit = max(
            1,
            _env_int("ORCH_TIMEOUT_BACKPRESSURE_LIMIT", 2),
        )
        if throttle_limit < policy_limit:
            logger.warning(
                "Applying timeout backpressure for policy '%s': limit %s -> %s",
                policy_name,
                policy_limit,
                throttle_limit,
            )
        return min(policy_limit, throttle_limit)

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

        lane_policy_env_map = {
            "orchestrator.lane_policy.enabled": "MULTI_SOURCE_LANE_POLICY_ENABLED",
            "orchestrator.lane_policy.lane1_enabled": "MULTI_SOURCE_LANE1_ENABLED",
            "orchestrator.lane_policy.lane2_enabled": "MULTI_SOURCE_LANE2_ENABLED",
            "orchestrator.lane_policy.min_article_count": "MULTI_SOURCE_MIN_ARTICLE_COUNT",
            "orchestrator.lane_policy.min_source_count": "MULTI_SOURCE_MIN_SOURCE_COUNT",
            "orchestrator.lane_policy.min_unique_domains": "MULTI_SOURCE_MIN_UNIQUE_DOMAINS",
            "orchestrator.lane_policy.version": "MULTI_SOURCE_LANE_POLICY_VERSION",
            "orchestrator.lane_policy.topic_overrides_json": "MULTI_SOURCE_LANE_POLICY_TOPIC_OVERRIDES_JSON",
            "orchestrator.lane1.seed_count": "LANE1_BBC_SEED_COUNT",
            "orchestrator.lane1.max_related_per_seed": "LANE1_MAX_RELATED_PER_SEED",
            "orchestrator.lane1.ddg_enabled": "LANE1_DDG_ENABLED",
            "orchestrator.lane1.ddg_max_queries_per_seed": "LANE1_DDG_MAX_QUERIES_PER_SEED",
            "orchestrator.lane1.require_bbc_first": "LANE1_REQUIRE_BBC_FIRST",
            "orchestrator.balance_policy.enabled": "BALANCE_POLICY_ENABLED",
            "orchestrator.balance_policy.disputed_topics_hard_gate": "BALANCE_POLICY_DISPUTED_TOPICS_HARD_GATE",
            "orchestrator.balance_policy.min_distinct_sides": "BALANCE_POLICY_MIN_DISTINCT_SIDES",
            "orchestrator.balance_policy.allow_opinion_as_perspective": "BALANCE_POLICY_ALLOW_OPINION_AS_PERSPECTIVE",
            "orchestrator.balance_policy.allow_opinion_as_factual_corroboration": "BALANCE_POLICY_ALLOW_OPINION_AS_FACTUAL_CORROBORATION",
            "orchestrator.discovery.enabled": "UNIFIED_CRAWLER_DISCOVERY_ENABLED",
            "orchestrator.discovery.offsite_follow_enabled": "UNIFIED_CRAWLER_OFFSITE_FOLLOW_ENABLED",
            "orchestrator.discovery.provisional_ingest_enabled": "UNIFIED_CRAWLER_PROVISIONAL_INGEST_ENABLED",
            "orchestrator.discovery.whitelist_only_mode": "UNIFIED_CRAWLER_WHITELIST_ONLY_MODE",
        }

        for runtime_key, env_key in lane_policy_env_map.items():
            if runtime_key not in overrides:
                os.environ.pop(env_key, None)

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

                mapped_env = lane_policy_env_map.get(key)
                if mapped_env:
                    if isinstance(value, bool):
                        os.environ[mapped_env] = "1" if value else "0"
                    else:
                        os.environ[mapped_env] = str(value)

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

        queue_pressure = self._build_queue_pressure_state()

        candidate_reason = "stable_no_change"
        if pressure_detected:
            candidate_reason = "resource_pressure"
        elif stalled and self._last_resource_healthy:
            candidate_reason = "downstream_stall_recovery"

        if candidate_reason == self._autonomic_last_candidate_reason:
            self._autonomic_candidate_reason_streak += 1
        else:
            self._autonomic_candidate_reason_streak = 1
            self._autonomic_last_candidate_reason = candidate_reason

        damped = False
        streak_required = self.autonomic_action_streak_required
        if (
            candidate_reason in {"resource_pressure", "downstream_stall_recovery"}
            and self._autonomic_candidate_reason_streak < streak_required
        ):
            damped = True
            reason = "oscillation_damping_hold"
        else:
            reason = candidate_reason

        if reason == "resource_pressure":
            proposed_patch["orchestrator.max_concurrent_tasks"] = max(1, current_tasks - 1)
            proposed_patch["orchestrator.polling_interval_seconds"] = min(30, current_poll + 1)
        elif reason == "downstream_stall_recovery":
            proposed_patch["orchestrator.polling_interval_seconds"] = max(1, current_poll - 1)
            proposed_patch["orchestrator.max_concurrent_tasks"] = min(30, current_tasks + 1)

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
                "queue_pressure_summary": {
                    "total_queue_depth": queue_pressure.get("total_queue_depth", 0),
                    "max_queue_depth": queue_pressure.get("max_queue_depth", 0),
                    "hottest_policy": queue_pressure.get("hottest_policy"),
                    "hottest_pressure_score": queue_pressure.get(
                        "hottest_pressure_score"
                    ),
                },
                "damping": {
                    "candidate_reason": candidate_reason,
                    "candidate_reason_streak": self._autonomic_candidate_reason_streak,
                    "streak_required": streak_required,
                    "damped": damped,
                },
            },
        }

    def _run_autonomic_decision_cycle(self) -> None:
        now_epoch = time.time()
        decision = {
            "timestamp": _utc_now(),
            "mode": self.autonomic_mode,
            "enabled": self.autonomic_decisions_enabled,
            "reason": None,
            "reason_code": None,
            "reason_detail": None,
            "expected_effect": None,
            "proposed_patch": {},
            "candidate_actions": [],
            "rejected_actions": [],
            "confidence": 0.0,
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
        reason_meta = self._reason_metadata(str(decision.get("reason") or ""))
        decision["reason_code"] = reason_meta["reason_code"]
        decision["reason_detail"] = reason_meta["reason_detail"]
        decision["expected_effect"] = reason_meta["expected_effect"]
        decision["confidence"] = self._estimate_decision_confidence(
            str(decision.get("reason") or ""),
            decision["proposed_patch"],
            decision.get("inputs", {}),
        )

        if decision["proposed_patch"]:
            decision["candidate_actions"].append(
                {
                    "action_type": "runtime_patch",
                    "patch": decision["proposed_patch"],
                    "rationale": decision["reason_code"],
                }
            )

        if not decision["proposed_patch"]:
            decision["result"] = {"status": "noop", "message": "no bounded action"}
            decision["rejected_actions"].append(
                {
                    "action_type": "runtime_patch",
                    "reason": "no_candidate_action",
                }
            )
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
            if not cooldown_ok:
                decision["rejected_actions"].append(
                    {
                        "action_type": "runtime_patch",
                        "reason": "cooldown_block",
                    }
                )
            if not budget_ok:
                decision["rejected_actions"].append(
                    {
                        "action_type": "runtime_patch",
                        "reason": "action_budget_block",
                    }
                )
            if not denylist_ok:
                decision["rejected_actions"].append(
                    {
                        "action_type": "runtime_patch",
                        "reason": "denylist_block",
                        "blocked_keys": unknown_or_blocked_keys,
                    }
                )
            self._record_autonomic_decision(decision)
            return

        if self.autonomic_mode == "shadow":
            decision["result"] = {
                "status": "shadow",
                "message": "decision recorded without apply",
            }
            decision["rejected_actions"].append(
                {
                    "action_type": "runtime_patch",
                    "reason": "shadow_mode_no_apply",
                }
            )
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
        
        for policy in self._ordered_policies_for_tick():
            policy_name = policy.name()
            policy_telemetry = self._ensure_policy_telemetry(policy_name)
            check_started = time.time()
            # We treat max_tasks as a per-policy limit for simplicity v1
            try:
                policy_limit = self._policy_batch_limit(policy_name, max_tasks)
                policy_limit = self._apply_timeout_backpressure(policy_name, policy_limit)
                items = policy.check_condition(limit=policy_limit)
                policy_telemetry["check_count"] += 1
                policy_telemetry["last_checked_at"] = _utc_now()
                policy_telemetry["last_check_ms"] = round(
                    (time.time() - check_started) * 1000.0, 3
                )
                policy_telemetry["last_limit"] = int(policy_limit)
                dynamic_state = self._dynamic_limit_state.get(policy_name)
                policy_telemetry["dynamic_limit_enabled"] = self.dynamic_policy_limits_enabled
                if dynamic_state:
                    policy_telemetry["dynamic_limit"] = int(
                        dynamic_state.get("current_limit", policy_limit)
                    )
                    policy_telemetry["dynamic_limit_reason"] = str(
                        dynamic_state.get("last_reason", "unknown")
                    )
                    policy_telemetry["dynamic_limit_min_cap"] = int(
                        dynamic_state.get("min_cap", policy_limit)
                    )
                    policy_telemetry["dynamic_limit_max_cap"] = int(
                        dynamic_state.get("max_cap", policy_limit)
                    )
                    policy_telemetry["dynamic_limit_error_rate"] = float(
                        dynamic_state.get("error_rate", 0.0)
                    )
                    policy_telemetry["dynamic_limit_recent_error"] = bool(
                        dynamic_state.get("recent_error", False)
                    )
                policy_telemetry["last_queue_depth"] = len(items)
                policy_telemetry["total_items_seen"] += len(items)
                dynamic_parallelism = self._compute_dynamic_policy_parallelism(
                    policy_name,
                    len(items),
                )
                policy_telemetry[
                    "dynamic_parallelism_enabled"
                ] = self.dynamic_policy_parallelism_enabled
                if dynamic_parallelism is not None:
                    p_state = self._dynamic_parallelism_state.get(policy_name, {})
                    policy_telemetry["dynamic_parallelism"] = int(dynamic_parallelism)
                    policy_telemetry["dynamic_parallelism_reason"] = str(
                        p_state.get("last_reason", "unknown")
                    )
                    policy_telemetry["dynamic_parallelism_min_cap"] = int(
                        p_state.get("min_cap", dynamic_parallelism)
                    )
                    policy_telemetry["dynamic_parallelism_max_cap"] = int(
                        p_state.get("max_cap", dynamic_parallelism)
                    )
                    policy_telemetry["dynamic_parallelism_error_rate"] = float(
                        p_state.get("error_rate", 0.0)
                    )
                    policy_telemetry["dynamic_parallelism_recent_error"] = bool(
                        p_state.get("recent_error", False)
                    )
                if items:
                    logger.info(
                        "Policy '%s' matched %s items (limit=%s).",
                        policy_name,
                        len(items),
                        policy_limit,
                    )
                    execute_started = time.time()
                    await policy.execute(items)
                    self._record_fairness_consumption(policy_name, len(items), len(items))
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
                    self._record_fairness_consumption(policy_name, 0, 0)
                    pass
            except Exception as e:
                policy_telemetry["error_count"] += 1
                policy_telemetry["last_error"] = str(e)
                policy_telemetry["last_error_at"] = _utc_now()
                self._record_fairness_consumption(
                    policy_name,
                    0,
                    int(policy_telemetry.get("last_queue_depth", 0) or 0),
                )
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
        queue_pressure = self._build_queue_pressure_state()

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
                "queue_pressure": queue_pressure,
                "scheduler": self._last_policy_order_plan,
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
