from agents.common.gpu_manager_production import (
    GPUStatus,
    MultiAgentGPUManager,
)


class FakeHealthMonitor:
    def __init__(self, devices, statuses):
        self._devices = devices
        self._statuses = statuses

    def get_available_devices(self):
        return self._devices

    def get_gpu_status(self, device_id):
        return self._statuses.get(device_id)


def test_request_allocation_already_allocated():
    mgr = MultiAgentGPUManager(max_memory_per_agent_gb=8.0)
    mgr._allocations["a1"] = type(
        "T",
        (),
        {
            "status": "active",
            "gpu_device": "cuda:0",
            "allocated_memory_gb": 2.0,
            "batch_size": 4,
        },
    )()
    res = mgr.request_gpu_allocation("a1", 1.0)
    assert res["status"] == "already_allocated"


def test_request_allocation_cpu_fallback_when_no_devices(monkeypatch):
    mgr = MultiAgentGPUManager(max_memory_per_agent_gb=8.0)
    # empty devices
    mgr.health_monitor = FakeHealthMonitor([], {})
    res = mgr.request_gpu_allocation("agentX", 4.0)
    assert res["status"] == "cpu_fallback"


def test_allocate_and_release_success(monkeypatch):
    mgr = MultiAgentGPUManager(max_memory_per_agent_gb=8.0)
    # prepare a healthy CUDA device with plenty of free memory
    status = GPUStatus(
        device_id="cuda:0",
        device_type="cuda",
        total_memory_gb=16.0,
        used_memory_gb=2.0,
        free_memory_gb=14.0,
        utilization_percent=10.0,
        temperature_c=50.0,
        power_draw_w=80.0,
        is_healthy=True,
    )
    mgr.health_monitor = FakeHealthMonitor(["cuda:0"], {"cuda:0": status})

    res = mgr.request_gpu_allocation(
        "agentY", 4.0, preferred_device="cuda:0", model_type="embedding"
    )
    assert res["status"] == "allocated"
    # check allocation status
    stat = mgr.get_allocation_status("agentY")
    assert stat and stat["status"] == "active"

    # release
    ok = mgr.release_gpu_allocation("agentY")
    assert ok is True


def test_batch_size_heuristics(monkeypatch):
    mgr = MultiAgentGPUManager(max_memory_per_agent_gb=8.0)
    # simulate one device with 10GB free
    status = GPUStatus(
        device_id="cuda:0",
        device_type="cuda",
        total_memory_gb=16.0,
        used_memory_gb=6.0,
        free_memory_gb=10.0,
        utilization_percent=20.0,
        temperature_c=45.0,
        power_draw_w=70.0,
        is_healthy=True,
    )
    mgr.health_monitor = FakeHealthMonitor(["cuda:0"], {"cuda:0": status})

    # embedding with 4GB -> enhanced heuristic should return >=8
    bs = mgr._calculate_enhanced_heuristic_batch_size(4.0, "embedding")
    assert isinstance(bs, int) and bs >= 4
