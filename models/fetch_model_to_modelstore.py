#!/usr/bin/env python3
"""Fetch a Hugging Face model and stage it into the local ModelStore.

Usage:
  python models/fetch_model_to_modelstore.py --model mistralai/Mistral-7B-Instruct-v0.3
"""
from pathlib import Path
import argparse
import shutil
import tempfile
import os

try:
    from huggingface_hub import snapshot_download
except Exception as e:
    raise RuntimeError("huggingface_hub is required to fetch models; pip install huggingface-hub") from e

ROOT = Path(__file__).resolve().parents[1]
MODEL_STORE_ROOT = Path(os.environ.get("MODEL_STORE_ROOT", str(ROOT / "model_store")))


def target_model_dir(model_id: str) -> Path:
    # convert HF id to ModelStore directory naming used elsewhere
    model_dir_name = model_id.replace("/", "--").replace("_", "_")
    model_dir = MODEL_STORE_ROOT / "base_models" / f"models--{model_dir_name}"
    return model_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--no-snapshots", action="store_true")
    args = parser.parse_args()

    model_id = args.model
    tgt = target_model_dir(model_id)
    print(f"Staging model {model_id} into ModelStore at {tgt}")
    tmp = Path(tempfile.mkdtemp(prefix="justnews-model-"))
    try:
        print("Downloading snapshot (this may take a while)...")
        snapshot_dir = snapshot_download(repo_id=model_id, revision=args.revision, cache_dir=str(tmp), local_files_only=False)
        # create structure: <tgt>/snapshots/<snapshot_hash>/
        snapshots_dir = tgt / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        # use timestamped dir
        stamp = tmp.name
        final_snapshot = snapshots_dir / stamp
        print(f"Copying files to {final_snapshot}")
        shutil.copytree(snapshot_dir, final_snapshot)
        # also ensure that tgt exists
        (tgt / "METADATA").write_text(f"source: {model_id}\ninstalled: true\n")
        print(f"Model staged at {final_snapshot}")
    except Exception as e:
        print("Failed to fetch model:", e)
        raise
    finally:
        try:
            shutil.rmtree(tmp)
        except Exception:
            pass


if __name__ == "__main__":
    main()
