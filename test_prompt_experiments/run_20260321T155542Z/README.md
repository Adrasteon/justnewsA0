# Prompt Experiment

This folder is intentionally self-contained for repeatability.

## Scripts in this folder

- select_clusters.py: chooses 5 test clusters and writes selected_clusters.json
- run_inference_variants.py: runs prompt/temperature variants against selected clusters

## How to rerun

1. cd /app/test_prompt_experiments/run_20260321T155542Z
2. /app/.venv/bin/python select_clusters.py
3. /app/.venv/bin/python run_inference_variants.py

Artifacts are written under clusters/<cluster_id>/.
