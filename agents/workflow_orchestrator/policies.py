"""
Workflow Policies for the Orchestrator.

This module defines the abstract base class and concrete implementations
for data pipeline transitions.
"""

from abc import ABC, abstractmethod
from typing import List, Any, Awaitable, Callable
import requests
import asyncio
import os
import json
import uuid
import time
import hashlib
import statistics
import re
from urllib.parse import urlparse
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

from common.observability import get_logger
from common.metrics import get_metrics
from database.utils.migrated_database_utils import create_database_service
from agents.common.headline_adapter import HeadlineAdapter

logger = get_logger(__name__)
_ORCH_METRICS = get_metrics("workflow_orchestrator")
_LANE_METRIC_TOTALS: dict[str, int] = {
    "verified_story": 0,
    "developing_brief": 0,
}
_UNIQUE_DOMAIN_SAMPLES: list[int] = []
_SINGLETON_CONVERSION_SEEN: set[str] = set()

_HEADLINE_ADAPTER = HeadlineAdapter(name="orchestrator_title_llm")


def _generate_llm_title_candidates(synthesis_result: dict[str, Any] | None) -> list[str]:
    result = synthesis_result if isinstance(synthesis_result, dict) else {}
    summary = str(result.get("summary") or "").strip()
    key_points = result.get("key_points")
    key_points_text = ""
    if isinstance(key_points, list):
        key_points_text = "\n".join(f"- {str(item).strip()}" for item in key_points[:5] if str(item).strip())

    body = str(result.get("body") or "").strip()
    context = "\n".join(part for part in [summary, key_points_text, body[:1500]] if part).strip()
    if not context:
        return []
    return _HEADLINE_ADAPTER.generate_candidates(context)


def _derive_story_title(
    cluster_id: str,
    synthesis_result: dict[str, Any] | None,
    *,
    is_brief: bool = False,
) -> str:
    result = synthesis_result if isinstance(synthesis_result, dict) else {}

    candidates: list[Any] = []
    candidates.extend(_generate_llm_title_candidates(result))

    qwen_payload = result.get("qwen")
    if isinstance(qwen_payload, dict):
        candidates.extend(
            [
                qwen_payload.get("headline"),
                qwen_payload.get("title"),
                qwen_payload.get("topic_title"),
            ]
        )

    candidates.extend(
        [
            result.get("headline"),
            result.get("title"),
            result.get("topic_title"),
            result.get("summary"),
        ]
    )

    key_points = result.get("key_points")
    if isinstance(key_points, list) and key_points:
        candidates.append(key_points[0])

    disallowed = re.compile(r"^\s*(\[brief\]\s*)?synthesis report\s*:", re.IGNORECASE)
    headline = HeadlineAdapter.select_best_headline(
        candidates,
        min_len=10,
        disallowed_pattern=disallowed,
    )
    if headline:
        return headline

    if is_brief:
        return f"Brief Update: {cluster_id}"
    return f"Developing Story: {cluster_id}"


def _safe_json_list(raw_value: Any) -> list[int]:
    if raw_value is None:
        return []
    try:
        parsed = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[int] = []
    for item in parsed:
        try:
            out.append(int(item))
        except Exception:
            continue
    return out


