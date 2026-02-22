"""Runtime configuration control-plane utilities for workflow orchestrator."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


RUNTIME_KEY_REGISTRY: dict[str, dict[str, Any]] = {
    "orchestrator.polling_interval_seconds": {
        "type": "int",
        "min": 1,
        "max": 120,
        "mutability": "hot",
        "owner": "workflow_orchestrator",
        "apply_mode": "next_tick",
    },
    "orchestrator.max_concurrent_tasks": {
        "type": "int",
        "min": 1,
        "max": 200,
        "mutability": "hot",
        "owner": "workflow_orchestrator",
        "apply_mode": "next_tick",
    },
    "orchestrator.resource_limits.max_cpu_percent": {
        "type": "int",
        "min": 1,
        "max": 100,
        "mutability": "hot",
        "owner": "workflow_orchestrator",
        "apply_mode": "next_tick",
    },
    "orchestrator.resource_limits.max_memory_percent": {
        "type": "int",
        "min": 1,
        "max": 100,
        "mutability": "hot",
        "owner": "workflow_orchestrator",
        "apply_mode": "next_tick",
    },
    "orchestrator.resource_limits.max_gpu_utilization": {
        "type": "int",
        "min": 1,
        "max": 100,
        "mutability": "hot",
        "owner": "workflow_orchestrator",
        "apply_mode": "next_tick",
    },
    "orchestrator.resource_limits.max_gpu_memory_percent": {
        "type": "int",
        "min": 1,
        "max": 100,
        "mutability": "hot",
        "owner": "workflow_orchestrator",
        "apply_mode": "next_tick",
    },
    "orchestrator.lane_policy.enabled": {
        "type": "bool",
        "mutability": "hot",
        "owner": "workflow_orchestrator",
        "apply_mode": "next_tick",
    },
    "orchestrator.lane_policy.min_article_count": {
        "type": "int",
        "min": 1,
        "max": 10,
        "mutability": "hot",
        "owner": "workflow_orchestrator",
        "apply_mode": "next_tick",
    },
    "orchestrator.lane_policy.min_source_count": {
        "type": "int",
        "min": 1,
        "max": 10,
        "mutability": "hot",
        "owner": "workflow_orchestrator",
        "apply_mode": "next_tick",
    },
    "orchestrator.lane_policy.min_unique_domains": {
        "type": "int",
        "min": 1,
        "max": 10,
        "mutability": "hot",
        "owner": "workflow_orchestrator",
        "apply_mode": "next_tick",
    },
    "orchestrator.lane_policy.version": {
        "type": "str",
        "mutability": "hot",
        "owner": "workflow_orchestrator",
        "apply_mode": "next_tick",
    },
    "orchestrator.lane_policy.topic_overrides_json": {
        "type": "str",
        "mutability": "hot",
        "owner": "workflow_orchestrator",
        "apply_mode": "next_tick",
    },
    "mcp_bus.call.read_timeout_sec": {
        "type": "float",
        "min": 0.1,
        "max": 300.0,
        "mutability": "hot",
        "owner": "mcp_bus",
        "apply_mode": "next_request",
    },
    "mcp_bus.call.max_retries": {
        "type": "int",
        "min": 0,
        "max": 10,
        "mutability": "hot",
        "owner": "mcp_bus",
        "apply_mode": "next_request",
    },
    "fact_checker.search.max_queries": {
        "type": "int",
        "min": 1,
        "max": 20,
        "mutability": "hot",
        "owner": "fact_checker",
        "apply_mode": "next_request",
    },
    "fact_checker.search.deep_crawl_timeout_sec": {
        "type": "float",
        "min": 0.1,
        "max": 60.0,
        "mutability": "hot",
        "owner": "fact_checker",
        "apply_mode": "next_request",
    },
    "analyst.workers": {
        "type": "int",
        "min": 1,
        "max": 16,
        "mutability": "restart_required",
        "owner": "analyst",
        "apply_mode": "restart",
    },
    "analyst.model.name": {
        "type": "str",
        "mutability": "restart_required",
        "owner": "analyst",
        "apply_mode": "restart",
    },
}


TIER_KEY_PREFIXES: dict[str, tuple[str, ...]] = {
    "tier1": ("orchestrator.",),
    "tier2": ("mcp_bus.call.",),
    "tier3": ("fact_checker.search.",),
}


@dataclass
class ValidationResult:
    ok: bool
    normalized: dict[str, Any]
    errors: list[str]
    warnings: list[str]
    blocked_non_hot: list[str]
    impacted_services: list[str]


class RuntimeConfigStore:
    def __init__(self, state_path: str | Path | None = None):
        self.state_path = Path(state_path or "config/runtime/runtime_config_state.json")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._state = self._load_state()

    def _default_state(self) -> dict[str, Any]:
        timestamp = _utc_now()
        return {
            "version": 0,
            "updated_at": timestamp,
            "overrides": {},
            "timeline": [
                {
                    "version": 0,
                    "operation": "init",
                    "reason": "initial_state",
                    "actor": "system",
                    "timestamp": timestamp,
                    "overrides": {},
                }
            ],
            "audit_log": [],
        }

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            state = self._default_state()
            self._save_state(state)
            return state

        try:
            with self.state_path.open("r", encoding="utf-8") as file_handle:
                loaded = json.load(file_handle)
            if not isinstance(loaded, dict):
                raise ValueError("runtime config state must be a JSON object")
            loaded.setdefault("version", 0)
            loaded.setdefault("updated_at", _utc_now())
            loaded.setdefault("overrides", {})
            loaded.setdefault("timeline", [])
            loaded.setdefault("audit_log", [])
            return loaded
        except Exception as exc:
            logger.warning(
                "Failed to load runtime config state from %s: %s. Resetting to defaults.",
                self.state_path,
                exc,
            )
            state = self._default_state()
            self._save_state(state)
            return state

    def _save_state(self, state: dict[str, Any]) -> None:
        with self.state_path.open("w", encoding="utf-8") as file_handle:
            json.dump(state, file_handle, indent=2, sort_keys=True)

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._state)

    def _key_tier(self, key: str) -> str | None:
        for tier_name, prefixes in TIER_KEY_PREFIXES.items():
            if any(key.startswith(prefix) for prefix in prefixes):
                return tier_name
        return None

    def validate_patch(self, patch: dict[str, Any]) -> ValidationResult:
        normalized: dict[str, Any] = {}
        errors: list[str] = []
        warnings: list[str] = []
        blocked_non_hot: list[str] = []
        impacted_services: set[str] = set()

        for key, raw_value in patch.items():
            metadata = RUNTIME_KEY_REGISTRY.get(key)
            if metadata is None:
                errors.append(f"Unknown runtime key: {key}")
                continue

            impacted_services.add(str(metadata.get("owner", "unknown")))
            mutability = str(metadata.get("mutability", "hot"))
            if mutability != "hot":
                blocked_non_hot.append(key)
                warnings.append(
                    f"{key} is {mutability}; runtime apply is blocked for non-hot keys"
                )
                continue

            expected_type = metadata.get("type")
            try:
                if expected_type == "int":
                    value = int(raw_value)
                elif expected_type == "float":
                    value = float(raw_value)
                elif expected_type == "bool":
                    if isinstance(raw_value, bool):
                        value = raw_value
                    else:
                        value = str(raw_value).strip().lower() in {
                            "1",
                            "true",
                            "yes",
                            "on",
                        }
                elif expected_type == "str":
                    value = str(raw_value)
                else:
                    value = raw_value
            except Exception:
                errors.append(
                    f"Invalid value for {key}: expected {expected_type}, got {raw_value!r}"
                )
                continue

            min_value = metadata.get("min")
            max_value = metadata.get("max")
            if min_value is not None and value < min_value:
                errors.append(f"{key} below minimum {min_value}")
                continue
            if max_value is not None and value > max_value:
                errors.append(f"{key} above maximum {max_value}")
                continue

            normalized[key] = value

        return ValidationResult(
            ok=not errors,
            normalized=normalized,
            errors=errors,
            warnings=warnings,
            blocked_non_hot=blocked_non_hot,
            impacted_services=sorted(impacted_services),
        )

    def apply_patch(
        self,
        patch: dict[str, Any],
        *,
        reason: str,
        actor: str = "operator",
    ) -> dict[str, Any]:
        if not patch:
            return {
                "status": "error",
                "errors": ["patch cannot be empty"],
                "warnings": [],
                "blocked_non_hot": [],
                "impacted_services": [],
            }

        validation = self.validate_patch(patch)
        if not validation.ok:
            return {
                "status": "error",
                "errors": validation.errors,
                "warnings": validation.warnings,
                "blocked_non_hot": validation.blocked_non_hot,
                "impacted_services": validation.impacted_services,
            }

        if validation.blocked_non_hot:
            return {
                "status": "error",
                "errors": [
                    "runtime apply rejected: patch includes non-hot keys"
                ],
                "warnings": validation.warnings,
                "blocked_non_hot": validation.blocked_non_hot,
                "impacted_services": validation.impacted_services,
            }

        if not validation.normalized:
            return {
                "status": "error",
                "errors": ["no hot runtime keys available to apply"],
                "warnings": validation.warnings,
                "blocked_non_hot": validation.blocked_non_hot,
                "impacted_services": validation.impacted_services,
            }

        with self._lock:
            prev_version = int(self._state.get("version", 0))
            current_overrides = dict(self._state.get("overrides", {}))
            merged = dict(current_overrides)
            merged.update(validation.normalized)
            new_version = prev_version + 1
            timestamp = _utc_now()

            inverse_patch: dict[str, Any] = {}
            for key in validation.normalized.keys():
                if key in current_overrides:
                    inverse_patch[key] = current_overrides[key]

            self._state["version"] = new_version
            self._state["updated_at"] = timestamp
            self._state["overrides"] = merged

            self._state.setdefault("timeline", []).append(
                {
                    "version": new_version,
                    "previous_version": prev_version,
                    "operation": "apply",
                    "reason": reason,
                    "actor": actor,
                    "timestamp": timestamp,
                    "patch": validation.normalized,
                    "inverse_rollback": {
                        "method": "rollback_to_version",
                        "target_version": prev_version,
                        "inverse_patch": inverse_patch,
                    },
                    "tiers": sorted(
                        {
                            self._key_tier(key)
                            for key in validation.normalized.keys()
                            if self._key_tier(key) is not None
                        }
                    ),
                    "overrides": deepcopy(merged),
                }
            )

            self._state.setdefault("audit_log", []).append(
                {
                    "version": new_version,
                    "previous_version": prev_version,
                    "operation": "apply",
                    "reason": reason,
                    "actor": actor,
                    "timestamp": timestamp,
                    "patch": validation.normalized,
                    "warnings": validation.warnings,
                }
            )

            self._save_state(self._state)

            return {
                "status": "ok",
                "version": new_version,
                "previous_version": prev_version,
                "applied": validation.normalized,
                "warnings": validation.warnings,
                "blocked_non_hot": validation.blocked_non_hot,
                "impacted_services": validation.impacted_services,
                "inverse_rollback": {
                    "method": "rollback_to_version",
                    "target_version": prev_version,
                    "inverse_patch": inverse_patch,
                },
                "updated_at": timestamp,
            }

    def apply_tier_patch(
        self,
        tier: str,
        patch: dict[str, Any],
        *,
        reason: str,
        actor: str = "operator",
    ) -> dict[str, Any]:
        tier_name = str(tier or "").strip().lower()
        allowed_prefixes = TIER_KEY_PREFIXES.get(tier_name)
        if allowed_prefixes is None:
            return {
                "status": "error",
                "errors": [f"unknown tier: {tier}"],
                "warnings": [],
                "blocked_non_hot": [],
                "impacted_services": [],
            }

        disallowed = [
            key
            for key in patch.keys()
            if not any(key.startswith(prefix) for prefix in allowed_prefixes)
        ]
        if disallowed:
            return {
                "status": "error",
                "errors": ["patch contains keys outside selected tier"],
                "warnings": [],
                "blocked_non_hot": [],
                "impacted_services": [],
                "disallowed_keys": disallowed,
            }

        result = self.apply_patch(patch, reason=reason, actor=actor)
        if result.get("status") == "ok":
            result["tier"] = tier_name
        return result

    def rollback(
        self,
        target_version: int,
        *,
        reason: str,
        actor: str = "operator",
    ) -> dict[str, Any]:
        with self._lock:
            timeline = self._state.get("timeline", [])
            target_entry = next(
                (item for item in timeline if int(item.get("version", -1)) == int(target_version)),
                None,
            )
            if target_entry is None:
                return {
                    "status": "error",
                    "message": f"target version {target_version} not found",
                }

            target_overrides = dict(target_entry.get("overrides", {}))
            prev_version = int(self._state.get("version", 0))
            new_version = prev_version + 1
            timestamp = _utc_now()

            self._state["version"] = new_version
            self._state["updated_at"] = timestamp
            self._state["overrides"] = target_overrides

            self._state.setdefault("timeline", []).append(
                {
                    "version": new_version,
                    "operation": "rollback",
                    "reason": reason,
                    "actor": actor,
                    "timestamp": timestamp,
                    "rollback_target_version": int(target_version),
                    "overrides": deepcopy(target_overrides),
                }
            )

            self._state.setdefault("audit_log", []).append(
                {
                    "version": new_version,
                    "operation": "rollback",
                    "reason": reason,
                    "actor": actor,
                    "timestamp": timestamp,
                    "rollback_target_version": int(target_version),
                }
            )

            self._save_state(self._state)

            return {
                "status": "ok",
                "version": new_version,
                "previous_version": prev_version,
                "rollback_target_version": int(target_version),
                "updated_at": timestamp,
            }

    def rollback_apply_version(
        self,
        apply_version: int,
        *,
        reason: str,
        actor: str = "operator",
    ) -> dict[str, Any]:
        state = self.get_state()
        timeline = state.get("timeline", [])
        apply_entry = next(
            (
                entry
                for entry in timeline
                if int(entry.get("version", -1)) == int(apply_version)
                and entry.get("operation") == "apply"
            ),
            None,
        )
        if apply_entry is None:
            return {
                "status": "error",
                "message": f"apply version {apply_version} not found",
            }

        target_version = int(apply_entry.get("previous_version", -1))
        if target_version < 0:
            return {
                "status": "error",
                "message": f"apply version {apply_version} has no previous_version",
            }

        rollback_result = self.rollback(
            target_version,
            reason=reason,
            actor=actor,
        )
        if rollback_result.get("status") == "ok":
            rollback_result["inverse_of_apply_version"] = int(apply_version)
        return rollback_result


def extract_owner_overrides(overrides: dict[str, Any], owner: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in overrides.items():
        metadata = RUNTIME_KEY_REGISTRY.get(key)
        if metadata and metadata.get("owner") == owner:
            result[key] = value
    return result


def get_lane_policy_runtime_examples() -> dict[str, Any]:
    """Return canonical runtime-config payload examples for lane policy operations."""
    return {
        "owner": "workflow_orchestrator",
        "notes": {
            "validate_first": "Use /runtime-config/validate before /runtime-config",
            "rollback": "Use /runtime-config/rollback with target_version from /runtime-config available_versions",
        },
        "examples": {
            "enable_dev_baseline": {
                "patch": {
                    "orchestrator.lane_policy.enabled": True,
                    "orchestrator.lane_policy.min_article_count": 2,
                    "orchestrator.lane_policy.min_source_count": 2,
                    "orchestrator.lane_policy.min_unique_domains": 2,
                    "orchestrator.lane_policy.version": "v1-dev",
                },
                "reason": "enable lane policy for dev burn-in",
                "actor": "ops",
            },
            "disable_safety_hold": {
                "patch": {
                    "orchestrator.lane_policy.enabled": False,
                    "orchestrator.lane_policy.version": "v1-hold",
                },
                "reason": "temporary hold for quality investigation",
                "actor": "ops",
            },
            "canary_tighten_thresholds": {
                "patch": {
                    "orchestrator.lane_policy.enabled": True,
                    "orchestrator.lane_policy.min_article_count": 3,
                    "orchestrator.lane_policy.min_source_count": 3,
                    "orchestrator.lane_policy.min_unique_domains": 3,
                    "orchestrator.lane_policy.version": "v2-canary",
                },
                "reason": "canary threshold increase",
                "actor": "ops",
            },
            "sparse_topic_relief": {
                "patch": {
                    "orchestrator.lane_policy.enabled": True,
                    "orchestrator.lane_policy.min_article_count": 1,
                    "orchestrator.lane_policy.min_source_count": 2,
                    "orchestrator.lane_policy.min_unique_domains": 1,
                    "orchestrator.lane_policy.version": "v2-sparse-topic",
                },
                "reason": "sparse topic relief tuning",
                "actor": "ops",
            },
        },
    }
