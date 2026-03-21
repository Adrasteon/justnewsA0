from agents.workflow_orchestrator.runtime_config import RuntimeConfigStore


def test_runtime_config_accepts_traceability_lane_keys(tmp_path):
    state_path = tmp_path / 'runtime_state.json'
    store = RuntimeConfigStore(state_path=state_path)

    patch = {
        'orchestrator.lane1.seed_count': 10,
        'orchestrator.lane1.max_related_per_seed': 5,
        'orchestrator.lane1.ddg_enabled': True,
        'orchestrator.balance_policy.enabled': True,
        'orchestrator.balance_policy.min_distinct_sides': 2,
    }

    validated = store.validate_patch(patch)
    assert validated.ok is True
    assert validated.errors == []
    assert validated.normalized['orchestrator.lane1.seed_count'] == 10


def test_runtime_config_accepts_discovery_kill_switch_keys(tmp_path):
    state_path = tmp_path / 'runtime_state.json'
    store = RuntimeConfigStore(state_path=state_path)

    patch = {
        'orchestrator.discovery.enabled': True,
        'orchestrator.discovery.offsite_follow_enabled': False,
        'orchestrator.discovery.provisional_ingest_enabled': True,
        'orchestrator.discovery.whitelist_only_mode': False,
    }

    validated = store.validate_patch(patch)
    assert validated.ok is True
    assert validated.errors == []
    assert validated.normalized['orchestrator.discovery.enabled'] is True