def _normalize_text_for_diff(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(str(text).lower().split())


def _text_similarity(left: str | None, right: str | None) -> float:
    a = _normalize_text_for_diff(left)
    b = _normalize_text_for_diff(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _cluster_input_fingerprint(article_ids: list[int]) -> str:
    normalized = sorted({int(x) for x in article_ids})
    payload = ",".join(str(x) for x in normalized)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_json_dict(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def _safe_float(raw_value: Any, default: float = 0.0) -> float:
    try:
        return float(raw_value)
    except Exception:
        return default


def _safe_int(raw_value: Any, default: int = 0) -> int:
    try:
        return int(raw_value)
    except Exception:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def _env_bool_first(names: list[str], default: bool = False) -> bool:
    for name in names:
        raw_value = os.environ.get(name)
        if raw_value is None:
            continue
        return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}
    return default


def _safe_datetime(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None

    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is not None:
            return raw_value.astimezone(timezone.utc).replace(tzinfo=None)
        return raw_value

    try:
        raw_text = str(raw_value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(raw_text)
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _infer_urgency_class(title_text: str | None, body_text: str | None) -> str:
    combined = _normalize_text_for_diff(f"{title_text or ''} {body_text or ''}")
    if not combined:
        return "active"

    breaking_keywords = {
        "breaking",
        "urgent",
        "alert",
        "developing",
        "explosion",
        "evacuation",
        "earthquake",
        "attack",
        "ceasefire",
        "election",
        "vote",
    }
    background_keywords = {
        "analysis",
        "opinion",
        "feature",
        "long read",
        "explainer",
        "retrospective",
        "background",
    }

    if any(keyword in combined for keyword in breaking_keywords):
        return "breaking"
    if any(keyword in combined for keyword in background_keywords):
        return "background"
    return "active"


def _resolve_living_story_calibration(urgency_class: str) -> dict[str, float]:
    profile = str(os.environ.get("LIVING_STORY_CALIBRATION_PROFILE", "balanced")).strip().lower()
    if profile not in {"balanced", "conservative", "aggressive", "breaking"}:
        profile = "balanced"

    profile_defaults = {
        "balanced": {
            "major_delta": 0.12,
            "minor_delta": 0.03,
            "min_new_articles": 2,
            "composite_threshold": 0.35,
            "weight_text": 0.45,
            "weight_source": 0.20,
            "weight_recency": 0.15,
            "weight_fact": 0.15,
            "weight_new": 0.05,
        },
        "conservative": {
            "major_delta": 0.16,
            "minor_delta": 0.05,
            "min_new_articles": 3,
            "composite_threshold": 0.45,
            "weight_text": 0.55,
            "weight_source": 0.15,
            "weight_recency": 0.10,
            "weight_fact": 0.15,
            "weight_new": 0.05,
        },
        "aggressive": {
            "major_delta": 0.08,
            "minor_delta": 0.02,
            "min_new_articles": 1,
            "composite_threshold": 0.28,
            "weight_text": 0.35,
            "weight_source": 0.20,
            "weight_recency": 0.20,
            "weight_fact": 0.15,
            "weight_new": 0.10,
        },
        "breaking": {
            "major_delta": 0.06,
            "minor_delta": 0.015,
            "min_new_articles": 1,
            "composite_threshold": 0.22,
            "weight_text": 0.25,
            "weight_source": 0.20,
            "weight_recency": 0.30,
            "weight_fact": 0.15,
            "weight_new": 0.10,
        },
    }

    defaults = dict(profile_defaults[profile])
    major_delta = _safe_float(os.environ.get("LIVING_STORY_MAJOR_TEXT_DELTA"), defaults["major_delta"])
    minor_delta = _safe_float(os.environ.get("LIVING_STORY_MINOR_TEXT_DELTA"), defaults["minor_delta"])
    min_new_articles = _safe_int(os.environ.get("LIVING_STORY_MIN_NEW_ARTICLES"), int(defaults["min_new_articles"]))
    composite_threshold = _safe_float(os.environ.get("LIVING_STORY_COMPOSITE_THRESHOLD"), defaults["composite_threshold"])

    weight_text = _safe_float(os.environ.get("LIVING_STORY_WEIGHT_TEXT"), defaults["weight_text"])
    weight_source = _safe_float(os.environ.get("LIVING_STORY_WEIGHT_SOURCE"), defaults["weight_source"])
    weight_recency = _safe_float(os.environ.get("LIVING_STORY_WEIGHT_RECENCY"), defaults["weight_recency"])
    weight_fact = _safe_float(os.environ.get("LIVING_STORY_WEIGHT_FACT"), defaults["weight_fact"])
    weight_new = _safe_float(os.environ.get("LIVING_STORY_WEIGHT_NEW_ARTICLES"), defaults["weight_new"])

    recency_multiplier_defaults = {
        "breaking": 1.35,
        "active": 1.0,
        "background": 0.80,
    }
    threshold_multiplier_defaults = {
        "breaking": 0.85,
        "active": 1.0,
        "background": 1.10,
    }
    recency_multiplier = _safe_float(
        os.environ.get(f"LIVING_STORY_RECENCY_MULTIPLIER_{urgency_class.upper()}"),
        recency_multiplier_defaults.get(urgency_class, 1.0),
    )
    threshold_multiplier = _safe_float(
        os.environ.get(f"LIVING_STORY_THRESHOLD_MULTIPLIER_{urgency_class.upper()}"),
        threshold_multiplier_defaults.get(urgency_class, 1.0),
    )

    weight_recency *= max(recency_multiplier, 0.0)
    total_weight = max(weight_text + weight_source + weight_recency + weight_fact + weight_new, 1e-6)
    weight_text /= total_weight
    weight_source /= total_weight
    weight_recency /= total_weight
    weight_fact /= total_weight
    weight_new /= total_weight

    return {
        "profile": profile,
        "major_delta": major_delta,
        "minor_delta": minor_delta,
        "min_new_articles": float(max(min_new_articles, 1)),
        "composite_threshold": max(composite_threshold * max(threshold_multiplier, 0.1), 0.01),
        "weight_text": weight_text,
        "weight_source": weight_source,
        "weight_recency": weight_recency,
        "weight_fact": weight_fact,
        "weight_new": weight_new,
        "recency_multiplier": recency_multiplier,
        "threshold_multiplier": threshold_multiplier,
    }


def _govern_override(override: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    require_owner = _env_bool("LIVING_STORY_OVERRIDE_REQUIRE_OWNER", default=True)
    require_approval = _env_bool("LIVING_STORY_OVERRIDE_REQUIRE_APPROVAL", default=False)
    max_ttl_hours = _safe_int(os.environ.get("LIVING_STORY_OVERRIDE_MAX_TTL_HOURS"), 168)

    owner = str(override.get("owner", "")).strip()
    approved_by = str(override.get("approved_by", "")).strip()
    expires_at = _safe_datetime(override.get("expires_at")) if override.get("expires_at") else None
    now_utc = datetime.utcnow()

    if require_owner and not owner:
        return None, {"reason": "missing_owner", "required": "owner"}
    if require_approval and not approved_by:
        return None, {"reason": "missing_approval", "required": "approved_by"}
    if expires_at is not None and expires_at < now_utc:
        return None, {"reason": "override_expired", "expires_at": override.get("expires_at")}

    if max_ttl_hours > 0 and expires_at is not None:
        ttl_hours = (expires_at - now_utc).total_seconds() / 3600.0
        if ttl_hours > max_ttl_hours:
            return None, {
                "reason": "override_ttl_exceeds_limit",
                "ttl_hours": round(ttl_hours, 2),
                "max_ttl_hours": max_ttl_hours,
            }

    governed = dict(override)
    governed["owner"] = owner
    governed["approved_by"] = approved_by
    if expires_at is not None:
        governed["expires_at"] = expires_at.isoformat() + "Z"
    governed["governed_at"] = datetime.utcnow().isoformat() + "Z"
    governed["governance"] = {
        "require_owner": require_owner,
        "require_approval": require_approval,
        "max_ttl_hours": max_ttl_hours,
    }
    return governed, None


def _extract_domain(raw_url: Any) -> str:
    if not raw_url:
        return ""
    try:
        parsed = urlparse(str(raw_url))
        return (parsed.netloc or "").lower()
    except Exception:
        return ""


def _load_operator_override_map() -> dict[str, Any]:
    raw_json = os.environ.get("LIVING_STORY_OPERATOR_OVERRIDES_JSON", "").strip()
    if not raw_json:
        return {}
    try:
        parsed = json.loads(raw_json)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def _resolve_operator_override(
    cluster_id: str,
    story_id: str | None,
    living_story_meta: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    valid_actions = {"force_update", "force_hold", "force_republish"}

    inline_override = living_story_meta.get("operator_override")
    if isinstance(inline_override, dict):
        action = str(inline_override.get("action", "")).strip().lower()
        if action in valid_actions:
            candidate = {
                "action": action,
                "reason": str(inline_override.get("reason", "manual override")).strip(),
                "source": "synth_metadata",
                "owner": inline_override.get("owner"),
                "approved_by": inline_override.get("approved_by"),
                "expires_at": inline_override.get("expires_at"),
            }
            return _govern_override(candidate)

    override_map = _load_operator_override_map()
    candidates = [cluster_id]
    if story_id:
        candidates.append(story_id)

    for candidate in candidates:
        raw_entry = override_map.get(candidate)
        if not raw_entry:
            continue
        if isinstance(raw_entry, str):
            action = raw_entry.strip().lower()
            if action in valid_actions:
                return _govern_override({
                    "action": action,
                    "reason": "env override",
                    "source": "env_json",
                })
        elif isinstance(raw_entry, dict):
            action = str(raw_entry.get("action", "")).strip().lower()
            if action in valid_actions:
                candidate = {
                    "action": action,
                    "reason": str(raw_entry.get("reason", "env override")).strip(),
                    "source": "env_json",
                    "owner": raw_entry.get("owner"),
                    "approved_by": raw_entry.get("approved_by"),
                    "expires_at": raw_entry.get("expires_at"),
                }
                return _govern_override(candidate)

    return None, None


def _compute_story_diff(
    prev_title: str | None,
    next_title: str | None,
    prev_body: str | None,
    next_body: str | None,
    prev_ids: list[int],
    next_ids: list[int],
) -> dict[str, Any]:
    prev_title_norm = _normalize_text_for_diff(prev_title)
    next_title_norm = _normalize_text_for_diff(next_title)
    title_similarity = _text_similarity(prev_title_norm, next_title_norm)
    body_similarity = _text_similarity(prev_body, next_body)

    prev_set = set(prev_ids)
    next_set = set(next_ids)
    added = sorted(next_set - prev_set)
    removed = sorted(prev_set - next_set)

    return {
        "title_similarity": round(title_similarity, 4),
        "title_delta": round(1.0 - title_similarity, 4),
        "body_similarity": round(body_similarity, 4),
        "body_delta": round(1.0 - body_similarity, 4),
        "previous_body_length": len(prev_body or ""),
        "new_body_length": len(next_body or ""),
        "body_length_delta": len(next_body or "") - len(prev_body or ""),
        "sources_added": added,
        "sources_removed": removed,
        "source_delta_count": len(added) + len(removed),
    }


def _fetch_article_context_metrics(db_service, article_ids: list[int]) -> dict[str, Any]:
    if not article_ids:
        return {
            "source_diversity_score": 0.0,
            "source_count": 0,
            "unique_domain_count": 0,
            "fact_quality_score": 0.5,
            "recency_score": 0.0,
        }

    db_service.ensure_conn()
    cursor = db_service.mb_conn.cursor()
    format_strings = ",".join(["%s"] * len(article_ids))
    cursor.execute(
        f"""
        SELECT source_id, source_url, created_at, factual_accuracy_score, fact_check_status
        FROM articles
        WHERE id IN ({format_strings})
        """,
        tuple(article_ids),
    )
    rows = cursor.fetchall()
    cursor.close()

    unique_sources = set()
    unique_domains = set()
    created_values = []
    fact_scores = []

    fact_status_map = {
        "proven": 1.0,
        "plausible": 0.8,
        "verified": 0.8,
        "unverified": 0.5,
        "pending": 0.5,
        "improbable": 0.2,
        "disproven": 0.0,
        "false": 0.0,
    }

    for source_id, source_url, created_at, factual_accuracy_score, fact_check_status in rows:
        domain = _extract_domain(source_url)
        if domain:
            unique_domains.add(domain)

        if source_id is not None:
            unique_sources.add(f"sid:{source_id}")
        else:
            if domain:
                unique_sources.add(f"domain:{domain}")

        if created_at:
            created_values.append(created_at)

        status_key = str(fact_check_status or "").strip().lower()
        mapped_score = fact_status_map.get(status_key, 0.5)
        factual_score = _safe_float(factual_accuracy_score, mapped_score)
        fact_scores.append((mapped_score + factual_score) / 2.0)

    source_count = len(unique_sources)
    source_diversity_score = min(source_count / 3.0, 1.0)

    if created_values:
        newest = max(created_values)
        age_seconds = max((datetime.now() - newest).total_seconds(), 0.0)
        age_hours = age_seconds / 3600.0
        recency_score = 1.0 / (1.0 + (age_hours / 24.0))
    else:
        recency_score = 0.0

    fact_quality_score = sum(fact_scores) / len(fact_scores) if fact_scores else 0.5

    return {
        "source_diversity_score": round(source_diversity_score, 4),
        "source_count": source_count,
        "unique_domain_count": len(unique_domains),
        "fact_quality_score": round(fact_quality_score, 4),
        "recency_score": round(recency_score, 4),
    }


def _derive_confidence_tier(
    *,
    source_count: int,
    unique_domain_count: int,
    fact_quality_score: float,
) -> str:
    if unique_domain_count >= 3 and source_count >= 3 and fact_quality_score >= 0.75:
        return "high"
    if unique_domain_count >= 2 and source_count >= 2 and fact_quality_score >= 0.60:
        return "medium"
    return "low"


def _derive_publication_lane_metadata(
    *,
    cluster_id: str,
    article_count: int,
    input_fingerprint: str,
    context_metrics: dict[str, Any],
    urgency_class: str | None = None,
) -> dict[str, Any]:
    policy_enabled = _env_bool("MULTI_SOURCE_LANE_POLICY_ENABLED", default=True)
    lane_verified_enabled = _env_bool_first(
        ["MULTI_SOURCE_LANE1_ENABLED", "MULTI_SOURCE_LANE_VERIFIED_ENABLED"],
        default=True,
    )
    lane_developing_enabled = _env_bool_first(
        ["MULTI_SOURCE_LANE2_ENABLED", "MULTI_SOURCE_LANE_DEVELOPING_ENABLED"],
        default=True,
    )
    min_article_count = max(_safe_int(os.environ.get("MULTI_SOURCE_MIN_ARTICLE_COUNT"), 2), 1)
    min_sources = max(_safe_int(os.environ.get("MULTI_SOURCE_MIN_SOURCE_COUNT"), 2), 1)
    min_unique_domains = max(_safe_int(os.environ.get("MULTI_SOURCE_MIN_UNIQUE_DOMAINS"), 2), 1)
    policy_version = str(os.environ.get("MULTI_SOURCE_LANE_POLICY_VERSION", "v1")).strip() or "v1"

    override_source = "default"
    raw_overrides = os.environ.get("MULTI_SOURCE_LANE_POLICY_TOPIC_OVERRIDES_JSON", "").strip()
    if raw_overrides and urgency_class:
        try:
            parsed = json.loads(raw_overrides)
            if isinstance(parsed, dict):
                key = str(urgency_class).strip().lower()
                candidate = parsed.get(key)
                if isinstance(candidate, dict):
                    min_article_count = max(_safe_int(candidate.get("min_article_count"), min_article_count), 1)
                    min_sources = max(_safe_int(candidate.get("min_source_count"), min_sources), 1)
                    min_unique_domains = max(
                        _safe_int(candidate.get("min_unique_domains"), min_unique_domains),
                        1,
                    )
                    override_source = f"topic_override:{key}"
        except Exception:
            pass

    source_count = max(_safe_int(context_metrics.get("source_count"), 0), 0)
    unique_domain_count = max(_safe_int(context_metrics.get("unique_domain_count"), 0), 0)
    fact_quality_score = max(min(_safe_float(context_metrics.get("fact_quality_score"), 0.5), 1.0), 0.0)

    reason_codes: list[str] = []
    if not policy_enabled:
        reason_codes.append("lane_policy_disabled")
    else:
        if article_count < min_article_count:
            reason_codes.append("single_article_cluster")
        if source_count < min_sources:
            reason_codes.append("insufficient_source_count")
        if unique_domain_count < min_unique_domains:
            reason_codes.append("insufficient_domain_diversity")

    publication_lane = "verified_story" if not reason_codes else "developing_brief"

    lane_bounce_reason: str | None = None
    if publication_lane == "verified_story" and not lane_verified_enabled:
        if lane_developing_enabled:
            publication_lane = "developing_brief"
            lane_bounce_reason = "lane1_disabled_bounced_to_lane2"
        else:
            publication_lane = "developing_brief"
            lane_bounce_reason = "lane1_disabled_lane2_disabled_forced_fallback"
    elif publication_lane == "developing_brief" and not lane_developing_enabled:
        if lane_verified_enabled:
            publication_lane = "verified_story"
            lane_bounce_reason = "lane2_disabled_bounced_to_lane1"
        else:
            publication_lane = "developing_brief"
            lane_bounce_reason = "lane1_disabled_lane2_disabled_forced_fallback"

    if lane_bounce_reason:
        reason_codes.append(lane_bounce_reason)
    confidence_tier = _derive_confidence_tier(
        source_count=source_count,
        unique_domain_count=unique_domain_count,
        fact_quality_score=fact_quality_score,
    )

    return {
        "publication_lane": publication_lane,
        "source_count": source_count,
        "unique_domain_count": unique_domain_count,
        "confidence_tier": confidence_tier,
        "provenance_trace_id": f"cluster:{cluster_id}:{input_fingerprint[:16]}",
        "decision_reason_codes": reason_codes or ["meets_multi_source_thresholds"],
        "policy_version": policy_version,
        "policy_enabled": policy_enabled,
        "policy_override_source": override_source,
        "lane1_enabled": lane_verified_enabled,
        "lane2_enabled": lane_developing_enabled,
        "policy_decision_at": datetime.utcnow().isoformat() + "Z",
        "policy_thresholds": {
            "min_article_count": min_article_count,
            "min_source_count": min_sources,
            "min_unique_domains": min_unique_domains,
        },
    }


def _record_lane_metrics(lane_metadata: dict[str, Any]) -> None:
    lane = str(lane_metadata.get("publication_lane") or "developing_brief").strip().lower()
    if lane not in {"verified_story", "developing_brief"}:
        lane = "developing_brief"

    _LANE_METRIC_TOTALS[lane] = int(_LANE_METRIC_TOTALS.get(lane, 0)) + 1
    metric_lane_suffix = lane.replace("-", "_")
    _ORCH_METRICS.increment(f"published_total_{metric_lane_suffix}")

    total = sum(int(v) for v in _LANE_METRIC_TOTALS.values())
    verified = int(_LANE_METRIC_TOTALS.get("verified_story", 0))
    verified_share = (verified / total) if total else 0.0
    _ORCH_METRICS.gauge("published_verified_share", round(verified_share, 6))

    unique_domains = max(_safe_int(lane_metadata.get("unique_domain_count"), 0), 0)
    _UNIQUE_DOMAIN_SAMPLES.append(unique_domains)
    sample_window = max(_safe_int(os.environ.get("MULTI_SOURCE_METRIC_SAMPLE_WINDOW"), 200), 10)
    if len(_UNIQUE_DOMAIN_SAMPLES) > sample_window:
        del _UNIQUE_DOMAIN_SAMPLES[:-sample_window]
    _ORCH_METRICS.gauge(
        "median_unique_domains_per_story",
        float(statistics.median(_UNIQUE_DOMAIN_SAMPLES)) if _UNIQUE_DOMAIN_SAMPLES else 0.0,
    )


def _record_cluster_promotion_failure_metrics(lane_metadata: dict[str, Any]) -> None:
    lane = str(lane_metadata.get("publication_lane") or "developing_brief").strip().lower()
    if lane != "developing_brief":
        return

    reason_codes = lane_metadata.get("decision_reason_codes")
    if not isinstance(reason_codes, list):
        reason_codes = []

    for reason in reason_codes:
        reason_key = str(reason or "unknown").strip().lower() or "unknown"
        reason_key = reason_key.replace("-", "_")
        _ORCH_METRICS.increment(f"cluster_promotion_failures_{reason_key}")


def _record_singleton_to_verified_conversion(
    *,
    story_id: str,
    prev_meta: dict[str, Any],
    lane_metadata: dict[str, Any],
) -> None:
    lane = str(lane_metadata.get("publication_lane") or "developing_brief").strip().lower()
    if lane != "verified_story":
        return

    prev_lane = ""
    if isinstance(prev_meta, dict):
        prev_pub = prev_meta.get("publication")
        if isinstance(prev_pub, dict):
            prev_lane = str(prev_pub.get("publication_lane") or "").strip().lower()

    if prev_lane != "developing_brief":
        return
    if not story_id:
        return
    if story_id in _SINGLETON_CONVERSION_SEEN:
        return

    _SINGLETON_CONVERSION_SEEN.add(story_id)
    _ORCH_METRICS.increment("singleton_to_verified_conversion_total")


def _update_decision_telemetry(
    telemetry: dict[str, Any],
    action_label: str,
    score_value: float,
) -> dict[str, Any]:
    updated = dict(telemetry or {})
    decision_counts = dict(updated.get("decision_counts") or {})
    decision_counts[action_label] = int(decision_counts.get(action_label, 0)) + 1
    updated["decision_counts"] = decision_counts

    score_window = int(os.environ.get("LIVING_STORY_SCORE_WINDOW", "50"))
    scores_recent = list(updated.get("meaningful_scores_recent") or [])
    scores_recent.append(round(score_value, 4))
    updated["meaningful_scores_recent"] = scores_recent[-score_window:]

    if updated["meaningful_scores_recent"]:
        scores = updated["meaningful_scores_recent"]
        updated["mean_meaningful_score"] = round(sum(scores) / len(scores), 4)
        updated["median_meaningful_score"] = round(statistics.median(scores), 4)

    return updated


def record_living_story_publish_telemetry(db_service, story_id: str) -> None:
    db_service.ensure_conn()
    cursor = db_service.mb_conn.cursor()
    cursor.execute(
        """
        SELECT synth_metadata, updated_at
        FROM synthesized_articles
        WHERE story_id = %s
        LIMIT 1
        """,
        (story_id,),
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        return

    raw_meta, updated_at = row
    metadata = _load_json_dict(raw_meta)
    living_story = metadata.get("living_story") if isinstance(metadata.get("living_story"), dict) else {}
    telemetry = living_story.get("telemetry") if isinstance(living_story.get("telemetry"), dict) else {}

    updated_dt = _safe_datetime(updated_at)
    if updated_dt is None:
        cursor.close()
        return

    now_dt = datetime.now()
    latency_sec = max((now_dt - updated_dt).total_seconds(), 0.0)

    latency_window = int(os.environ.get("LIVING_STORY_PUBLISH_LATENCY_WINDOW", "30"))
    recent_latencies = list(telemetry.get("publish_latency_recent_seconds") or [])
    recent_latencies.append(round(latency_sec, 2))
    recent_latencies = recent_latencies[-latency_window:]

    telemetry["publish_latency_recent_seconds"] = recent_latencies
    telemetry["last_publish_latency_seconds"] = round(latency_sec, 2)
    telemetry["mean_publish_latency_seconds"] = round(sum(recent_latencies) / len(recent_latencies), 2)
    telemetry["median_publish_latency_seconds"] = round(statistics.median(recent_latencies), 2)
    telemetry["last_published_at"] = now_dt.isoformat() + "Z"

    living_story["telemetry"] = telemetry
    metadata["living_story"] = living_story

    cursor.execute(
        """
        UPDATE synthesized_articles
        SET synth_metadata = %s
        WHERE story_id = %s
        """,
        (json.dumps(metadata), story_id),
    )
    db_service.mb_conn.commit()
    cursor.close()


def upsert_living_story_record(
    db_service,
    cluster_id: str,
    article_ids: list[int],
    title_text: str,
    body_text: str,
    generation_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_ids = sorted({int(x) for x in article_ids})
    input_arts_json = json.dumps(normalized_ids)
    fingerprint = _cluster_input_fingerprint(normalized_ids)
    now_iso = datetime.utcnow().isoformat() + "Z"
    generation_event = {
        "timestamp": now_iso,
        "source_agent": "synthesizer",
        "source_tool": "aggregate_cluster",
        "body_length_chars": len(body_text or ""),
        "body_length_words": len((body_text or "").split()),
    }
    if isinstance(generation_audit, dict):
        generation_event.update(generation_audit)
    urgency_class = _infer_urgency_class(title_text, body_text)
    calibration = _resolve_living_story_calibration(urgency_class)

    major_delta = _safe_float(calibration.get("major_delta"), 0.12)
    minor_delta = _safe_float(calibration.get("minor_delta"), 0.03)
    min_new_articles = max(_safe_int(calibration.get("min_new_articles"), 2), 1)
    composite_threshold = _safe_float(calibration.get("composite_threshold"), 0.35)
    weight_text = _safe_float(calibration.get("weight_text"), 0.45)
    weight_source = _safe_float(calibration.get("weight_source"), 0.20)
    weight_recency = _safe_float(calibration.get("weight_recency"), 0.15)
    weight_fact = _safe_float(calibration.get("weight_fact"), 0.15)
    weight_new = _safe_float(calibration.get("weight_new"), 0.05)

    db_service.ensure_conn()
    cursor = db_service.mb_conn.cursor()
    cursor.execute(
        """
        SELECT story_id, title, body, input_articles, synth_metadata, is_published
        FROM synthesized_articles
        WHERE cluster_id = %s
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (cluster_id,),
    )
    existing = cursor.fetchone()

    context_metrics = _fetch_article_context_metrics(db_service, normalized_ids)
    lane_metadata = _derive_publication_lane_metadata(
        cluster_id=cluster_id,
        article_count=len(normalized_ids),
        input_fingerprint=fingerprint,
        context_metrics=context_metrics,
        urgency_class=urgency_class,
    )

    try:
        from agents.critic.tools import evaluate_traceability_balance

        traceability_report = {}
        if isinstance(generation_audit, dict):
            candidate_report = generation_audit.get("analysis_report")
            if isinstance(candidate_report, dict):
                traceability_report = candidate_report

        balance_gate = evaluate_traceability_balance(
            traceability_report,
            min_distinct_sides=max(
                1,
                _safe_int(os.environ.get("BALANCE_POLICY_MIN_DISTINCT_SIDES"), 2),
            ),
            disputed_topic_hard_gate=_env_bool(
                "BALANCE_POLICY_DISPUTED_TOPICS_HARD_GATE", default=False
            ),
            allow_opinion_as_factual_corroboration=_env_bool(
                "BALANCE_POLICY_ALLOW_OPINION_AS_FACTUAL_CORROBORATION",
                default=False,
            ),
        )
        lane_metadata["traceability_balance"] = balance_gate

        if balance_gate.get("gate_result") == "fail":
            lane_metadata["publication_lane"] = "developing_brief"
            reason_codes = lane_metadata.get("decision_reason_codes")
            if not isinstance(reason_codes, list):
                reason_codes = []
            reason_codes.append("traceability_balance_gate_failed")
            lane_metadata["decision_reason_codes"] = sorted(set(reason_codes))
    except Exception as exc:
        logger.debug("Traceability balance evaluation unavailable: %s", exc)

    if not existing:
        story_id = f"STORY-{uuid.uuid4().hex[:8]}"
        synth_metadata = {
            "living_story": {
                "revision": 1,
                "input_fingerprint": fingerprint,
                "last_meaningful_score": 1.0,
                "last_new_articles": len(normalized_ids),
                "last_update_action": "created",
                "updated_at": now_iso,
                "telemetry": {
                    "decision_counts": {"created": 1},
                    "meaningful_scores_recent": [1.0],
                    "mean_meaningful_score": 1.0,
                    "median_meaningful_score": 1.0,
                },
                "last_diff": {
                    "title_similarity": 0.0,
                    "title_delta": 1.0,
                    "body_similarity": 0.0,
                    "body_delta": 1.0,
                    "previous_body_length": 0,
                    "new_body_length": len(body_text or ""),
                    "body_length_delta": len(body_text or ""),
                    "sources_added": normalized_ids,
                    "sources_removed": [],
                    "source_delta_count": len(normalized_ids),
                },
                "explainability": {
                    "decision": "created",
                    "reasons": ["first_story_for_cluster"],
                    "urgency_class": urgency_class,
                    "calibration_profile": calibration.get("profile", "balanced"),
                    "lane_decision": lane_metadata,
                },
            }
        }
        synth_metadata["publication"] = lane_metadata
        synth_metadata["generation"] = {
            "last_event": generation_event,
            "history": [generation_event],
        }
        _record_lane_metrics(lane_metadata)
        _record_cluster_promotion_failure_metrics(lane_metadata)
        cursor.execute(
            """
            INSERT INTO synthesized_articles
            (story_id, cluster_id, input_articles, title, body, created_at, updated_at, is_published, critique_status, synth_metadata)
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), 0, 'pending', %s)
            """,
            (story_id, cluster_id, input_arts_json, title_text, body_text, json.dumps(synth_metadata)),
        )
        return {
            "story_id": story_id,
            "action": "created",
            "meaningful": True,
            "new_article_count": len(normalized_ids),
            "text_delta": 1.0,
            "composite_score": 1.0,
            "publication_lane": lane_metadata.get("publication_lane"),
            "publication_reason_codes": lane_metadata.get("decision_reason_codes"),
        }

    story_id, prev_title, prev_body, prev_input_articles, prev_meta_raw, _is_published = existing
    prev_ids = _safe_json_list(prev_input_articles)
    prev_ids_set = set(prev_ids)
    new_ids_set = set(normalized_ids)
    new_article_count = len(new_ids_set - prev_ids_set)
    similarity = _text_similarity(prev_body, body_text)
    text_delta = 1.0 - similarity

    source_diversity_score = _safe_float(context_metrics.get("source_diversity_score"), 0.0)
    recency_score = _safe_float(context_metrics.get("recency_score"), 0.0)
    fact_quality_score = _safe_float(context_metrics.get("fact_quality_score"), 0.5)
    new_article_score = min((new_article_count / max(min_new_articles, 1)), 1.0)

    composite_score = (
        (text_delta * weight_text)
        + (source_diversity_score * weight_source)
        + (recency_score * weight_recency)
        + (fact_quality_score * weight_fact)
        + (new_article_score * weight_new)
    )

    reasons = []
    if text_delta >= major_delta:
        reasons.append("major_text_delta")
    if new_article_count > 0 and text_delta >= minor_delta:
        reasons.append("minor_delta_with_new_articles")
    if new_article_count >= min_new_articles:
        reasons.append("new_articles_threshold")
    if composite_score >= composite_threshold:
        reasons.append("composite_threshold")

    meaningful = (
        text_delta >= major_delta
        or (new_article_count > 0 and text_delta >= minor_delta)
        or new_article_count >= min_new_articles
        or composite_score >= composite_threshold
    )

    previous_meta = _load_json_dict(prev_meta_raw)
    living_story_meta = previous_meta.get("living_story", {}) if isinstance(previous_meta.get("living_story"), dict) else {}
    override, override_rejected = _resolve_operator_override(
        cluster_id=cluster_id,
        story_id=story_id,
        living_story_meta=living_story_meta,
    )

    final_action = "updated" if meaningful else "tracked_noop"
    if override:
        override_action = override.get("action")
        if override_action == "force_hold":
            meaningful = False
            final_action = "forced_hold"
            reasons.append("operator_force_hold")
        elif override_action == "force_update":
            meaningful = True
            final_action = "forced_update"
            reasons.append("operator_force_update")
        elif override_action == "force_republish":
            meaningful = True
            final_action = "forced_republish"
            reasons.append("operator_force_republish")

    previous_revision = int(living_story_meta.get("revision", 1)) if living_story_meta else 1
    revision = previous_revision + 1 if meaningful else previous_revision

    diff_summary = _compute_story_diff(
        prev_title=prev_title,
        next_title=title_text,
        prev_body=prev_body,
        next_body=body_text,
        prev_ids=prev_ids,
        next_ids=normalized_ids,
    )

    telemetry_prev = living_story_meta.get("telemetry") if isinstance(living_story_meta.get("telemetry"), dict) else {}
    telemetry_next = _update_decision_telemetry(
        telemetry=telemetry_prev,
        action_label=final_action,
        score_value=text_delta,
    )
    lane_counts = dict(telemetry_next.get("lane_counts") or {})
    lane_key = str(lane_metadata.get("publication_lane") or "unknown")
    lane_counts[lane_key] = int(lane_counts.get(lane_key, 0)) + 1
    telemetry_next["lane_counts"] = lane_counts

    next_meta = previous_meta.copy()
    generation_meta = next_meta.get("generation") if isinstance(next_meta.get("generation"), dict) else {}
    generation_history = generation_meta.get("history") if isinstance(generation_meta.get("history"), list) else []
    generation_history.append(generation_event)
    next_meta["generation"] = {
        "last_event": generation_event,
        "history": generation_history[-25:],
    }
    next_meta["publication"] = lane_metadata
    next_meta["living_story"] = {
        "revision": revision,
        "input_fingerprint": fingerprint,
        "last_meaningful_score": round(text_delta, 4),
        "last_composite_score": round(composite_score, 4),
        "last_new_articles": new_article_count,
        "last_update_action": final_action,
        "updated_at": now_iso,
        "telemetry": telemetry_next,
        "last_diff": diff_summary,
        "explainability": {
            "decision": final_action,
            "reasons": sorted(set(reasons)) if reasons else ["no_meaningful_change"],
            "urgency_class": urgency_class,
            "calibration_profile": calibration.get("profile", "balanced"),
            "scores": {
                "text_delta": round(text_delta, 4),
                "composite_score": round(composite_score, 4),
                "source_diversity_score": round(source_diversity_score, 4),
                "recency_score": round(recency_score, 4),
                "fact_quality_score": round(fact_quality_score, 4),
                "new_article_score": round(new_article_score, 4),
            },
            "weights": {
                "text": weight_text,
                "source_diversity": weight_source,
                "recency": weight_recency,
                "fact_quality": weight_fact,
                "new_articles": weight_new,
                "recency_multiplier": _safe_float(calibration.get("recency_multiplier"), 1.0),
                "threshold_multiplier": _safe_float(calibration.get("threshold_multiplier"), 1.0),
            },
            "thresholds": {
                "major_delta": major_delta,
                "minor_delta": minor_delta,
                "min_new_articles": min_new_articles,
                "composite_threshold": composite_threshold,
            },
            "source_count": int(context_metrics.get("source_count", 0)),
            "override": override,
            "override_rejected": override_rejected,
            "lane_decision": lane_metadata,
        },
    }
    _record_lane_metrics(lane_metadata)
    _record_cluster_promotion_failure_metrics(lane_metadata)
    _record_singleton_to_verified_conversion(
        story_id=str(story_id or ""),
        prev_meta=previous_meta,
        lane_metadata=lane_metadata,
    )

    if meaningful:
        cursor.execute(
            """
            UPDATE synthesized_articles
            SET title = %s,
                body = %s,
                input_articles = %s,
                synth_metadata = %s,
                updated_at = NOW(),
                is_published = 0,
                critique_status = 'pending',
                critique_text = NULL
            WHERE story_id = %s
            """,
            (title_text, body_text, input_arts_json, json.dumps(next_meta), story_id),
        )
    else:
        cursor.execute(
            """
            UPDATE synthesized_articles
            SET input_articles = %s,
                synth_metadata = %s,
                updated_at = NOW()
            WHERE story_id = %s
            """,
            (input_arts_json, json.dumps(next_meta), story_id),
        )

    return {
        "story_id": story_id,
        "action": final_action,
        "meaningful": meaningful,
        "new_article_count": new_article_count,
        "text_delta": round(text_delta, 4),
        "composite_score": round(composite_score, 4),
        "publication_lane": lane_metadata.get("publication_lane"),
        "publication_reason_codes": lane_metadata.get("decision_reason_codes"),
        "override": override,
        "override_rejected": override_rejected,
    }

class WorkflowPolicy(ABC):
    """Abstract base class for a workflow policy."""
    
    def __init__(self, mcp_bus_url: str):
        self.mcp_bus_url = mcp_bus_url
        self.db_service = create_database_service()
        default_timeout = _safe_float(os.environ.get("MCP_CALL_READ_TIMEOUT"), 120.0) + 5.0
        self.mcp_call_timeout_seconds = max(
            1.0,
            _safe_float(os.environ.get("ORCH_MCP_CALL_TIMEOUT_SECONDS"), default_timeout),
        )
        self.execution_parallel_default = max(
            1,
            _safe_int(os.environ.get("ORCH_POLICY_EXECUTION_PARALLELISM_DEFAULT"), 2),
        )

    @abstractmethod
    def name(self) -> str:
        """Name of the policy."""
        pass

    @abstractmethod
    def check_condition(self, limit: int) -> List[Any]:
        """Return a list of items (IDs) that match the condition."""
        pass

    @abstractmethod
    async def execute(self, items: List[Any]):
        """Execute the workflow action on the items."""
        pass
    
    def _call_mcp_tool_sync(self, agent: str, tool: str, kwargs: dict) -> dict:
        """Synchronous call to MCP Bus."""
        try:
            payload = {
                "agent": agent,
                "tool": tool,
                "kwargs": kwargs,
                "args": []
            }
            response = requests.post(
                f"{self.mcp_bus_url}/call",
                json=payload,
                timeout=self.mcp_call_timeout_seconds,
            )
            response.raise_for_status()
            
            result = response.json()
            # Unwrap MCP Bus packet if it follows the status/data pattern
            if isinstance(result, dict) and result.get("status") == "success" and "data" in result:
                return result["data"]
                
            return result
        except Exception as e:
            logger.error(f"Failed to call {agent}.{tool}: {e}")
            return {"status": "error", "error": str(e)}

    def _execution_parallelism(self, default: int | None = None) -> int:
        """Return per-policy execution parallelism from env with safe fallback."""
        base_default = (
            self.execution_parallel_default
            if default is None
            else max(1, int(default))
        )
        per_policy_key = f"ORCH_POLICY_EXECUTION_PARALLELISM_{self.name().upper()}"
        return max(1, _safe_int(os.environ.get(per_policy_key), base_default))

    async def _execute_bounded(
        self,
        items: List[Any],
        worker: Callable[[Any], Awaitable[Any]],
        stage_label: str,
        default_parallelism: int | None = None,
    ) -> int:
        """Execute policy worker with bounded concurrency to avoid burst overload."""
        if not items:
            logger.info(f"{stage_label} skipped (0 items).")
            return 0

        parallelism = self._execution_parallelism(default=default_parallelism)
        semaphore = asyncio.Semaphore(parallelism)

        async def _run_one(item: Any) -> Any:
            async with semaphore:
                return await worker(item)

        results = await asyncio.gather(
            *(_run_one(item) for item in items),
            return_exceptions=True,
        )

        success_count = 0
        for res in results:
            if isinstance(res, Exception):
                logger.error(f"{stage_label} task failed: {res}")
                continue
            if isinstance(res, dict):
                if res.get("status") == "success" or bool(res.get("success")):
                    success_count += 1
                elif res.get("error"):
                    logger.error(f"{stage_label} task returned error: {res.get('error')}")
            else:
                success_count += 1

        logger.info(
            "%s batch complete. Success: %s/%s (parallelism=%s)",
            stage_label,
            success_count,
            len(items),
            parallelism,
        )
        return success_count

    async def _call_mcp_tool(self, agent: str, tool: str, kwargs: dict):
        """Async wrapper for MCP tool call."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._call_mcp_tool_sync, agent, tool, kwargs)

    def _cleanup_pending_pool_for_article_ids(self, article_ids: List[int]) -> int:
        """Best-effort cleanup of pending pool rows for finalized article IDs."""
        if not article_ids:
            return 0
        try:
            self.db_service.ensure_conn()
            cursor = self.db_service.mb_conn.cursor()
            try:
                placeholders = ", ".join(["%s"] * len(article_ids))
                cursor.execute(
                    f"DELETE FROM pending_articles_pool WHERE article_id IN ({placeholders})",
                    tuple(article_ids),
                )
                return int(cursor.rowcount or 0)
            finally:
                cursor.close()
        except Exception as e:
            logger.warning("Pending pool cleanup failed: %s", e)
            return 0


class IngestionToAnalysisPolicy(WorkflowPolicy):
    """
    Policy: Ingested -> Analyzed
    Condition: articles.analyzed = 0
    Action: Call 'analyst.analyze_article'
    """

    def name(self) -> str:
        return "ingestion_to_analysis"

    def check_condition(self, limit: int) -> List[int]:
        ids = []
        try:
            self.db_service.ensure_conn()
            # Commit any existing transaction to ensure we see fresh data
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            # Select unanalyzed articles, preferring newer ones
            query = """
                SELECT id FROM articles 
                WHERE analyzed = 0 
                ORDER BY created_at DESC 
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            # Try to reconnect on next pass
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[int]):
        logger.info(f"Triggering analysis for {len(items)} articles.")
        async def _worker(article_id: int):
            return await self._call_mcp_tool(
                agent="analyst",
                tool="analyze_article",
                kwargs={"article_id": article_id},
            )

        await self._execute_bounded(items, _worker, "analysis")


class AnalysisToEmbeddingPolicy(WorkflowPolicy):
    """
    Policy: Analyzed -> Embedded
    Condition: articles.analyzed = 1 AND articles.embedded = 0
    Action: Call 'memory.embed_article'
    """

    def name(self) -> str:
        return "analysis_to_embedding"

    def check_condition(self, limit: int) -> List[int]:
        ids = []
        try:
            self.db_service.ensure_conn()
            # Commit any existing transaction to ensure we see fresh data
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            # Select analyzed but not embedded articles
            query = """
                SELECT id FROM articles 
                WHERE analyzed = 1 AND embedded = 0
                ORDER BY created_at DESC 
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[int]):
        logger.info(f"Triggering embedding for {len(items)} articles.")
        async def _worker(article_id: int):
            return await self._call_mcp_tool(
                agent="memory",
                tool="embed_article",
                kwargs={"article_id": article_id},
            )

        await self._execute_bounded(items, _worker, "embedding")


class AnalysisToSummaryPolicy(WorkflowPolicy):
    """
    Policy: Analyzed -> Summarized
    Condition: articles.analyzed = 1 AND (articles.summary IS NULL OR articles.summary = '')
    Action: Call 'synthesizer.summarize_article'
    """

    def name(self) -> str:
        return "analysis_to_summary"

    def check_condition(self, limit: int) -> List[int]:
        if not _env_bool("ORCHESTRATOR_ENABLE_SOURCE_SUMMARY_STAGE", default=False):
            return []
        ids = []
        try:
            self.db_service.ensure_conn()
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            query = """
                SELECT id FROM articles 
                WHERE analyzed = 1 AND (summary IS NULL OR summary = '')
                ORDER BY created_at DESC 
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[int]):
        logger.info(f"Triggering summarization for {len(items)} articles.")
        async def _worker(article_id: int):
            return await self._call_mcp_tool(
                agent="synthesizer",
                tool="summarize_article",
                kwargs={"article_id": article_id},
            )

        await self._execute_bounded(items, _worker, "summarization")


class AnalysisToFactCheckPolicy(WorkflowPolicy):
    """
    Policy: Summarized -> Fact Checked
    Condition: articles.analyzed = 1 AND articles.fact_check_status IS NULL
    Action: Call 'fact_checker.verify_article' (requires fact_checker agent update)
    """

    def name(self) -> str:
        return "analysis_to_fact_check"

    def check_condition(self, limit: int) -> List[int]:
        ids = []
        try:
            self.db_service.ensure_conn()
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            query = """
                SELECT id FROM articles 
                WHERE analyzed = 1 
                  AND fact_check_status IS NULL
                ORDER BY created_at DESC 
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[int]):
        logger.info(f"Triggering fact check for {len(items)} articles.")
        async def _worker(article_id: int):
            return await self._call_mcp_tool(
                agent="fact_checker",
                tool="verify_article",
                kwargs={"article_id": article_id},
            )

        await self._execute_bounded(items, _worker, "fact_check")



# Backward-compatible alias for legacy imports
SummaryToFactCheckPolicy = AnalysisToFactCheckPolicy



class IncrementalClusteringPolicy(WorkflowPolicy):
    """
    Policy: Fact Checked -> Clustered (Incremental)
    Condition: articles.fact_check_status IS NOT NULL 
               AND (articles.input_cluster_ids IS NULL OR articles.input_cluster_ids = '[]')
    Action: Query ChromaDB for neighbors. If close match found, join cluster. Else create new.
    """

    def name(self) -> str:
        return "incremental_clustering"

    def check_condition(self, limit: int) -> List[int]:
        ids = []
        try:
            self.db_service.ensure_conn()
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            
            # Process one by one or small batches.
            query = """
                SELECT id FROM articles 
                WHERE fact_check_status IS NOT NULL 
                      AND embedded = 1
                      AND (input_cluster_ids IS NULL OR input_cluster_ids = '[]' OR input_cluster_ids = '')
                ORDER BY created_at DESC
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[int]):
        if not items:
            return
            
        logger.info(f"Incremental clustering for {len(items)} articles.")
        
        # We need the collection to be available
        if not self.db_service.collection:
             logger.warning("ChromaDB collection not available. Skipping clustering.")
             return

        for article_id in items:
            try:
                # 1. Get Embedding
                # We cast ID to string as Chroma uses string IDs
                result = self.db_service.collection.get(
                    ids=[str(article_id)],
                    include=["embeddings"]
                )
                
                # Safe check for embeddings to avoid numpy ambiguity
                has_embedding = False
                if result and 'embeddings' in result:
                    embs = result['embeddings']
                    if embs is not None and len(embs) > 0:
                        has_embedding = True
                
                if not has_embedding:
                    logger.warning(f"No embedding found for article {article_id}. Skipping.")
                    continue
                    
                embedding = result['embeddings'][0]
                
                # 2. Query Neighbors
                # We look for nearest 5
                # We filter by distance < 0.5
                neighbors = self.db_service.collection.query(
                    query_embeddings=[embedding],
                    n_results=5,
                    include=["metadatas", "distances", "documents"]
                )
                
                found_cluster_id = None
                
                # Handling numpy/list ambiguity safely
                has_results = False
                if neighbors:
                    ids_list = neighbors.get('ids')
                    if ids_list and len(ids_list) > 0 and len(ids_list[0]) > 0:
                        has_results = True
                
                if has_results:
                    neighbor_ids = neighbors['ids'][0]
                    distances = neighbors['distances'][0]
                    
                    # Filter by distance
                    # 0.5 is significant. 0 is identical.
                    valid_neighbor_db_ids = []
                    for nid, dist in zip(neighbor_ids, distances):
                        if dist < 0.5 and str(nid) != str(article_id):
                            # nid is the chroma ID, which is str(article_id)
                            try:
                                valid_neighbor_db_ids.append(int(nid))
                            except:
                                pass
                    
                    if valid_neighbor_db_ids:
                        # Fetch cluster IDs of these neighbors
                        self.db_service.ensure_conn()
                        cursor = self.db_service.mb_conn.cursor()
                        format_strings = ','.join(['%s'] * len(valid_neighbor_db_ids))
                        cursor.execute(f"SELECT input_cluster_ids FROM articles WHERE id IN ({format_strings})", tuple(valid_neighbor_db_ids))
                        rows = cursor.fetchall()
                        cursor.close()
                        
                        cluster_counts = {}
                        for row in rows:
                            if row[0]:
                                try:
                                    c_ids = json.loads(row[0])
                                    if c_ids:
                                        cid = c_ids[0]
                                        cluster_counts[cid] = cluster_counts.get(cid, 0) + 1
                                except:
                                    pass
                        
                        # If we have candidates, pick the most frequent
                        if cluster_counts:
                            found_cluster_id = max(cluster_counts, key=cluster_counts.get)
                            logger.info(f"Article {article_id} matched to existing cluster {found_cluster_id} (neighbors: {len(valid_neighbor_db_ids)})")

                # 3. Assign Cluster
                if not found_cluster_id:
                    found_cluster_id = f"CL-{uuid.uuid4().hex[:8]}"
                    logger.info(f"Article {article_id} assigned to NEW cluster {found_cluster_id}")
                
                # Update DB
                self.db_service.ensure_conn()
                cursor = self.db_service.mb_conn.cursor()
                input_cluster_json = json.dumps([found_cluster_id])
                cursor.execute(
                    "UPDATE articles SET input_cluster_ids = %s WHERE id = %s",
                    (input_cluster_json, article_id)
                )

                removed = self._cleanup_pending_pool_for_article_ids([article_id])
                if removed > 0:
                    logger.info(
                        "Removed %s pending pool row(s) for clustered article %s",
                        removed,
                        article_id,
                    )
                self.db_service.mb_conn.commit()
                cursor.close()
                
            except Exception as e:
                logger.error(f"Error processing clustering for article {article_id}: {e}")



class ClusterToSynthesisPolicy(WorkflowPolicy):
    """
    Policy: Clustered -> Synthesized
    Condition: articles.is_synthesized = 0 
               AND articles.input_cluster_ids IS NOT NULL 
               AND articles.input_cluster_ids != '[]'
    Action: Group by cluster_id, call 'synthesizer.aggregate_cluster', save to 'synthesized_articles'.
    """

    def name(self) -> str:
        return "cluster_to_synthesis"


    def check_condition(self, limit: int) -> List[str]:
        # Returns list of Cluster IDs to process
        cluster_ids = []
        try:
            self.db_service.ensure_conn()
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            
            # Fetch candidates: un-synthesized articles with clusters
            # We fetch a larger batch to find a complete cluster
            # New Rule: Only pick clusters with at least 2 articles (to avoid premature singletons)
            # Maturity Rule: Fetch created_at to ensure cluster is stable (no new arrivals in last 20 mins)
            # INCREASED LIMIT: To 2000 to ensure we look past the "Singleton Jam" (backlog of ~1000 items)
            query = """
                SELECT input_cluster_ids, created_at FROM articles 
                WHERE is_synthesized = 0 
                  AND input_cluster_ids IS NOT NULL 
                  AND input_cluster_ids != '[]'
                  AND input_cluster_ids != ''
                ORDER BY created_at ASC
                LIMIT 2000
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()
            
            # Tally counts per cluster and track latest timestamp
            counts = {}
            latest_activity = {}
            
            for row in rows:
                try:
                    c_ids = json.loads(row[0])
                    created_at = row[1]
                    
                    if isinstance(c_ids, list) and c_ids:
                        cid = c_ids[0] # Assume primary cluster
                        counts[cid] = counts.get(cid, 0) + 1
                        
                        if created_at:
                            current_max = latest_activity.get(cid)
                            if not current_max or created_at > current_max:
                                latest_activity[cid] = created_at
                except:
                    continue
            
            # Filter:
            # 1. Count >= 2
            # 2. Maturity: Last article > 20 mins ago
            # 3. Optional singleton processing via env flag
            # 4. Stale Snapshot fallback: Count == 1 AND Age > 18 hours -> Synthesize as Brief
            valid_counts = {}
            now = datetime.now()
            # Use 20 minutes maturity window for active clusters
            maturity_window = timedelta(minutes=20)
            # Use 18 hours for stale singletons (Briefs)
            stale_window = timedelta(hours=18)
            process_singletons = _env_bool("PROCESS_SINGLETON_CLUSTERS", default=False)
            
            for cid, count in counts.items():
                last_ts = latest_activity.get(cid)
                if last_ts:
                    age = now - last_ts
                    
                    if count >= 2:
                         # Active Cluster Maturity Rule
                         if age > maturity_window:
                             valid_counts[cid] = count
                    elif count == 1:
                         if process_singletons:
                             valid_counts[cid] = count
                             continue
                         # Stale Brief Rule
                         if age > stale_window:
                             valid_counts[cid] = count
            
            # Prioritize freshest clusters first, then larger clusters.
            # This prevents newer pipeline output from being starved behind older backlog.
            sorted_clusters = sorted(
                valid_counts.items(),
                key=lambda x: (latest_activity.get(x[0], datetime.min), x[1]),
                reverse=True,
            )
            cluster_ids = [c[0] for c in sorted_clusters[:limit]]
            
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return cluster_ids

    async def execute(self, cluster_ids: List[str]):
        """
        Execute synthesis for the given cluster IDs.
        Note: The 'items' arg here is a list of cluster_ids, not article_ids.
        """
        logger.info(f"Synthesis policy triggered for {len(cluster_ids)} clusters.")
        
        for cid in cluster_ids:
            try:
                # 1. Fetch articles for this cluster
                self.db_service.ensure_conn()
                cursor = self.db_service.mb_conn.cursor()
                
                # We need to find articles where JSON contains this CID.
                # LIKE is a cheap approximation for logic: ["CL-ABC"] contains CL-ABC
                query = """
                    SELECT id, content FROM articles 
                    WHERE is_synthesized = 0 
                      AND input_cluster_ids LIKE %s
                """
                like_pattern = f"%{cid}%"
                cursor.execute(query, (like_pattern,))
                rows = cursor.fetchall()
                
                if not rows:
                    cursor.close()
                    continue
                    
                article_ids = [row[0] for row in rows]
                texts = [row[1] for row in rows if row[1]]
                cursor.close()
                
                if not texts:
                    continue

                logger.info(f"Synthesizing cluster {cid} with {len(texts)} articles.")
                
                # Check for previous synthesis history (Context Continuity)
                previous_context = None
                try:
                    cursor = self.db_service.mb_conn.cursor()
                    # Get the most recent synthesized version of this cluster
                    hist_query = """
                        SELECT body, created_at FROM synthesized_articles 
                        WHERE cluster_id = %s 
                        ORDER BY created_at DESC LIMIT 1
                    """
                    cursor.execute(hist_query, (cid,))
                    hist_row = cursor.fetchone()
                    
                    if hist_row:
                        prev_body = hist_row[0]
                        prev_date = hist_row[1]
                        
                        # Logic: Only use context if it's somewhat recent (e.g. < 7 days)
                        # otherwise treat as a fresh angle on an old topic.
                        if prev_body:
                             days_diff = (datetime.now() - prev_date).days if prev_date else 0
                             if days_diff < 7:
                                 previous_context = prev_body
                                 logger.info(f"Using previous context from {prev_date} for cluster {cid}")
                    cursor.close()
                except Exception as e:
                    logger.warning(f"Failed to fetch history for {cid}: {e}")

                # 2. Call Synthesizer
                # Using aggregate_cluster_tool
                synthesis_result = await self._call_mcp_tool(
                    agent="synthesizer",
                    tool="aggregate_cluster",
                    kwargs={
                        "article_texts": texts,
                        "type": "brief" if len(texts) == 1 else "full",
                        "previous_context": previous_context
                    }
                )
                
                if isinstance(synthesis_result, dict) and synthesis_result.get("success"):
                    body_text = str(
                        synthesis_result.get("body")
                        or synthesis_result.get("summary")
                        or ""
                    ).strip()
                    if not body_text:
                        logger.warning(f"Skipping empty synthesis output for cluster {cid}")
                        continue
                    is_brief = len(texts) == 1
                    title_text = _derive_story_title(
                        cid,
                        synthesis_result,
                        is_brief=is_brief,
                    )
                    
                    # 3. Upsert canonical living story per cluster
                    self.db_service.ensure_conn()
                    cursor = self.db_service.mb_conn.cursor()
                    upsert_result = upsert_living_story_record(
                        db_service=self.db_service,
                        cluster_id=cid,
                        article_ids=article_ids,
                        title_text=title_text,
                        body_text=body_text,
                        generation_audit={
                            "method": synthesis_result.get("method"),
                            "model_used": synthesis_result.get("model_used"),
                            "confidence": synthesis_result.get("confidence"),
                            "article_count": len(texts),
                            "has_previous_context": bool(previous_context),
                        },
                    )

                    # 4. Mark articles as synthesized (always, even when update is not meaningful)
                    format_strings = ','.join(['%s'] * len(article_ids))
                    update_query = f"UPDATE articles SET is_synthesized = 1 WHERE id IN ({format_strings})"
                    cursor.execute(update_query, tuple(article_ids))

                    removed = self._cleanup_pending_pool_for_article_ids(article_ids)
                    if removed > 0:
                        logger.info(
                            "Removed %s pending pool row(s) for synthesized cluster %s",
                            removed,
                            cid,
                        )
                    
                    self.db_service.mb_conn.commit()
                    cursor.close()

                    if upsert_result.get("action") == "tracked_noop":
                        logger.info(
                            f"ℹ️ Cluster {cid} produced no meaningful story delta "
                            f"(text_delta={upsert_result.get('text_delta')}, composite_score={upsert_result.get('composite_score')}, "
                            f"new_articles={upsert_result.get('new_article_count')}). "
                            f"Tracked inputs without republish for story {upsert_result.get('story_id')}."
                        )
                    else:
                        logger.info(
                            f"✅ Upserted living story {upsert_result.get('story_id')} from cluster {cid} "
                            f"(action={upsert_result.get('action')}, text_delta={upsert_result.get('text_delta')}, "
                            f"composite_score={upsert_result.get('composite_score')}, "
                            f"new_articles={upsert_result.get('new_article_count')})."
                        )
                else:
                    err = synthesis_result.get('error') if isinstance(synthesis_result, dict) else str(synthesis_result)
                    logger.error(f"Synthesis failed for cluster {cid}: {err}")
                    
                    # Log timeouts to a separate file for later processing
                    if "timed out" in str(err).lower() or "timeout" in str(err).lower():
                        try:
                            failed_log_path = "heavy_clusters.log"
                            entry = {
                                "cluster_id": cid,
                                "article_count": len(texts),
                                "error": str(err),
                                "timestamp": datetime.now().isoformat()
                            }
                            # Append metadata to a JSONL file
                            with open(failed_log_path, "a") as f:
                                f.write(json.dumps(entry) + "\n")
                            logger.info(f"💾 Logged heavy cluster {cid} to {failed_log_path}")
                        except Exception as log_err:
                            logger.error(f"Failed to log heavy cluster: {log_err}")
                    
            except Exception as e:
                logger.error(f"Error processing cluster {cid}: {e}")

class HeavyClusterRetryPolicy(WorkflowPolicy):
    """
    Policy: Retry Heavy Clusters
    Condition: 
      1. System load is light (load avg < 6.0)
      2. No significant active backlog in JustNews queues
      3. heavy_clusters.log has entries
    Action: Retry synthesis for one cluster at a time.
    """
    def name(self) -> str:
        return "heavy_cluster_retry"

    def check_condition(self, limit: int) -> List[str]:
        # 1. Check System Load
        try:
            # 1 minute load average. 16 cores. 
            # If load > 6.0, consider it busy.
            load = os.getloadavg()
            if load[0] > 6.0: 
                return []
        except:
            return []

        # 2. Check JustNews Backlog
        try:
            self.db_service.ensure_conn()
            # Check for unanalyzed articles or pending regular clusters
            cursor = self.db_service.mb_conn.cursor()
            query = """
                SELECT 
                    (SELECT COUNT(*) FROM articles WHERE analyzed = 0) +
                    (SELECT COUNT(*) FROM articles WHERE is_synthesized = 0 AND input_cluster_ids IS NOT NULL AND input_cluster_ids != '[]' AND input_cluster_ids != '')
                as backlog
            """
            cursor.execute(query)
            row = cursor.fetchone()
            cursor.close()
            backlog = row[0] if row else 0
            
            # If there are more than 10 regular items pending, defer heavy processing
            if backlog > 10: 
                return []
        except Exception as e:
            logger.error(f"Error checking backlog for HeavyClusterRetryPolicy: {e}")
            return []
            
        # 3. Check for Heavy Clusters
        failed_log_path = "heavy_clusters.log"
        if not os.path.exists(failed_log_path):
            return []

        cluster_id_to_retry = None
        
        try:
            with open(failed_log_path, "r") as f:
                lines = f.readlines()
            
            # Check the first valid entry
            for line in lines:
                if line.strip():
                    try:
                        rec = json.loads(line)
                        cid = rec.get("cluster_id")
                        if cid:
                            # Verify if it is still unsynthesized
                            self.db_service.ensure_conn()
                            cursor = self.db_service.mb_conn.cursor()
                            cursor.execute("SELECT id FROM synthesized_articles WHERE cluster_id = %s", (cid,))
                            exists = cursor.fetchone()
                            cursor.close()
                            
                            if not exists:
                                cluster_id_to_retry = cid
                                break
                            else:
                                # It's already done, we should clean it up later, but for now just skip returning it
                                pass
                    except:
                        pass
        except Exception as e:
            logger.error(f"Error reading heavy_clusters.log: {e}")
            return []

        if cluster_id_to_retry:
            return [cluster_id_to_retry]
            
        return []

    async def execute(self, cluster_ids: List[str]):
        """
        Execute synthesis for the given heavy cluster IDs.
        """
        logger.info(f"🏋️ HeavyClusterRetryPolicy triggered for {len(cluster_ids)} clusters.")
        
        for cid in cluster_ids:
            try:
                # 1. Fetch articles for this cluster
                self.db_service.ensure_conn()
                cursor = self.db_service.mb_conn.cursor()
                
                query = """
                    SELECT id, content FROM articles 
                    WHERE is_synthesized = 0 
                      AND input_cluster_ids LIKE %s
                """
                like_pattern = f"%{cid}%"
                cursor.execute(query, (like_pattern,))
                rows = cursor.fetchall()
                
                if not rows:
                    cursor.close()
                    continue
                    
                article_ids = [row[0] for row in rows]
                texts = [row[1] for row in rows if row[1]]
                cursor.close()
                
                if not texts:
                    continue

                logger.info(f"Retry synthesizing heavy cluster {cid} with {len(texts)} articles.")
                
                # 2. Call Synthesizer
                # Using aggregate_cluster_tool
                synthesis_result = await self._call_mcp_tool(
                    agent="synthesizer",
                    tool="aggregate_cluster",
                    kwargs={"article_texts": texts}
                )
                
                if isinstance(synthesis_result, dict) and synthesis_result.get("success"):
                    body_text = str(
                        synthesis_result.get("body")
                        or synthesis_result.get("summary")
                        or ""
                    ).strip()
                    if not body_text:
                        logger.warning(f"Skipping empty synthesis output for heavy cluster {cid}")
                        continue
                    title_text = _derive_story_title(
                        cid,
                        synthesis_result,
                        is_brief=len(texts) == 1,
                    )
                    
                    # 3. Upsert canonical living story per cluster
                    self.db_service.ensure_conn()
                    cursor = self.db_service.mb_conn.cursor()
                    upsert_result = upsert_living_story_record(
                        db_service=self.db_service,
                        cluster_id=cid,
                        article_ids=article_ids,
                        title_text=title_text,
                        body_text=body_text,
                        generation_audit={
                            "method": synthesis_result.get("method"),
                            "model_used": synthesis_result.get("model_used"),
                            "confidence": synthesis_result.get("confidence"),
                            "article_count": len(texts),
                            "retry_policy": "heavy_cluster_retry",
                        },
                    )

                    # 4. Mark articles as synthesized (always, even when update is not meaningful)
                    format_strings = ','.join(['%s'] * len(article_ids))
                    update_query = f"UPDATE articles SET is_synthesized = 1 WHERE id IN ({format_strings})"
                    cursor.execute(update_query, tuple(article_ids))

                    removed = self._cleanup_pending_pool_for_article_ids(article_ids)
                    if removed > 0:
                        logger.info(
                            "Removed %s pending pool row(s) for heavy cluster %s",
                            removed,
                            cid,
                        )
                    
                    self.db_service.mb_conn.commit()
                    cursor.close()

                    if upsert_result.get("action") == "tracked_noop":
                        logger.info(
                            f"ℹ️ Heavy cluster {cid} produced no meaningful story delta "
                            f"(text_delta={upsert_result.get('text_delta')}, composite_score={upsert_result.get('composite_score')}, "
                            f"new_articles={upsert_result.get('new_article_count')}). "
                            f"Tracked inputs without republish for story {upsert_result.get('story_id')}."
                        )
                    else:
                        logger.info(
                            f"✅ Successfully upserted living story {upsert_result.get('story_id')} from heavy cluster {cid} "
                            f"(action={upsert_result.get('action')}, text_delta={upsert_result.get('text_delta')}, "
                            f"composite_score={upsert_result.get('composite_score')}, "
                            f"new_articles={upsert_result.get('new_article_count')})."
                        )
                    
                    # 5. Remove from heavy_clusters.log
                    self._remove_from_log(cid)
                    
                else:
                    err = synthesis_result.get('error') if isinstance(synthesis_result, dict) else str(synthesis_result)
                    logger.error(f"Retry failed for heavy cluster {cid}: {err}")
                    # Do not remove from log, so it can be retried again later (maybe infinite loop if keeps failing? user can check log)
                    
            except Exception as e:
                logger.error(f"Error processing heavy cluster {cid}: {e}")

    def _remove_from_log(self, cid_to_remove: str):
        try:
            failed_log_path = "heavy_clusters.log"
            if not os.path.exists(failed_log_path):
                return
                
            with open(failed_log_path, "r") as f:
                lines = f.readlines()
            
            new_lines = []
            for line in lines:
                try:
                    rec = json.loads(line)
                    if rec.get("cluster_id") != cid_to_remove:
                        new_lines.append(line)
                except:
                    new_lines.append(line)
            
            with open(failed_log_path, "w") as f:
                f.writelines(new_lines)
                
            logger.info(f"Removed {cid_to_remove} from {failed_log_path}")
        except Exception as e:
            logger.error(f"Failed to update heavy_clusters.log: {e}")





class SynthesisToCritiquePolicy(WorkflowPolicy):
    """
    Policy: Synthesized -> Critiqued
    Condition: synthesized_articles.critique_status IS NULL OR 'pending'
               AND is_published = 0
    Action: Call 'critic.critique_synthesis'
    """
    def name(self) -> str:
        return "synthesis_to_critique"

    def check_condition(self, limit: int) -> List[str]:
        ids = []
        try:
            self.db_service.ensure_conn()
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            query = """
                SELECT story_id FROM synthesized_articles 
                WHERE is_published = 0 
                  AND (critique_status IS NULL OR critique_status = 'pending')
                ORDER BY created_at ASC
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[str]):
        logger.info(f"Triggering critique for {len(items)} stories.")
        
        for story_id in items:
            try:
                # Fetch story body
                self.db_service.ensure_conn()
                cursor = self.db_service.mb_conn.cursor()
                cursor.execute("SELECT body, title FROM synthesized_articles WHERE story_id = %s", (story_id,))
                row = cursor.fetchone()
                cursor.close()
                
                if not row:
                    continue
                    
                body = row[0]
                title = row[1]
                content_to_critique = f"Title: {title}\n\n{body}"
                
                # Call Critic
                result = await self._call_mcp_tool(
                    agent="critic",
                    tool="critique_synthesis",
                    kwargs={"content": content_to_critique}
                )
                
                if isinstance(result, dict):
                    # Save critique
                    critique_text = json.dumps(result)
                    self.db_service.ensure_conn()
                    cursor = self.db_service.mb_conn.cursor()
                    cursor.execute(
                        """UPDATE synthesized_articles 
                           SET critique_status = 'completed', critique_text = %s 
                           WHERE story_id = %s""",
                        (critique_text, story_id)
                    )
                    self.db_service.mb_conn.commit()
                    cursor.close()
                    logger.info(f"✅ Critiqued story {story_id}")
                else:
                    logger.error(f"Critique failed for {story_id}: {result}")
            except Exception as e:
                logger.error(f"Error critiquing story {story_id}: {e}")


class SynthesisToPublishingPolicy(WorkflowPolicy):
    """
    Policy: Synthesized & Critiqued -> Published
    Condition: synthesized_articles.is_published = 0 AND critique_status = 'completed'
    Action: Call 'chief_editor.publish_story'
    """

    def name(self) -> str:
        return "synthesis_to_publishing"

    def check_condition(self, limit: int) -> List[str]:
        ids = []
        try:
            self.db_service.ensure_conn()
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            
            # Select unpublished stories that have been critiqued
            query = """
                SELECT story_id FROM synthesized_articles 
                WHERE is_published = 0 
                  AND critique_status = 'completed'
                ORDER BY created_at ASC
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[str]):
        logger.info(f"Triggering publishing for {len(items)} stories.")
        
        for story_id in items:
            try:
                logger.info(f"Publishing story {story_id}...")
                
                # 1. Call Chief Editor
                result = await self._call_mcp_tool(
                    agent="chief_editor",
                    tool="publish_story",
                    kwargs={"story_id": story_id}
                )
                
                # Unpack EditorialResponse if present
                if isinstance(result, dict) and "result" in result and "status" not in result:
                    result = result["result"]

                # 2. Update DB on Success
                # We accept 'published' or 'published_locally'
                if isinstance(result, dict) and "published" in result.get("status", ""):
                    try:
                        record_living_story_publish_telemetry(self.db_service, story_id)
                    except Exception as telemetry_error:
                        logger.warning(f"Failed to record publish telemetry for {story_id}: {telemetry_error}")
                    logger.info(f"✅ Published story {story_id}")
                else:
                    err = result.get('error') if isinstance(result, dict) else str(result)
                    logger.error(f"Publishing failed for {story_id}: {err}")
                    
            except Exception as e:
                logger.error(f"Error publishing story {story_id}: {e}")
