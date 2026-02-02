# Adapter Specification — JustNews

This document defines the minimal adapter contract, best-practices and test guidance for adapters in the JustNews
codebase.

Purpose

- Provide a small, stable interface so agent engines, the GPU orchestrator, and other components can interact with model
  providers uniformly.

- Make adapters easy to test (dry-run) and to run in constrained CI environments.

Minimal contract (BaseAdapter)

- load(self, model_id: str, config: dict | None = None) -> None

- Prepare the model for inference, load weights/tokenizer or validate model path.

- Should be idempotent and quick to return if already loaded.

- infer(self, prompt: str, **kwargs) -> dict

- Run a single prompt synchronously and return a normalized dict with keys: text (str), raw (provider response), tokens
  (int), latency (float).

- batch_infer(self, prompts: list[str], **kwargs) -> list[dict]

- Batch inference, return a list of normalized dicts with the same shape as infer output.

- health_check(self) -> dict

- Return a small readiness dict containing at minimum {'loaded': bool, 'name': str}.

- unload(self) -> None

- Free resources loaded by this adapter (GPU memory, file handles, threads).

- metadata(self) -> dict

- Return a small metadata dict: { 'adapter': 'name', 'version': 'v1', 'device': 'cpu/gpu' }

Behavioral constraints & expectations

- Deterministic timeouts: adapters must use configured timeouts and fail fast rather than hang indefinitely.

- Thread-safety: either be thread-safe or document async/worker entrypoints.

- Graceful failures: wrap provider errors into AdapterError or return explicit error structure instead of raw
  tracebacks.

Dry-run / ModelStore compatibility

- The repo supports a dry-run mode controlled by environment flags: MODEL_STORE_DRY_RUN=1 or DRY_RUN=1. In this mode
  loaders return lightweight dict placeholders instead of real model/tokenizer handles.

- Because dry-run handles are dictionaries, adapters MUST NOT assume tokenizers or model handles are callables in dry-
  run mode. Either short-circuit (preferred) or detect the handle types before calling.

Per-agent adapter patterns

- The canonical OpenAI/vLLM wrapper lives at `agents/common/openai_adapter.py` and provides convenience helpers. Those helpers are optional for new adapters but recommended for JSON-centric agents.

- Per-agent wrappers live at `agents/<agent>/model_adapter.py` and should only contain prompts and normalization code
  — avoid running file downloads or heavy tensor ops at import-time.

Testing guidance

- Unit tests: test the BaseAdapter contract (raising NotImplementedError by default), and create a MockAdapter that
  implements the contract deterministically.

- Integration / dry-run tests: ensure adapters behave safely in dry-run mode and produce consistent, schema-compatible
  outputs. Use the `PYTHONPATH=. scripts/dev/run_pytest_conda.sh <tests>`helper to run tests inside the canonical conda
  environment (`${CANONICAL_ENV:-justnews-py312-phase1}`) so CI/local runs are identical.

- CI: include adapter unit tests and dry-run adapter smoke tests in PR jobs. For real-provider tests (OpenAI/HF), gate
  them behind environment variables/secrets and run them in a separate gated CI job.

Example minimal mock adapter (pseudocode)

```py
class MockAdapter(BaseAdapter):
    def load(self, model_id, config=None):
        self.loaded = True

    def infer(self, prompt, **kwargs):
        return { 'text': f"[MOCK] {prompt}", 'raw': {}, 'tokens': len(prompt.split()), 'latency': 0.0 }

    def batch_infer(self, prompts, **kwargs):
        return [self.infer(p, **kwargs) for p in prompts]

    def health_check(self):
        return {'loaded': self.loaded, 'name': 'mock'}

    def unload(self):
        self.loaded = False

    def metadata(self):
        return {'adapter': 'mock'}

```

CI checklist for adapter PRs

1. Add/update unit tests covering the BaseAdapter and MockAdapter.

1. Add dry-run tests for the adapter's JSON shapes and edge-cases (empty input, truncated content, missing fields).

1. If introducing a real provider adapter, add a gated CI matrix entry that runs one or two example queries with
   secrets.

Where to start

- Quick win (recommended): create/update `agents/common/adapter_base.py`,`agents/common/mock_adapter.py`and add
  tests`tests/adapters/test_base.py`,`tests/adapters/test_mock_adapter.py`(already present in this repo). Continue by
  adding`docs/adapter_spec.md` and include this file in PRs when adding new adapters.

Repository templates

- `agents/common/openai_adapter.py` — OpenAI adapter template (dry-run short-circuiting, configurable system
  prompt/temperature/max tokens, retry/backoff, metrics hooks, optional custom headers).

- `agents/common/hf_adapter.py` — HF adapter template (ModelStore-aware loading, optional int8/int4 quantization via
  bitsandbytes, device-map selection, retry/backoff, dry-run short-circuiting, and configurable generation defaults).

- `agents/common/adapter_base.py`— provides`AdapterResult`,`AdapterMetadata`,`AdapterHealth`,`AdapterError`, dry-run
  detection helpers,`mark_loaded/mark_unloaded`,`ensure_loaded`, and a default`batch_infer` implementation so adapters
  can focus on provider logic.

- `agents/common/mock_adapter.py` — canonical deterministic mock adapter with configurable responses, forced-failure
  hooks, latency injection, and health metadata for CI tests.

---

## Developer recipe: adding a new adapter

1. **Copy the base template** — Start from `agents/common/openai_adapter.py`(hosted provider)
   or`agents/common/hf_adapter.py`(local/HF). Keep imports lazy and respect`BaseAdapter.dry_run`.

1. **Implement the contract** — Provide `load`,`infer`, and (optionally) override`batch_infer`if batching needs
   optimized paths. Use`mark_loaded`,`ensure_loaded`, and`build_result` helpers.

1. **Handle dry-run + ModelStore** — Short-circuit or return deterministic placeholders when `self.dry_run` is true or
   when handles from ModelStore are dicts.

1. **Emit metrics** — Use `common.metrics.get_metrics` to produce latency/success/error data as described in the
   playbook. Guard metric calls so tests work without Prometheus.

1. **Expose metadata & health** — Return concise dictionaries describing adapter name, version, device, and include
   useful `health_check` details (loaded status, errors, provider hints).

1. **Write tests** — Add/update files under `tests/adapters/` to cover:

- Base behavior (`test_adapter_base.py`,`test_mock_adapter.py` already exist).

- New adapter dry-run paths, failure modes, JSON schema stability.

- Provider-specific retry/backoff logic gated behind feature flags or env vars.

1. **Document + register** — Update `docs/model-adapter-playbook.md` (status + next steps) and this spec if the new
   adapter introduces fresh patterns or requirements.

1. **Run canonical tests** — Use `./scripts/dev/run_pytest_conda.sh tests/adapters/*`so the
   canonical`${CANONICAL_ENV:-justnews-py312-phase1}` env validates your changes before opening a PR.

Following this recipe keeps adapters testable, dry-run friendly, and aligned with the shared BaseAdapter utilities.

Document version: 0.1 — generated/updated December 2, 2025
