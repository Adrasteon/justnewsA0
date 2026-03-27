#!/usr/bin/env python3
"""Download one or more Hugging Face models into the shared ModelStore.

This script stages a new version for a given agent, downloads the requested
Hugging Face repositories using ``huggingface_hub.snapshot_download``, and then
finalises the version so the ``current`` symlink points at the fresh payload.

Example:
    ./scripts/publish_hf_to_model_store.py \
        --agent synthesizer \
        --model sentence-transformers/all-MiniLM-L6-v2 \
        --version v2025-10-28-embeddings

The script respects ``MODEL_STORE_ROOT`` unless ``--model-store`` overrides it.
Set ``HF_TOKEN`` or pass ``--token`` to authenticate against private repos.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def _import_snapshot_download():
    try:
        from huggingface_hub import snapshot_download  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency missing path
        raise SystemExit(
            "huggingface_hub is required for this script. Install it with 'pip install huggingface-hub'."
        ) from exc
    return snapshot_download


def _import_model_store():
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from models.model_store import ModelStore, ModelStoreError
    except Exception as exc:  # pragma: no cover - import failure
        raise SystemExit(f"Failed to import ModelStore helpers: {exc}") from exc
    return ModelStore, ModelStoreError


def _normalize_model_id(model_id: str) -> str:
    """Mirror the directory naming convention used by huggingface_hub."""
    return f"models--{model_id.replace('/', '--')}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage Hugging Face models in the ModelStore"
    )
    parser.add_argument("--agent", required=True, help="Agent name (e.g. synthesizer)")
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        required=True,
        help="Hugging Face model id. Pass multiple --model flags to download more than one.",
    )
    parser.add_argument(
        "--version",
        help="Version label for the ModelStore (default: vYYYYMMDD-HHMM)",
    )
    parser.add_argument(
        "--model-store",
        dest="model_store",
        help="Override MODEL_STORE_ROOT path.",
    )
    parser.add_argument(
        "--token",
        dest="token",
        help="Optional Hugging Face token. Defaults to HF_TOKEN / HF_HUB_TOKEN env vars.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing staged version if present.",
    )
    parser.add_argument(
        "--metadata",
        help="Optional path to a JSON metadata file to embed into the ModelStore manifest.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    snapshot_download = _import_snapshot_download()
    ModelStore, ModelStoreError = _import_model_store()

    model_store_root = args.model_store or os.environ.get("MODEL_STORE_ROOT")
    if not model_store_root:
        raise SystemExit(
            "MODEL_STORE_ROOT is not set and --model-store was not provided."
        )

    agent = args.agent.strip()
    version = args.version or f"v{datetime.now(UTC):%Y%m%d-%H%M}"
    token = args.token or os.environ.get("HF_TOKEN") or os.environ.get("HF_HUB_TOKEN")

    store = ModelStore(Path(model_store_root))
    versions_root = store.versions_root(agent)
    versions_root.mkdir(parents=True, exist_ok=True)

    staged_path = versions_root / f"{version}.tmp"
    final_path = versions_root / version
    if staged_path.exists() and not args.force:
        raise SystemExit(
            f"Staging path already exists: {staged_path}. Use --force to replace it."
        )
    if final_path.exists() and not args.force:
        raise SystemExit(
            f"Version already exists: {final_path}. Choose another --version or pass --force."
        )

    if args.force:
        # Clean up existing staged path if present. Leave final version intact to avoid surprise.
        if staged_path.exists():
            import shutil

            shutil.rmtree(staged_path)

    try:
        with store.stage_new(agent, version) as tmp_dir:
            for model_id in args.models:
                target_dir = Path(tmp_dir) / _normalize_model_id(model_id)
                target_dir.mkdir(parents=True, exist_ok=True)
                print(f"Downloading {model_id} -> {target_dir}")
                snapshot_download(
                    repo_id=model_id,
                    local_dir=str(target_dir),
                    local_dir_use_symlinks=False,
                    token=token,
                )
    except ModelStoreError as exc:
        raise SystemExit(f"ModelStore staging failed: {exc}") from exc
    except Exception as exc:
        # Any failure during download should clean the staging directory via context manager
        raise SystemExit(f"Failed to download models: {exc}") from exc

    metadata: dict | None = None
    if args.metadata:
        metadata_path = Path(args.metadata)
        if not metadata_path.exists():
            raise SystemExit(f"Metadata file not found: {metadata_path}")
        import json

        with metadata_path.open("r", encoding="utf-8") as fh:
            try:
                metadata = json.load(fh)
            except Exception as exc:  # pragma: no cover - invalid json
                raise SystemExit(f"Failed to parse metadata JSON: {exc}") from exc

    try:
        store.finalize(agent, version, metadata=metadata)
    except Exception as exc:
        raise SystemExit(f"Failed to finalize ModelStore version: {exc}") from exc

    current = store.get_current(agent)
    print(f"Published {agent} -> {current}")


if __name__ == "__main__":
    main()
