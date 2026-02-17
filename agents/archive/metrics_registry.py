"""Shared metrics registry for the archive agent."""

from __future__ import annotations

from common.metrics import JustNewsMetrics
from common.stage_b_metrics import configure_stage_b_metrics

metrics = JustNewsMetrics("archive")
configure_stage_b_metrics(metrics.registry)

__all__ = ["metrics"]
