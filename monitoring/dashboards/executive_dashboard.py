"""
Executive Dashboard for JustNews Monitoring System

This module provides executive-level dashboards with business KPIs,
high-level metrics, and strategic insights for management and stakeholders.
It aggregates data from all monitoring systems into executive summaries.

Author: JustNews Development Team
Date: October 22, 2025
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# Configure logging
logger = logging.getLogger(__name__)


class KPICategory(Enum):
    """KPI categories"""

    BUSINESS = "business"
    TECHNICAL = "technical"
    OPERATIONAL = "operational"
    SECURITY = "security"
    COMPLIANCE = "compliance"


class KPIStatus(Enum):
    """KPI status indicators"""

    EXCELLENT = "excellent"
    GOOD = "good"
    WARNING = "warning"
    CRITICAL = "critical"


class ExecutiveMetric(BaseModel):
    """Executive-level metric"""

    name: str = Field(..., description="Metric name")
    value: int | float | str = Field(..., description="Current value")
    unit: str = Field("", description="Unit of measurement")
    change_percent: float | None = Field(
        None, description="Percentage change from previous period"
    )
    trend: str = Field("stable", description="Trend direction: up, down, stable")
    status: KPIStatus = Field(KPIStatus.GOOD, description="Current status")
    target: int | float | None = Field(None, description="Target value")
    category: KPICategory = Field(..., description="KPI category")
    description: str = Field(..., description="Metric description")
    last_updated: datetime = Field(
        default_factory=datetime.now, description="Last update timestamp"
    )


class BusinessKPI(BaseModel):
    """Business Key Performance Indicator"""

    name: str = Field(..., description="KPI name")
    value: int | float = Field(..., description="Current value")
    target: int | float = Field(..., description="Target value")
    period: str = Field("monthly", description="Reporting period")
    status: KPIStatus = Field(..., description="KPI status")
    trend: str = Field("stable", description="Performance trend")
    impact: str = Field("medium", description="Business impact level")
    owner: str = Field("", description="Responsible person/team")
    last_updated: datetime = Field(
        default_factory=datetime.now, description="Last update"
    )


class ExecutiveSummary(BaseModel):
    """Executive summary data"""

    period: str = Field(..., description="Reporting period")
    overall_status: KPIStatus = Field(..., description="Overall system status")
    key_highlights: list[str] = Field(
        default_factory=list, description="Key achievements/highlights"
    )
    critical_issues: list[str] = Field(
        default_factory=list, description="Critical issues requiring attention"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Strategic recommendations"
    )
    risk_assessment: str = Field("", description="Overall risk assessment")
    next_steps: list[str] = Field(
        default_factory=list, description="Recommended next steps"
    )


@dataclass
class ExecutiveDashboard:
    """
    Executive dashboard providing business KPIs and high-level metrics.

    This class aggregates data from all monitoring systems into executive-level
    summaries, KPIs, and strategic insights for management decision-making.
    """

    # Core KPIs
    business_kpis: dict[str, BusinessKPI] = field(default_factory=dict)

    # Executive metrics
    executive_metrics: dict[str, ExecutiveMetric] = field(default_factory=dict)

    # Historical data for trend analysis
    historical_data: dict[str, list[tuple[datetime, int | float]]] = field(
        default_factory=dict
    )

    # Dashboard configuration
    update_interval: int = field(default=300)  # 5 minutes
    retention_days: int = field(default=90)

    # Status thresholds
    status_thresholds: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "cpu_usage": {"warning": 70.0, "critical": 90.0},
            "memory_usage": {"warning": 80.0, "critical": 95.0},
            "error_rate": {"warning": 2.0, "critical": 5.0},
            "response_time": {"warning": 1.0, "critical": 3.0},
            "uptime": {"warning": 99.5, "critical": 99.0},
        }
    )

    def __post_init__(self):
        """Initialize executive dashboard"""
        self._setup_default_kpis()
        self._setup_default_metrics()

    def _setup_default_kpis(self):
        """Setup default business KPIs"""
        default_kpis = [
            BusinessKPI(
                name="Monthly Active Users",
                value=15420,
                target=20000,
                period="monthly",
                status=KPIStatus.GOOD,
                trend="up",
                impact="high",
                owner="Product Team",
            ),
            BusinessKPI(
                name="Content Accuracy Score",
                value=94.2,
                target=95.0,
                period="monthly",
                status=KPIStatus.WARNING,
                trend="stable",
                impact="high",
                owner="Content Team",
            ),
            BusinessKPI(
                name="System Uptime",
                value=99.7,
                target=99.9,
                period="monthly",
                status=KPIStatus.GOOD,
                trend="stable",
                impact="critical",
                owner="DevOps Team",
            ),
            BusinessKPI(
                name="Revenue Growth",
                value=12.5,
                target=15.0,
                period="quarterly",
                status=KPIStatus.WARNING,
                trend="up",
                impact="high",
                owner="Business Team",
            ),
            BusinessKPI(
                name="Customer Satisfaction",
                value=4.2,
                target=4.5,
                period="quarterly",
                status=KPIStatus.GOOD,
                trend="up",
                impact="high",
                owner="Support Team",
            ),
        ]

        for kpi in default_kpis:
            self.business_kpis[kpi.name] = kpi

    def _setup_default_metrics(self):
        """Setup default executive metrics"""
        default_metrics = [
            ExecutiveMetric(
                name="Total Revenue",
                value=45230.50,
                unit="$",
                change_percent=8.5,
                trend="up",
                status=KPIStatus.GOOD,
                target=50000.0,
                category=KPICategory.BUSINESS,
                description="Total monthly revenue from all sources",
            ),
            ExecutiveMetric(
                name="System Uptime",
                value=99.7,
                unit="%",
                change_percent=0.1,
                trend="stable",
                status=KPIStatus.GOOD,
                target=99.9,
                category=KPICategory.TECHNICAL,
                description="Overall system availability percentage",
            ),
            ExecutiveMetric(
                name="Average Response Time",
                value=0.234,
                unit="seconds",
                change_percent=-5.2,
                trend="down",
                status=KPIStatus.GOOD,
                target=0.3,
                category=KPICategory.TECHNICAL,
                description="Average API response time across all services",
            ),
            ExecutiveMetric(
                name="Active Security Alerts",
                value=2,
                unit="count",
                change_percent=-50.0,
                trend="down",
                status=KPIStatus.WARNING,
                target=0,
                category=KPICategory.SECURITY,
                description="Number of currently active security alerts",
            ),
            ExecutiveMetric(
                name="Content Processing Rate",
                value=1250,
                unit="articles/hour",
                change_percent=15.3,
                trend="up",
                status=KPIStatus.GOOD,
                target=1000,
                category=KPICategory.OPERATIONAL,
                description="Rate of news content processing and analysis",
            ),
            ExecutiveMetric(
                name="Compliance Violations",
                value=0,
                unit="count",
                change_percent=0.0,
                trend="stable",
                status=KPIStatus.EXCELLENT,
                target=0,
                category=KPICategory.COMPLIANCE,
                description="Number of compliance violations this month",
            ),
        ]

        for metric in default_metrics:
            self.executive_metrics[metric.name] = metric

    async def update_metrics(self, metrics_data: dict[str, Any]):
        """
        Update executive metrics with new data

        Args:
            metrics_data: Dictionary of metric updates
        """
        for metric_name, value in metrics_data.items():
            if metric_name in self.executive_metrics:
                await self._update_metric(metric_name, value)
            elif metric_name in [kpi.name for kpi in self.business_kpis.values()]:
                await self._update_kpi(metric_name, value)

        # Update derived metrics
        await self._update_derived_metrics()

        logger.info("Updated executive dashboard metrics")

    async def _update_metric(self, metric_name: str, value: int | float):
        """Update a specific executive metric"""
        if metric_name not in self.executive_metrics:
            # Create the metric if it doesn't exist (for derived metrics)
            if "Health" in metric_name:
                category = KPICategory.TECHNICAL
                description = "Overall system health score"
            elif "Risk" in metric_name:
                category = KPICategory.SECURITY
                description = "Overall system risk score"
            else:
                category = KPICategory.OPERATIONAL
                description = f"Metric: {metric_name}"

            self.executive_metrics[metric_name] = ExecutiveMetric(
                name=metric_name,
                value=value,
                category=category,
                description=description,
            )
            # Initialize historical data
            if metric_name not in self.historical_data:
                self.historical_data[metric_name] = []
            self.historical_data[metric_name].append((datetime.now(), value))
            return

        metric = self.executive_metrics[metric_name]

        # Calculate change percentage
        if metric.value != 0:
            old_value = metric.value
            metric.change_percent = ((value - old_value) / old_value) * 100

            # Determine trend
            if value > old_value:
                metric.trend = "up"
            elif value < old_value:
                metric.trend = "down"
            else:
                metric.trend = "stable"

        # Update value and status
        metric.value = value
        metric.status = self._calculate_metric_status(metric)
        metric.last_updated = datetime.now()

        # Store historical data
        if metric_name not in self.historical_data:
            self.historical_data[metric_name] = []
        self.historical_data[metric_name].append((datetime.now(), value))

        # Maintain retention period
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        self.historical_data[metric_name] = [
            (ts, val) for ts, val in self.historical_data[metric_name] if ts >= cutoff
        ]

    async def _update_kpi(self, kpi_name: str, value: int | float):
        """Update a specific business KPI"""
        kpi = self.business_kpis[kpi_name]
        kpi.value = value
        kpi.status = self._calculate_kpi_status(kpi)
        kpi.last_updated = datetime.now()

        # Calculate trend based on target achievement
        if kpi.target > 0:
            achievement_rate = (kpi.value / kpi.target) * 100
            if achievement_rate >= 100:
                kpi.trend = "excellent"
            elif achievement_rate >= 90:
                kpi.trend = "good"
            elif achievement_rate >= 75:
                kpi.trend = "warning"
            else:
                kpi.trend = "critical"

    async def _update_derived_metrics(self):
        """Update metrics derived from other data"""
        # Calculate overall system health score
        health_score = await self._calculate_system_health_score()
        await self._update_metric("System Health Score", health_score)

        # Calculate risk score
        risk_score = await self._calculate_risk_score()
        await self._update_metric("Risk Score", risk_score)

    async def _calculate_system_health_score(self) -> float:
        """Calculate overall system health score (0-100)"""
        scores = []

        # CPU health (inverse of usage)
        cpu_usage = self.executive_metrics.get(
            "CPU Usage",
            ExecutiveMetric(
                name="CPU Usage",
                value=50,
                category=KPICategory.TECHNICAL,
                description="CPU usage percentage",
            ),
        )
        cpu_score = max(0, 100 - cpu_usage.value)
        scores.append(cpu_score)

        # Memory health
        memory_usage = self.executive_metrics.get(
            "Memory Usage",
            ExecutiveMetric(
                name="Memory Usage",
                value=60,
                category=KPICategory.TECHNICAL,
                description="Memory usage percentage",
            ),
        )
        memory_score = max(0, 100 - memory_usage.value)
        scores.append(memory_score)

        # Uptime score
        uptime = self.executive_metrics.get(
            "System Uptime",
            ExecutiveMetric(
                name="System Uptime",
                value=99.5,
                category=KPICategory.TECHNICAL,
                description="System uptime percentage",
            ),
        )
        uptime_score = uptime.value
        scores.append(uptime_score)

        # Error rate score (inverse)
        error_rate = self.executive_metrics.get(
            "Error Rate",
            ExecutiveMetric(
                name="Error Rate",
                value=1.0,
                category=KPICategory.OPERATIONAL,
                description="Error rate percentage",
            ),
        )
        error_score = max(0, 100 - (error_rate.value * 20))  # 5% error = 0 score
        scores.append(error_score)

        return statistics.mean(scores) if scores else 50.0

    async def _calculate_risk_score(self) -> float:
        """Calculate overall risk score (0-100, higher = more risk)"""
        risk_factors = []

        # Security alerts increase risk
        security_alerts = self.executive_metrics.get(
            "Active Security Alerts",
            ExecutiveMetric(
                name="Active Security Alerts",
                value=0,
                category=KPICategory.SECURITY,
                description="Number of active security alerts",
            ),
        )
        risk_factors.append(
            min(security_alerts.value * 10, 50)
        )  # Max 50 points for security

        # High error rates increase risk
        error_rate = self.executive_metrics.get(
            "Error Rate",
            ExecutiveMetric(
                name="Error Rate",
                value=1.0,
                category=KPICategory.OPERATIONAL,
                description="Error rate percentage",
            ),
        )
        risk_factors.append(min(error_rate.value * 5, 25))  # Max 25 points for errors

        # Low uptime increases risk
        uptime = self.executive_metrics.get(
            "System Uptime",
            ExecutiveMetric(
                name="System Uptime",
                value=99.5,
                category=KPICategory.TECHNICAL,
                description="System uptime percentage",
            ),
        )
        uptime_risk = max(0, (100 - uptime.value) * 2)  # 1% downtime = 2 risk points
        risk_factors.append(min(uptime_risk, 25))

        return min(sum(risk_factors), 100.0)

    def _calculate_metric_status(self, metric: ExecutiveMetric) -> KPIStatus:
        """Calculate status for an executive metric"""
        if metric.target is None:
            return KPIStatus.GOOD

        # Define status based on target achievement
        if metric.target == 0 or metric.target is None:
            # For metrics where target is 0 or None, use absolute value thresholds
            if metric.category == KPICategory.SECURITY:
                # For security metrics, lower values are better
                if metric.value == 0:
                    return KPIStatus.EXCELLENT
                elif metric.value <= 2:
                    return KPIStatus.GOOD
                elif metric.value <= 5:
                    return KPIStatus.WARNING
                else:
                    return KPIStatus.CRITICAL
            else:
                # For other metrics, use general thresholds
                if isinstance(metric.value, (int, float)):
                    if metric.value >= 95:
                        return KPIStatus.EXCELLENT
                    elif metric.value >= 80:
                        return KPIStatus.GOOD
                    elif metric.value >= 60:
                        return KPIStatus.WARNING
                    else:
                        return KPIStatus.CRITICAL
                else:
                    return KPIStatus.GOOD

        achievement_rate = (
            (metric.value / metric.target) * 100
            if isinstance(metric.value, (int, float))
            else 50
        )

        if metric.category == KPICategory.SECURITY:
            # For security metrics, lower values are better
            if metric.value == 0:
                return KPIStatus.EXCELLENT
            elif metric.value <= 2:
                return KPIStatus.GOOD
            elif metric.value <= 5:
                return KPIStatus.WARNING
            else:
                return KPIStatus.CRITICAL
        else:
            # For other metrics, higher achievement is better
            if achievement_rate >= 100:
                return KPIStatus.EXCELLENT
            elif achievement_rate >= 90:
                return KPIStatus.GOOD
            elif achievement_rate >= 75:
                return KPIStatus.WARNING
            else:
                return KPIStatus.CRITICAL

    def _calculate_kpi_status(self, kpi: BusinessKPI) -> KPIStatus:
        """Calculate status for a business KPI"""
        if kpi.target == 0:
            return KPIStatus.GOOD

        achievement_rate = (kpi.value / kpi.target) * 100

        if achievement_rate >= 100:
            return KPIStatus.EXCELLENT
        elif achievement_rate >= 90:
            return KPIStatus.GOOD
        elif achievement_rate >= 75:
            return KPIStatus.WARNING
        else:
            return KPIStatus.CRITICAL

    def get_executive_summary(self, period: str = "monthly") -> ExecutiveSummary:
        """
        Generate executive summary for the specified period

        Args:
            period: Time period for the summary

        Returns:
            ExecutiveSummary with key insights and recommendations
        """
        # Calculate overall status
        overall_status = self._calculate_overall_status()

        # Generate key highlights
        highlights = self._generate_key_highlights()

        # Identify critical issues
        critical_issues = self._identify_critical_issues()

        # Generate recommendations
        recommendations = self._generate_recommendations()

        # Assess risk
        risk_assessment = self._assess_risk()

        # Define next steps
        next_steps = self._define_next_steps()

        return ExecutiveSummary(
            period=period,
            overall_status=overall_status,
            key_highlights=highlights,
            critical_issues=critical_issues,
            recommendations=recommendations,
            risk_assessment=risk_assessment,
            next_steps=next_steps,
        )

    def _calculate_overall_status(self) -> KPIStatus:
        """Calculate overall system status"""
        statuses = [metric.status for metric in self.executive_metrics.values()]
        status_counts = {
            KPIStatus.EXCELLENT: statuses.count(KPIStatus.EXCELLENT),
            KPIStatus.GOOD: statuses.count(KPIStatus.GOOD),
            KPIStatus.WARNING: statuses.count(KPIStatus.WARNING),
            KPIStatus.CRITICAL: statuses.count(KPIStatus.CRITICAL),
        }

        # Overall status based on worst performing metrics
        if status_counts[KPIStatus.CRITICAL] > 0:
            return KPIStatus.CRITICAL
        elif status_counts[KPIStatus.WARNING] > 2:
            return KPIStatus.WARNING
        elif status_counts[KPIStatus.GOOD] >= len(statuses) * 0.7:
            return KPIStatus.GOOD
        else:
            return KPIStatus.EXCELLENT

    def _generate_key_highlights(self) -> list[str]:
        """Generate key highlights for the executive summary"""
        highlights = []

        # Revenue growth
        revenue = self.executive_metrics.get("Total Revenue")
        if revenue and revenue.change_percent and revenue.change_percent > 5:
            highlights.append(
                f"Revenue growth of {revenue.change_percent:.1f}% this period"
            )

        # System uptime
        uptime = self.executive_metrics.get("System Uptime")
        if uptime and uptime.value >= 99.9:
            highlights.append(f"Excellent system uptime of {uptime.value:.1f}%")

        # Content processing
        processing = self.executive_metrics.get("Content Processing Rate")
        if processing and processing.change_percent and processing.change_percent > 10:
            highlights.append(
                f"Content processing rate improved by {processing.change_percent:.1f}%"
            )

        # Security
        security = self.executive_metrics.get("Compliance Violations")
        if security and security.value == 0:
            highlights.append("Zero compliance violations this period")

        if not highlights:
            highlights.append("System operating within normal parameters")

        return highlights

    def _identify_critical_issues(self) -> list[str]:
        """Identify critical issues requiring attention"""
        issues = []

        # Check for critical status metrics
        for metric in self.executive_metrics.values():
            if metric.status == KPIStatus.CRITICAL:
                issues.append(f"Critical: {metric.name} requires immediate attention")

        # Check for warning status metrics
        warning_count = sum(
            1 for m in self.executive_metrics.values() if m.status == KPIStatus.WARNING
        )
        if warning_count > 3:
            issues.append(
                f"Multiple warning conditions: {warning_count} metrics need monitoring"
            )

        # Security issues
        security_alerts = self.executive_metrics.get("Active Security Alerts")
        if security_alerts and security_alerts.value > 5:
            issues.append(
                f"High number of active security alerts: {security_alerts.value}"
            )

        return issues

    def _generate_recommendations(self) -> list[str]:
        """Generate strategic recommendations"""
        recommendations = []

        # Based on metric trends and status
        for metric in self.executive_metrics.values():
            if metric.status == KPIStatus.WARNING and metric.trend == "down":
                recommendations.append(
                    f"Investigate declining {metric.name.lower()} and implement corrective actions"
                )
            elif metric.status == KPIStatus.CRITICAL:
                recommendations.append(
                    f"Immediate action required for {metric.name.lower()}"
                )

        # Capacity planning
        cpu_usage = self.executive_metrics.get("CPU Usage")
        if cpu_usage and cpu_usage.value > 80:
            recommendations.append(
                "Consider scaling compute resources to handle increased load"
            )

        # Process improvements
        error_rate = self.executive_metrics.get("Error Rate")
        if error_rate and error_rate.value > 2:
            recommendations.append(
                "Review error handling and implement process improvements"
            )

        if not recommendations:
            recommendations.append(
                "Continue monitoring system performance and maintain current operational excellence"
            )

        return recommendations

    def _assess_risk(self) -> str:
        """Assess overall system risk"""
        risk_score = self.executive_metrics.get(
            "Risk Score",
            ExecutiveMetric(
                name="Risk Score",
                value=20,
                category=KPICategory.OPERATIONAL,
                description="Overall system risk score",
            ),
        )

        if risk_score.value < 20:
            return "Low - System operating normally with minimal risk"
        elif risk_score.value < 40:
            return "Medium - Some areas require monitoring and attention"
        elif risk_score.value < 70:
            return "High - Multiple risk factors present, action recommended"
        else:
            return "Critical - Immediate risk mitigation required"

    def _define_next_steps(self) -> list[str]:
        """Define recommended next steps"""
        next_steps = []

        # Based on current status and trends
        overall_status = self._calculate_overall_status()

        if overall_status == KPIStatus.CRITICAL:
            next_steps.extend(
                [
                    "Immediate: Activate incident response team",
                    "Review and address all critical alerts",
                    "Conduct post-mortem analysis after resolution",
                ]
            )
        elif overall_status == KPIStatus.WARNING:
            next_steps.extend(
                [
                    "Monitor warning conditions closely",
                    "Implement planned improvements for affected metrics",
                    "Schedule review meeting with stakeholders",
                ]
            )
        else:
            next_steps.extend(
                [
                    "Continue performance optimization initiatives",
                    "Plan capacity upgrades based on growth trends",
                    "Conduct regular system health reviews",
                ]
            )

        return next_steps

    def get_metric_trend(self, metric_name: str, days: int = 7) -> dict[str, Any]:
        """
        Get trend analysis for a specific metric

        Args:
            metric_name: Name of the metric
            days: Number of days to analyze

        Returns:
            Dictionary with trend analysis data
        """
        if metric_name not in self.historical_data:
            return {"error": f"No historical data for metric '{metric_name}'"}

        data = self.historical_data[metric_name]
        cutoff = datetime.now() - timedelta(days=days)
        recent_data = [(ts, val) for ts, val in data if ts >= cutoff]

        if len(recent_data) < 2:
            return {
                "trend": "insufficient_data",
                "change": 0,
                "data_points": len(recent_data),
            }

        values = [val for _, val in recent_data]
        start_value = values[0]
        end_value = values[-1]

        if start_value == 0:
            change_percent = 0
        else:
            change_percent = ((end_value - start_value) / start_value) * 100

        # Determine trend
        if change_percent > 5:
            trend = "increasing"
        elif change_percent < -5:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "change_percent": change_percent,
            "start_value": start_value,
            "end_value": end_value,
            "data_points": len(recent_data),
            "period_days": days,
        }

    def export_dashboard_data(self) -> dict[str, Any]:
        """Export all dashboard data for reporting"""
        return {
            "business_kpis": [kpi.model_dump() for kpi in self.business_kpis.values()],
            "executive_metrics": [
                metric.model_dump() for metric in self.executive_metrics.values()
            ],
            "executive_summary": self.get_executive_summary().model_dump(),
            "export_timestamp": datetime.now().isoformat(),
            "data_retention_days": self.retention_days,
        }

    async def cleanup_old_data(self):
        """Clean up old historical data beyond retention period"""
        cutoff = datetime.now() - timedelta(days=self.retention_days)

        for metric_name in self.historical_data:
            original_count = len(self.historical_data[metric_name])
            self.historical_data[metric_name] = [
                (ts, val)
                for ts, val in self.historical_data[metric_name]
                if ts >= cutoff
            ]
            removed_count = original_count - len(self.historical_data[metric_name])
            if removed_count > 0:
                logger.info(
                    f"Cleaned up {removed_count} old data points for metric '{metric_name}'"
                )
