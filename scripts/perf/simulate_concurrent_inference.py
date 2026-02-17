#!/usr/bin/env python3
"""Simulate concurrent agent inference requests against a single base model + adapters.

This script has two modes:
 - test mode (RE_RANKER_TEST_MODE=1) which uses a fast deterministic stub model to
   exercise the concurrency, GPU usage measurement and latency pipeline without
   loading heavy models.
 - real mode: if the environment has transformers + bitsandbytes, will attempt to
   load `RE_RANKER_MODEL` or a given model id and run real inference.

Usage examples
  # Dry-run with stub (fast, no heavy downloads)
  RE_RANKER_TEST_MODE=1 python scripts/perf/simulate_concurrent_inference.py --workers 8 --requests 100

  # Try real model load (must have CUDA + bnb and model available)
  RE_RANKER_TEST_MODE=0 RE_RANKER_MODEL=mistralai/Mistral-7B-Instruct python scripts/perf/simulate_concurrent_inference.py --workers 3 --requests 30

The script reports per-request latency (p50, p95, max) and GPU memory snapshots.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import statistics
import time

try:
    import pynvml

    NVML_AVAILABLE = True
except Exception:
    NVML_AVAILABLE = False

RETRY_SLEEP = 0.01


def gpu_mem_snapshot() -> tuple[int, int]:
    if not NVML_AVAILABLE:
        return (0, 0)
    try:
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        m = pynvml.nvmlDeviceGetMemoryInfo(h)
        return (int(m.total // 1024**2), int(m.used // 1024**2))
    except Exception:
        return (0, 0)


class StubModel:
    def score(self, query: str, text: str) -> float:
        # cheap deterministic work to simulate compute
        s = sum(ord(c) for c in query) % (len(text) + 1)
        # simulate some GPU-like delay (tiny)
        time.sleep(0.002)
        return float(s) / (len(text) + 1)


def load_model_if_available(model_id: str | None):
    if os.environ.get("RE_RANKER_TEST_MODE", "1") in ("1", "true"):
        return StubModel()

    try:
        # Try real loading
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        model_id = model_id or os.environ.get("RE_RANKER_MODEL")
        if not model_id:
            raise RuntimeError("No model id configured (RE_RANKER_MODEL)")

        # Prepare load kwargs and create quantization config if bitsandbytes native binary is present.
        load_kwargs = {}
        bnb = None
        try:
            disable_bnb = os.environ.get("BNB_DISABLE", "0").lower() in {
                "1",
                "true",
                "yes",
            }
            if disable_bnb:
                raise RuntimeError("BNB_DISABLE=1 set")

            # Lightweight check for bitsandbytes native binary WITHOUT importing the module
            import importlib.util as _il

            spec = _il.find_spec("bitsandbytes")
            bnb_dir = None
            if spec and spec.submodule_search_locations:
                # spec gives us the location of the package files
                bnb_dir = list(spec.submodule_search_locations)[0]
            has_native = (
                any(name.startswith("libbitsandbytes") for name in os.listdir(bnb_dir))
                if bnb_dir and os.path.isdir(bnb_dir)
                else False
            )
            if has_native:
                bnb = BitsAndBytesConfig(
                    load_in_8bit=True,
                    bnb_8bit_use_double_quant=True,
                    bnb_8bit_compute_dtype=getattr(torch, "float16", None),
                )
                load_kwargs["quantization_config"] = bnb
            else:
                print(
                    "bitsandbytes native binary not found — skipping 8-bit quantization and using float16/device_map instead"
                )
        except Exception:
            # if bitsandbytes is completely missing or cannot provide a native binary, skip quantization
            print(
                "bitsandbytes disabled or check failed; skipping 8-bit quantization and using float16/device_map when possible"
            )

        # Prefer forcing the model onto GPU to get realistic inference latency when a GPU is available.
        # We'll try a strict placement first (all parameters to cuda:0) and on failure fall back to auto device_map.
        # load_kwargs already prepared above depending on bitsandbytes availability
        _tried_forced = False
        if torch.cuda.is_available():
            try:
                _tried_forced = True
                print(
                    "Attempting to load model directly onto gpu:0 (may OOM if not enough memory)"
                )
                # If we couldn't create a BitsAndBytesConfig (bnb is None) then prefer float16 dtype
                if bnb is None:
                    model = AutoModelForCausalLM.from_pretrained(
                        model_id,
                        device_map={"": "cuda:0"},
                        dtype=getattr(torch, "float16", None),
                        **load_kwargs,
                    )
                else:
                    model = AutoModelForCausalLM.from_pretrained(
                        model_id,
                        device_map={"": "cuda:0"},
                        dtype=getattr(torch, "float16", None),
                        **load_kwargs,
                    )
            except Exception as e_forced:
                print(
                    "Direct cuda:0 placement failed, falling back to device_map=auto; error:",
                    e_forced,
                )
                # If bnb None, don't pass quantization_config (load as float16 if possible) to avoid bitsandbytes errors.
                if bnb is None:
                    model = AutoModelForCausalLM.from_pretrained(
                        model_id,
                        device_map="auto",
                        dtype=getattr(torch, "float16", None),
                    )
                else:
                    model = AutoModelForCausalLM.from_pretrained(
                        model_id, device_map="auto", **load_kwargs
                    )
        else:
            model = AutoModelForCausalLM.from_pretrained(
                model_id, device_map="auto", **load_kwargs
            )
        tokenizer = AutoTokenizer.from_pretrained(model_id)

        # Log device placement info to help diagnose where parameters land
        try:
            if hasattr(model, "hf_device_map"):
                print("Model hf_device_map:", model.hf_device_map)
        except Exception:
            pass

        # count params on cuda
        try:
            params_on_cuda = sum(1 for p in model.parameters() if p.is_cuda)
            total_params = sum(1 for _ in model.parameters())
            print(f"Parameters on CUDA: {params_on_cuda}/{total_params}")
        except Exception:
            pass

        # If there are no params on CUDA but we have a GPU, attempt to move model there
        if torch.cuda.is_available():
            try:
                if params_on_cuda == 0:
                    print('Trying model.to("cuda") to force GPU placement...')
                    model.to("cuda")
                    params_on_cuda = sum(1 for p in model.parameters() if p.is_cuda)
                    print(
                        f'Parameters on CUDA after model.to("cuda"): {params_on_cuda}/{total_params}'
                    )
            except Exception as e_move:
                print(
                    'model.to("cuda") failed (likely OOM), keeping current placement:',
                    e_move,
                )

        class RealScorer:
            def __init__(self, m, tkn):
                self.m = m
                self.t = tkn

            def score(self, q, c):
                inp = f"Query: {q}\nCandidate: {c}\nScore:"
                tokens = self.t(inp, return_tensors="pt")
                if torch.cuda.is_available():
                    # ensure tokens land on the same device as model if possible
                    try:
                        # prefer model device for placement
                        dev = next(self.m.parameters()).device
                        tokens = {k: v.to(dev) for k, v in tokens.items()}
                    except Exception:
                        tokens = {k: v.to("cuda") for k, v in tokens.items()}
                with torch.no_grad():
                    out = self.m(**tokens)
                # heuristic: return max softmax on last token
                logits = out.logits[:, -1, :]
                # Robust handling of logits in either torch tensor or numpy/other
                try:
                    # Preferred: torch tensor path
                    probs = logits.softmax(dim=-1).max().values.item()
                    return float(probs)
                except Exception:
                    # Fallback: coerce to numpy and compute softmax then max
                    try:
                        import numpy as _np

                        if hasattr(logits, "detach"):
                            arr = logits.detach().cpu().numpy()
                        else:
                            arr = _np.array(logits)
                        # safe softmax implementation
                        exps = _np.exp(arr - _np.max(arr, axis=-1, keepdims=True))
                        soft = exps / _np.sum(exps, axis=-1, keepdims=True)
                        val = float(_np.max(soft))
                        return val
                    except Exception:
                        # Last-ditch: if everything fails, return 0.0
                        return 0.0

        return RealScorer(model, tokenizer)
    except Exception as e:
        print("Warning: failed to load real model - falling back to stub:", e)
        return StubModel()


def worker_task(worker_id: int, scorer, num_requests: int) -> list[float]:
    latencies = []
    for i in range(num_requests):
        q = f"Test query from worker {worker_id} iter {i}"
        cand = "The company reported record revenue this quarter with strong growth"
        t0 = time.monotonic()
        _ = scorer.score(q, cand)
        lat = (time.monotonic() - t0) * 1000.0
        latencies.append(lat)
    return latencies


def run_workers(workers: int, total_requests: int, model_id: str | None = None):
    requests_per_worker = max(1, total_requests // workers)
    print(
        f"Running {workers} workers, total requests {total_requests} (~{requests_per_worker} each)"
    )
    scorer = load_model_if_available(model_id)

    # warmup snapshot
    total_mb, used_mb = gpu_mem_snapshot()
    print(f"GPU snapshot before workers: total={total_mb}MB used={used_mb}MB")

    start = time.monotonic()
    all_latencies: list[float] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [
            ex.submit(worker_task, i, scorer, requests_per_worker)
            for i in range(workers)
        ]
        for fut in concurrent.futures.as_completed(futures):
            all_latencies.extend(fut.result())

    duration = time.monotonic() - start

    total_mb2, used_mb2 = gpu_mem_snapshot()
    print(f"GPU snapshot after: total={total_mb2}MB used={used_mb2}MB")

    print(f"Total completed requests: {len(all_latencies)} in {duration:.2f}s")
    if all_latencies:
        print(
            f"p50={statistics.median(all_latencies):.1f}ms p95={statistics.quantiles(all_latencies, n=100)[94]:.1f}ms max={max(all_latencies):.1f}ms avg={statistics.mean(all_latencies):.1f}ms"
        )
    return {
        "total_requests": len(all_latencies),
        "duration_s": duration,
        "gpu_used_before_mb": used_mb,
        "gpu_used_after_mb": used_mb2,
        "latencies_ms": all_latencies,
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--requests", type=int, default=100)
    p.add_argument("--model", type=str, default=None)
    p.add_argument(
        "--repeat", type=int, default=1, help="Repeat each experiment N times"
    )
    p.add_argument(
        "--sweep",
        action="store_true",
        help="Run a sweep of worker counts from 1..N instead of a single workers value",
    )
    p.add_argument(
        "--sweep-max",
        type=int,
        default=6,
        help="When --sweep is used, maximum workers to try",
    )
    p.add_argument(
        "--output-csv",
        type=str,
        default=None,
        help="Write per-experiment summary rows to CSV file",
    )
    p.add_argument(
        "--output-json", type=str, default=None, help="Write full results to JSON file"
    )
    args = p.parse_args(argv)

    # run experiments: either a single run (workers) or a sweep
    all_results = []

    def record_result(w, r, run_idx, res):
        summary = {
            "workers": w,
            "total_requests": res["total_requests"],
            "duration_s": res["duration_s"],
            "p50_ms": statistics.median(res["latencies_ms"])
            if res["latencies_ms"]
            else None,
            "p95_ms": (
                statistics.quantiles(res["latencies_ms"], n=100)[94]
                if res["latencies_ms"]
                else None
            ),
            "max_ms": (max(res["latencies_ms"]) if res["latencies_ms"] else None),
            "avg_ms": (
                statistics.mean(res["latencies_ms"]) if res["latencies_ms"] else None
            ),
            "gpu_used_before_mb": res["gpu_used_before_mb"],
            "gpu_used_after_mb": res["gpu_used_after_mb"],
            "run_idx": run_idx,
            "requests_per_worker": max(1, r // w),
        }
        all_results.append(summary)

    if args.sweep:
        max_workers = args.sweep_max
        for w in range(1, max_workers + 1):
            for rep in range(args.repeat):
                print(f"\n=== sweep: workers={w} repeat={rep + 1}/{args.repeat} ===")
                res = run_workers(w, args.requests, args.model)
                record_result(w, args.requests, rep + 1, res)
    else:
        for rep in range(args.repeat):
            print(
                f"\n=== run: workers={args.workers} repeat={rep + 1}/{args.repeat} ==="
            )
            res = run_workers(args.workers, args.requests, args.model)
            record_result(args.workers, args.requests, rep + 1, res)

    # print a compact summary
    print("\nOverall summary:")
    for rr in all_results:
        print(
            f"  workers={rr['workers']} run={rr['run_idx']} p50={rr['p50_ms']:.1f}ms p95={rr['p95_ms']:.1f}ms avg={rr['avg_ms']:.1f}ms gpu_before={rr['gpu_used_before_mb']} gpu_after={rr['gpu_used_after_mb']}"
        )

    # optional CSV / JSON outputs
    import json

    if args.output_json:
        with open(args.output_json, "w") as jf:
            json.dump(all_results, jf, indent=2)
        print(f"Wrote JSON results to {args.output_json}")

    if args.output_csv:
        import csv

        headers = [
            "workers",
            "run_idx",
            "requests_per_worker",
            "total_requests",
            "duration_s",
            "p50_ms",
            "p95_ms",
            "avg_ms",
            "max_ms",
            "gpu_used_before_mb",
            "gpu_used_after_mb",
        ]
        with open(args.output_csv, "w", newline="") as cf:
            wtr = csv.DictWriter(cf, fieldnames=headers)
            wtr.writeheader()
            for rr in all_results:
                row = {k: rr.get(k) for k in headers}
                wtr.writerow(row)
        print(f"Wrote CSV results to {args.output_csv}")


if __name__ == "__main__":
    main()
