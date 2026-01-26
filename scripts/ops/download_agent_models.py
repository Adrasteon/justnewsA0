#!/usr/bin/env python3
"""
Download selected HF models into agent-specific model folders under agents/*/models.

Usage:
    ./scripts/download_agent_models.py [--dry-run] [--only SMALL|ALL] [--yes]

By default this downloads a conservative set of small/medium models. Use --only ALL to download everything (may be large).
"""

import argparse
import sys
from pathlib import Path

from common.observability import get_logger

logger = get_logger(__name__)

# Mapping of agents -> list of model ids to download
AGENT_MODEL_MAP = {
    # scout is deprecated
    # newsreader is deprecated
    "fact_checker": [
        ("transformers", "distilbert-base-uncased", False),
        ("transformers", "roberta-base", False),
        ("sentence-transformers", "sentence-transformers/all-mpnet-base-v2", True),
    ],
    "memory": [
        ("sentence-transformers", "all-MiniLM-L6-v2", True),
    ],
    "synthesizer": [
        ("transformers", "distilgpt2", False),
        ("transformers", "google/flan-t5-small", False),
    ],
    "critic": [
        ("transformers", "unitary/unbiased-toxic-roberta", False),
        ("transformers", "unitary/toxic-bert", False),
    ],
    "analyst": [
        ("transformers", "google/bert_uncased_L-2_H-128_A-2", False),
    ],
    # "newsreader": [
    #     ("sentence-transformers", "all-MiniLM-L6-v2", True),
    # ],
    # balancer removed - models migrated to critic/chief_editor/analytics
    "chief_editor": [
        ("transformers", "distilbert-base-uncased", False),
    ],
}


# Normalizer for folder names
def normalize_name(name: str) -> str:
    return name.replace("/", "_").replace(" ", "_")


def download_sentence_transformer(model_id: str, target_dir: Path):
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        logger.error("sentence_transformers not installed: %s", e)
        raise
    logger.info("Downloading sentence-transformer %s -> %s", model_id, target_dir)
    # The SentenceTransformer class accepts cache_folder
    model = SentenceTransformer(model_id, cache_folder=str(target_dir))
    try:
        model.save(str(target_dir))
    except Exception:
        # some ST versions won't implement .save for remote models; ignore
        pass


def download_transformers_model(model_id: str, target_dir: Path):
    try:
        from transformers import AutoModel, AutoTokenizer
    except Exception as e:
        logger.error("transformers not installed: %s", e)
        raise
    logger.info(
        "Downloading transformers model+tokenizer %s -> %s", model_id, target_dir
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    # Use cache_dir to force files into target_dir
    try:
        AutoModel.from_pretrained(model_id, cache_dir=str(target_dir))
    except Exception as e:
        logger.warning("Model download failed for %s: %s", model_id, e)
    try:
        AutoTokenizer.from_pretrained(model_id, cache_dir=str(target_dir))
    except Exception as e:
        logger.warning("Tokenizer download failed for %s: %s", model_id, e)


def ensure_and_download(agent: str, model_tuple, dry_run: bool, base: Path):
    mtype, model_id, _ = model_tuple
    folder = base / agent / "models" / normalize_name(model_id)
    if folder.exists() and any(folder.iterdir()):
        logger.info("Skipping existing: %s (exists)", folder)
        return folder
    logger.info(
        "Preparing to download %s for agent %s into %s", model_id, agent, folder
    )
    if dry_run:
        return folder
    folder.mkdir(parents=True, exist_ok=True)
    if mtype == "sentence-transformers":
        download_sentence_transformer(model_id, folder)
    else:
        download_transformers_model(model_id, folder)
    return folder


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--only", choices=["SMALL", "ALL"], default="SMALL")
    p.add_argument("--yes", action="store_true")
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    base = repo_root / "agents"

    # If ONLY=SMALL, we will skip models that look large (heuristic)
    large_keywords = ["large", "7b", "13b", "llava", "vicuna"]

    to_download = []
    for agent, models in AGENT_MODEL_MAP.items():
        for m in models:
            if args.only == "SMALL" and any(k in m[1].lower() for k in large_keywords):
                logger.info("Skipping potentially large model %s (only=SMALL)", m[1])
                continue
            to_download.append((agent, m))

    if not args.yes:
        logger.info(
            "About to download %d model(s) into agents/*/models (dry-run=%s, only=%s)",
            len(to_download),
            args.dry_run,
            args.only,
        )
        for agent, m in to_download:
            logger.info("  %s -> %s", agent, m[1])
        resp = input("Proceed? [y/N]: ")
        if resp.lower() not in ("y", "yes"):
            logger.info("Aborting per user request")
            sys.exit(0)

    for agent, m in to_download:
        folder = ensure_and_download(agent, m, args.dry_run, base)
        logger.info("Completed: %s -> %s", m[1], folder)

    logger.info("All done")


if __name__ == "__main__":
    main()
