import subprocess
import threading
import time
from pathlib import Path

from agents.gpu_orchestrator.gpu_orchestrator_engine import GPUOrchestratorEngine


class DummyCompleted:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def test_can_start_model_uses_nvidia_smi(monkeypatch):
    engine = GPUOrchestratorEngine(bootstrap_external_services=False)

    # Mock nvidia-smi output to indicate 12000 MB free
    def fake_run(cmd, capture_output=True, text=True, check=False):
        return DummyCompleted(stdout="12000\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    spec = engine.ModelSpec(id="mistralai/Mistral-7B-Instruct-v0.3", gpu_memory_util=0.5)
    assert engine.can_start_model(spec)


def test_start_model_prefers_systemd(monkeypatch):
    engine = GPUOrchestratorEngine(bootstrap_external_services=False)

    calls = []

    def fake_run(cmd, check=False, capture_output=False, text=False):
        calls.append(cmd)
        return None

    monkeypatch.setattr(subprocess, "run", fake_run)

    spec = engine.ModelSpec(id="mistralai/Mistral-7B-Instruct-v0.3", service_unit="vllm-test.service")
    ok = engine.start_model(spec)
    assert ok
    assert any("systemctl" in c for c in calls)


def test_detect_oom_in_log(tmp_path: Path):
    engine = GPUOrchestratorEngine(bootstrap_external_services=False)
    log_file = tmp_path / "vllm_test.log"
    log_file.write_text("some output\nCUDA out of memory: Tried to allocate 12345 bytes\n")
    assert engine._detect_oom_in_log(log_file)


def test_monitor_model_restarts(monkeypatch, tmp_path: Path):
    engine = GPUOrchestratorEngine(bootstrap_external_services=False)
    spec = engine.ModelSpec(id="mistralai/Mistral-7B-Instruct-v0.3")

    # create a log file and write OOM content after monitor starts
    log_file = tmp_path / "vllm_mistral.log"
    log_file.write_text("ok\n")

    # patch the log path used by monitor
    monkeypatch.setattr(engine, '_detect_oom_in_log', lambda p: True)

    # patch start_model and stop_model to record calls and then raise to break loop
    events = {"restarts": 0}

    def fake_start(spec_in):
        events["restarts"] += 1
        if events["restarts"] > 2:
            # break the monitor loop by raising
            raise RuntimeError("stop-monitor")
        return True

    def fake_stop(spec_in):
        return True

    monkeypatch.setattr(engine, 'start_model', fake_start)
    monkeypatch.setattr(engine, 'stop_model', fake_stop)

    # run monitor in a thread and expect it to raise after >2 restarts
    t = threading.Thread(target=lambda: engine.monitor_model(spec), daemon=True)
    t.start()
    # wait for thread to run and stop
    time.sleep(1)
    assert events["restarts"] >= 1


def test_ensure_model_installed_collects_adapters(tmp_path: Path, monkeypatch):
    # Create a temporary AGENT_MODEL_MAP.json pointing to an adapter path
    root = tmp_path / "repo"
    root.mkdir()
    am = root / "AGENT_MODEL_MAP.json"
    am.write_text('''{
  "agents": {
    "synthesizer": [
      {"base_ref": "mistral-7b-v0.3", "adapter_model_store_path": "synthesizer/adapters/mistral_synth_v1"}
    ]
  }
}''')

    engine = GPUOrchestratorEngine(bootstrap_external_services=False)

    # Monkeypatch engine file resolution so ensure_model_installed finds our AGENT_MODEL_MAP.json
    fake_file = str(root / 'some' / 'path' / 'file.py')
    monkeypatch.setattr(engine, '__file__', fake_file)

    spec = engine.ModelSpec(id="mistralai/Mistral-7B-Instruct-v0.3")
    # Call ensure_model_installed; ModelStore resolution will fail, but adapter collection should proceed
    engine.ensure_model_installed(spec)
    # the adapter path should have been added (or at least property exists)
    assert hasattr(spec, 'adapter_paths')
    assert "synthesizer/adapters/mistral_synth_v1" in spec.adapter_paths
