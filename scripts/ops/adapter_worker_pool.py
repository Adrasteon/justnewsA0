#!/usr/bin/env python3
"""Spawn a warm pool of adapter workers that load the shared base model + adapter.

This is an operational helper used for load testing and for establishing a warm
pool on a single GPU node. The script will spawn N worker processes which load
the base model (int8) then optionally a specified adapter and keep the process
alive ready to accept requests.

When invoked with --remote (or when GPU_ORCHESTRATOR_URL is set) the script
delegates worker management to the GPU orchestrator via its /workers/pool API.

Note: in production, GPU Orchestrator should manage worker pools; this script
provides a developer-runable tool to prototype pool sizing and memory usage.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import multiprocessing as mp
import os
import time
from typing import Any


def _lazy_requests():  # pragma: no cover - simple helper to avoid hard dependency in local mode
    try:
        import requests  # type: ignore

        return requests
    except Exception as exc:  # pragma: no cover
        raise RuntimeError('Remote mode requires the "requests" package') from exc


def _orchestrator_headers(admin_key: str | None) -> dict[str, str]:
    headers: dict[str, str] = {
        "Content-Type": "application/json",
    }
    if admin_key:
        headers["X-Admin-API-Key"] = admin_key
    return headers


def _orchestrator_base(url: str | None) -> str:
    if not url:
        raise RuntimeError(
            "GPU orchestrator URL is required for remote mode (set --orchestrator-url or GPU_ORCHESTRATOR_URL)"
        )
    return url.rstrip("/")


def _remote_start_pool(
    base_url: str, admin_key: str | None, payload: dict[str, Any]
) -> dict[str, Any]:
    requests = _lazy_requests()
    resp = requests.post(
        f"{base_url}/workers/pool",
        headers=_orchestrator_headers(admin_key),
        json=payload,
        timeout=20,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Orchestrator start failed ({resp.status_code}): {resp.text}"
        )
    return resp.json()


def _remote_list_pools(base_url: str, admin_key: str | None) -> list[dict[str, Any]]:
    requests = _lazy_requests()
    resp = requests.get(
        f"{base_url}/workers/pool", headers=_orchestrator_headers(admin_key), timeout=10
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Orchestrator list failed ({resp.status_code}): {resp.text}"
        )
    return resp.json()


def _remote_stop_pool(
    base_url: str, admin_key: str | None, pool_id: str
) -> dict[str, Any]:
    requests = _lazy_requests()
    resp = requests.delete(
        f"{base_url}/workers/pool/{pool_id}",
        headers=_orchestrator_headers(admin_key),
        timeout=10,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Orchestrator stop failed ({resp.status_code}): {resp.text}"
        )
    return resp.json()


def worker_main(model_id: str | None, adapter: str | None, run_seconds: int = 3600):
    # workable minimal loader: use RE_RANKER_TEST_MODE for stub
    if os.environ.get("RE_RANKER_TEST_MODE", "1") in ("1", "true"):
        print(
            f"[worker {os.getpid()}] running stub (test mode) — sleeping {run_seconds}s"
        )
        time.sleep(run_seconds)
        return

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        try:
            from transformers import BitsAndBytesConfig  # type: ignore
        except Exception:  # pragma: no cover - optional dependency
            BitsAndBytesConfig = None  # type: ignore

        load_kwargs: dict = {}
        bnb_cfg = None
        if BitsAndBytesConfig is not None:
            try:
                spec = importlib.util.find_spec("bitsandbytes")
                bnb_dir = None
                if spec and spec.submodule_search_locations:
                    bnb_dir = list(spec.submodule_search_locations)[0]
                has_native = bool(
                    bnb_dir
                    and os.path.isdir(bnb_dir)
                    and any(
                        name.startswith("libbitsandbytes")
                        for name in os.listdir(bnb_dir)
                    )
                )
                if has_native:
                    bnb_cfg = BitsAndBytesConfig(
                        load_in_8bit=True,
                        bnb_8bit_use_double_quant=True,
                        bnb_8bit_compute_dtype=getattr(torch, "float16", None),
                    )
                    load_kwargs["quantization_config"] = bnb_cfg
                else:
                    print(
                        "[worker] bitsandbytes native binary missing — using float16 fp16 device_map"
                    )
            except Exception as e:
                print(
                    f"[worker] bitsandbytes detection failed ({e}); using float16 fp16 device_map"
                )
        else:
            print(
                "[worker] transformers BitsAndBytesConfig unavailable — using float16 fp16 device_map"
            )

        dtype = getattr(torch, "float16", None)
        if bnb_cfg is None:
            model = AutoModelForCausalLM.from_pretrained(
                model_id, device_map="auto", dtype=dtype
            )
        else:
            model = AutoModelForCausalLM.from_pretrained(
                model_id, device_map="auto", **load_kwargs
            )

        # tokenizer not used directly here; call to warm model cache
        _ = AutoTokenizer.from_pretrained(model_id)

        if adapter:
            try:
                from peft import PeftModel

                model = PeftModel.from_pretrained(model, adapter)
                print(f"[worker {os.getpid()}] loaded adapter {adapter}")
            except Exception as e:
                print(f"[worker {os.getpid()}] failed to load adapter {adapter}: {e}")

        print(f"[worker {os.getpid()}] model loaded, holding for {run_seconds}s")
        time.sleep(run_seconds)

    except Exception as e:
        print(f"[worker {os.getpid()}] failed to load model: {e}")


def spawn_pool(
    num_workers: int, model_id: str | None, adapter: str | None, hold_time: int
):
    # Use spawn context to avoid fork safety issues in threaded environments (like pytest)
    # This prevents "DeprecationWarning: This process is multi-threaded, use of fork() may lead to deadlocks"
    ctx = mp.get_context("spawn")
    procs = []
    for _ in range(num_workers):
        p = ctx.Process(target=worker_main, args=(model_id, adapter, hold_time))
        p.start()
        procs.append(p)
        time.sleep(0.5)  # stagger loads slightly

    print(f"Spawned {len(procs)} workers. Press Ctrl-C to stop early.")
    try:
        # wait for processes
        for p in procs:
            p.join()
    except KeyboardInterrupt:
        print("Stopping workers...")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--model", type=str, default=None)
    p.add_argument("--adapter", type=str, default=None)
    p.add_argument("--hold", type=int, default=600)
    p.add_argument(
        "--agent",
        type=str,
        default=None,
        help="Optional logical agent name used for orchestrator audit",
    )
    p.add_argument(
        "--pool-id",
        type=str,
        default=None,
        help="Explicit pool identifier when using remote mode",
    )
    p.add_argument(
        "--variant",
        type=str,
        default=None,
        help="Hint for orchestrator loading strategy (fp16, bnb-4bit-qlora, etc)",
    )
    p.add_argument(
        "--orchestrator-url",
        type=str,
        default=os.environ.get("GPU_ORCHESTRATOR_URL"),
        help="GPU orchestrator base URL (enables remote mode when set)",
    )
    p.add_argument(
        "--admin-key",
        type=str,
        default=os.environ.get("GPU_ORCHESTRATOR_ADMIN_KEY")
        or os.environ.get("ADMIN_API_KEY"),
        help="Admin API key for orchestrator authentication",
    )
    p.add_argument(
        "--remote",
        action="store_true",
        help="Delegate pool management to the GPU orchestrator instead of spawning local processes",
    )
    p.add_argument(
        "--list-remote",
        action="store_true",
        help="List remote worker pools and exit (requires orchestrator URL + admin key)",
    )
    p.add_argument(
        "--stop-remote",
        type=str,
        default=None,
        help="Stop a remote pool by id and exit",
    )
    args = p.parse_args(argv)

    if args.list_remote:
        base = _orchestrator_base(args.orchestrator_url)
        pools = _remote_list_pools(base, args.admin_key)
        print(json.dumps(pools, indent=2))
        return

    if args.stop_remote:
        base = _orchestrator_base(args.orchestrator_url)
        resp = _remote_stop_pool(base, args.admin_key, args.stop_remote)
        print(json.dumps(resp, indent=2))
        return

    if args.remote or args.orchestrator_url:
        base = _orchestrator_base(args.orchestrator_url)
        payload = {
            "pool_id": args.pool_id,
            "agent": args.agent,
            "model": args.model,
            "adapter": args.adapter,
            "num_workers": args.workers,
            "hold_seconds": args.hold,
            "variant": args.variant,
        }
        resp = _remote_start_pool(base, args.admin_key, payload)
        print(json.dumps(resp, indent=2))
        return

    spawn_pool(args.workers, args.model, args.adapter, args.hold)


if __name__ == "__main__":
    main()
