# ModelSpec & GPU Orchestrator Integration

This document describes how models (canonical base models and per-agent adapters) are represented and managed by the
`gpu_orchestrator` agent.

Key points:

- Canonical model manifests live in `config/vllm_qwen.yaml`and the`AGENT_MODEL_MAP.json` maps adapters and agent-
  specific variants.

- The orchestrator manages a `ModelSpec`which
  includes:`id`,`dtype`,`gpu_memory_util`,`service_unit`(systemd),`memory_max`,`cpu_quota`, and`adapter_paths`.

- The orchestrator will attempt to resolve the model in the ModelStore via
  `models.model_loader._resolve_model_store_path`. If present, adapter paths are collected from`AGENT_MODEL_MAP.json`and
  written into the`ModelSpec`.

- When adapter paths are present, the orchestrator sets `VLLM_ADAPTER_PATHS` as a colon-delimited env var before
  starting the model process. The vLLM runtime must be configured to load PEFT/LoRA adapters from these paths when
  available.

Operational behavior:

- `gpu_orchestrator` will check free GPU memory and only start a model when safe headroom exists.

- Models are started via systemd user units if available, falling back to starting vLLM in-process if systemd is not
  available.

- The orchestrator monitors model logs for OOM and will attempt a bounded number of restarts with exponential backoff;
  after repeated failures the model is marked as degraded.

Telemetry & alerts:

- Metrics exported:
  `gpu_orchestrator_vllm_restarts_total`,`gpu_orchestrator_vllm_ooms_total`,`gpu_orchestrator_vllm_status`.

- GPU monitor will alert when free GPU memory is consistently low and can be used to trigger orchestration decisions.

Testing & developer notes:

- Unit tests for the `gpu_orchestrator`ModelSpec lifecycle live
  at`tests/agents/gpu_orchestrator/test_model_lifecycle.py`and cover adapter
  resolution,`can_start_model`checks,`start_model`/`stop_model` behaviour, OOM detection, and bounded restart logic.

- To run the orchestrator unit tests locally:

```bash
conda run -n justnews-py312 pytest -q tests/agents/gpu_orchestrator/test_model_lifecycle.py

```

- Tips for writing tests:

- Use `tmp_path` to create temporary log files and directories for model logs.

- Patch GPU checks (`_free_gpu_memory_mb`) to simulate headroom vs low memory cases.

- Mock systemd interactions or use the `service_unit` test double to avoid requiring sudo/systemd on CI.

- Validate that `VLLM_ADAPTER_PATHS`is set correctly when adapter mappings exist in`AGENT_MODEL_MAP.json`.

Rollout:

- Use `make monitor-install && make monitor-enable` to enable the GPU monitor.

- Install the example `vllm-qwen.service`with`cp infrastructure/systemd/vllm-qwen.service.example
  /etc/systemd/system/vllm-qwen.service`and`systemctl enable --now vllm-qwen` (run on host where vLLM is
  installed).

See also `docs/operations/VLLM_QWEN_SETUP.md` for vLLM-specific guidelines.
