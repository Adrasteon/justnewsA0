from datetime import datetime, timezone

from agents.workflow_orchestrator.engine import OrchestratorEngine
from agents.workflow_orchestrator.resources import SystemStats


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _build_engine(monkeypatch) -> OrchestratorEngine:
    monkeypatch.setattr(OrchestratorEngine, '_init_policies', lambda self: None)
    monkeypatch.setattr(
        OrchestratorEngine,
        '_load_config',
        lambda self: setattr(
            self,
            'config',
            {
                'polling_interval_seconds': 10,
                'max_concurrent_tasks': 5,
                'resource_limits': {
                    'max_cpu_percent': 95,
                    'max_memory_percent': 98,
                    'max_gpu_utilization': 95,
                    'max_gpu_memory_percent': 95,
                },
            },
        ),
    )
    return OrchestratorEngine()


def test_autonomic_backlog_floor_recovery_scales_up_with_headroom(monkeypatch):
    engine = _build_engine(monkeypatch)
    engine.config['polling_interval_seconds'] = 17
    engine.config['max_concurrent_tasks'] = 1

    engine._last_resource_stats = SystemStats(cpu_percent=33.0, memory_percent=42.0, gpu_utilization=20.0)
    engine._last_resource_healthy = True
    engine.telemetry['progress']['last_progress_at'] = _iso_now()
    engine.telemetry['policies'] = {
        'ingestion_to_analysis': {
            'last_queue_depth': 12,
            'last_success_at_epoch': None,
            'check_count': 10,
            'error_count': 0,
            'last_execute_ms': 12.0,
        }
    }

    action = engine._compute_autonomic_action()

    assert action['reason'] == 'queue_backlog_floor_recovery'
    assert action['proposed_patch']['orchestrator.max_concurrent_tasks'] == 3
    assert action['proposed_patch']['orchestrator.polling_interval_seconds'] == 6


def test_autonomic_backlog_floor_recovery_is_blocked_by_resource_pressure(monkeypatch):
    engine = _build_engine(monkeypatch)
    engine.autonomic_action_streak_required = 1
    engine.config['polling_interval_seconds'] = 10
    engine.config['max_concurrent_tasks'] = 4

    engine._last_resource_stats = SystemStats(cpu_percent=96.0, memory_percent=70.0, gpu_utilization=10.0)
    engine._last_resource_healthy = False
    engine.telemetry['progress']['last_progress_at'] = _iso_now()
    engine.telemetry['policies'] = {
        'analysis_to_fact_check': {
            'last_queue_depth': 20,
            'last_success_at_epoch': None,
            'check_count': 10,
            'error_count': 0,
            'last_execute_ms': 20.0,
        }
    }

    action = engine._compute_autonomic_action()

    assert action['reason'] == 'resource_pressure'
    assert action['proposed_patch']['orchestrator.max_concurrent_tasks'] == 3
    assert action['proposed_patch']['orchestrator.polling_interval_seconds'] == 11


def test_autonomic_backlog_floor_recovery_holds_when_floor_already_met(monkeypatch):
    engine = _build_engine(monkeypatch)
    engine.config['polling_interval_seconds'] = 5
    engine.config['max_concurrent_tasks'] = 4

    engine._last_resource_stats = SystemStats(cpu_percent=41.0, memory_percent=50.0, gpu_utilization=24.0)
    engine._last_resource_healthy = True
    engine.telemetry['progress']['last_progress_at'] = _iso_now()
    engine.telemetry['policies'] = {
        'cluster_to_synthesis': {
            'last_queue_depth': 14,
            'last_success_at_epoch': None,
            'check_count': 10,
            'error_count': 0,
            'last_execute_ms': 44.0,
        }
    }

    action = engine._compute_autonomic_action()

    assert action['reason'] == 'stable_no_change'
    assert action['proposed_patch'] == {}
