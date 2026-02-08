from pathlib import Path

from agents.gpu_orchestrator.gpu_orchestrator_engine import GPUOrchestratorEngine


def test_loads_spec_and_attempts_start(monkeypatch, tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg_dir = repo / "config"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "vllm_mistral_7b.yaml"
    cfg_file.write_text('''model:
  id: "mistralai/Mistral-7B-Instruct-v0.3"
runtime:
  gpu_memory_util: 0.1
service:
  systemd_unit: vllm-test.service
''')

    # monkeypatch repo location resolution used by engine: Path(__file__).resolve().parents[2]
    engine = GPUOrchestratorEngine(bootstrap_external_services=False)
    monkeypatch.setattr(engine, '__file__', str(repo / 'some' / 'file.py'))

    started = {"called": False}

    def fake_ensure(spec):
        return None

    def fake_can(spec):
        return True

    def fake_start(spec):
        started["called"] = True
        return True

    monkeypatch.setattr(engine, 'ensure_model_installed', fake_ensure)
    monkeypatch.setattr(engine, 'can_start_model', fake_can)
    monkeypatch.setattr(engine, 'start_model', fake_start)

    # Re-run the block that loads the config
    engine._vllm_enabled = True
    engine.__init__(bootstrap_external_services=False)
    assert started["called"]
