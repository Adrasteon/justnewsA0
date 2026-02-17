#!/usr/bin/env python3
"""
Host-native TensorRT engine build wrapper (scaffold)

This wrapper tries to run the real `NativeTensorRTCompiler` when the host
has the required toolchain. When the toolchain is not available it falls
back to creating marker engine files (safe for CI and developers without GPUs).

Usage:
  python tools/build_engine/build_engine.py --check-only
  python tools/build_engine/build_engine.py --build --model <hf_model> --precision fp8
  python tools/build_engine/build_engine.py --build-markers

Note: This is a scaffold. The full implementation will orchestrate:
  - fetch model from ModelStore or HF
  - export ONNX with dynamic axes
  - run TensorRT build with optimization profiles
  - run INT8 calibration if requested
  - upload artifacts to ModelStore atomically
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINES_DIR = ROOT / "agents" / "analyst" / "tensorrt_engines"
ENGINES_DIR.mkdir(parents=True, exist_ok=True)


def create_marker(engine_name: str, task: str, precision: str = "fp16"):
    engine_path = ENGINES_DIR / engine_name
    metadata_path = engine_path.with_suffix(".json")

    with open(engine_path, "w", encoding="utf-8") as f:
        f.write(f"Marker TensorRT engine for {task}\n")
        f.write(f"Created: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Precision: {precision}\n")

    metadata = {
        "task": task,
        "precision": precision,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    # Optional calibration metadata placeholder
    # If precision is int8 we record that calibration was requested; real calibration
    # artifacts would be generated on GPU hosts.
    if precision == "int8":
        metadata["calibrated"] = False
        metadata["calib_data"] = None
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"Created marker engine: {engine_path}")


def try_native_compile(args):
    try:
        # Try to use the repo-native compiler
        sys.path.insert(0, str(ROOT / "agents" / "analyst"))
        from agents.analyst.native_tensorrt_compiler import NativeTensorRTCompiler

        compiler = NativeTensorRTCompiler()
        # Apply requested precision and calibration data to the compiler config
        compiler.optimization_config["precision"] = args.precision
        if args.calibrate:
            compiler.optimization_config["calibration_data"] = args.calib_data

        if args.model:
            print(
                f"Starting native compilation for model: {args.model} precision={args.precision}"
            )
            if args.model == "sentiment":
                ok = compiler.compile_sentiment_model()
            elif args.model == "bias":
                ok = compiler.compile_bias_model()
            else:
                print(
                    "Model-specific compile not implemented in scaffold. Use compile_all_models()"
                )
                ok = compiler.compile_all_models()
        else:
            print("Running full compile_all_models() via NativeTensorRTCompiler")
            ok = compiler.compile_all_models()

        print("Native compilation finished:", ok)
        return ok

    except Exception as e:
        print("Native compiler not available or failed:", e)
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--build-markers", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument(
        "--model", type=str, help="Model name or task (e.g., sentiment)"
    )
    parser.add_argument(
        "--precision", default="fp16", choices=["fp32", "fp16", "fp8", "int8"]
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Run INT8 calibration during build (requires --precision int8)",
    )
    parser.add_argument(
        "--calib-data",
        type=str,
        help="Path to calibration dataset (JSONL or directory)",
    )
    args = parser.parse_args()

    if args.check_only:
        try:
            import tensorrt  # noqa: F401
            import torch  # noqa: F401

            print("TensorRT and CUDA appear to be available on this machine.")
        except Exception as e:
            print("TensorRT/CUDA not available:", e)
        return

    if args.build_markers:
        create_marker(
            "native_sentiment_roberta.engine", "sentiment", precision=args.precision
        )
        create_marker("native_bias_bert.engine", "bias", precision=args.precision)
        print("Marker engine creation complete.")
        return

    if args.build:
        # If INT8 calibration requested but precision != int8, warn and continue
        if args.calibrate and args.precision != "int8":
            print(
                "Warning: --calibrate requested but --precision is not int8; proceeding with precision=",
                args.precision,
            )

        ok = try_native_compile(args)
        if not ok:
            print(
                "Native compilation failed or not available; creating marker engines instead"
            )
            create_marker(
                "native_sentiment_roberta.engine", "sentiment", precision=args.precision
            )
            create_marker("native_bias_bert.engine", "bias", precision=args.precision)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
