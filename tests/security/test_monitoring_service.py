import asyncio
import importlib.util
import os
import types as _types

# Load security.models directly (avoid importing package __init__ with side-effects)
root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
models_path = os.path.join(root, "security", "models.py")
spec = importlib.util.spec_from_file_location("security.models", models_path)
models_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models_mod)

# Inject a lightweight security package into sys.modules so relative imports inside
# the monitoring service resolve to the models module without running package __init__
import sys as _sys  # noqa: E402

security_pkg = _types.ModuleType("security")
security_pkg.models = models_mod
_sys.modules["security"] = security_pkg
_sys.modules["security.models"] = models_mod

# Load the monitoring service module from file
svc_path = os.path.join(root, "security", "monitoring", "service.py")
spec2 = importlib.util.spec_from_file_location("security.monitoring.service", svc_path)
svc_mod = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(svc_mod)

SecurityConfig = models_mod.SecurityConfig
SecurityMonitor = svc_mod.SecurityMonitor
MonitoringRule = svc_mod.MonitoringRule
AlertSeverity = svc_mod.AlertSeverity


def build_cfg():
    return SecurityConfig(jwt_secret="x" * 32)


async def _drain_events(svc: SecurityMonitor):
    # helper to allow async tasks to run
    await asyncio.sleep(0)


def test_log_security_events_and_generate_alert(monkeypatch):
    cfg = build_cfg()
    svc = SecurityMonitor(cfg)

    # avoid writing files
    async def _noop(*a, **k):
        return None

    svc._save_monitoring_data = _noop

    # make a handler that appends alerts
    captured = []

    async def handler(alert):
        captured.append(alert)

    asyncio.run(svc.add_alert_handler(handler))

    ip = "1.2.3.4"
    # Log 5 authentication_failure events from same IP to trigger brute_force_login rule
    for _ in range(5):
        asyncio.run(
            svc.log_security_event(
                "authentication_failure",
                None,
                {"ip_address": ip},
                severity=AlertSeverity.MEDIUM,
            )
        )

    # Allow event loop to process rule evaluation
    asyncio.run(_drain_events(svc))

    # There should be at least one active alert generated
    active = asyncio.run(svc.get_active_alerts())
    assert isinstance(active, list)
    assert len(active) >= 1


def test_get_security_metrics_and_rule_manipulation():
    cfg = build_cfg()
    svc = SecurityMonitor(cfg)

    async def _noop(*a, **k):
        return None

    svc._save_monitoring_data = _noop

    # Add a custom rule and then remove it
    rule = MonitoringRule(
        id="test_rule",
        name="Test",
        description="Test rule",
        event_pattern={"event_type": "suspicious_activity"},
        condition="True",
        severity=AlertSeverity.LOW,
    )
    asyncio.run(svc.add_monitoring_rule(rule))
    rules = svc.get_monitoring_rules()
    assert "test_rule" in rules

    asyncio.run(svc.remove_monitoring_rule("test_rule"))
    rules2 = svc.get_monitoring_rules()
    assert "test_rule" not in rules2

    # Log a few events and check metrics
    asyncio.run(
        svc.log_security_event(
            "suspicious_activity",
            None,
            {"ip_address": None},
            severity=AlertSeverity.LOW,
        )
    )
    metrics = asyncio.run(svc.get_security_metrics(hours=1))
    assert metrics.total_events >= 1
