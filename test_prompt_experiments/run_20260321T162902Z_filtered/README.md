# Prompt Experiment (Filtered)

Self-contained run with quality filter and fixed controls.

## Scripts
- select_clusters_filtered.py
- run_inference_variants.py

## Rerun
1. cd /app/test_prompt_experiments/run_20260321T162902Z_filtered
2. /app/.venv/bin/python select_clusters_filtered.py
3. VLLM_BASE_URL=http://vllm:8010/v1 /app/.venv/bin/python run_inference_variants.py
