# QLoRA Adapter Training Guide

This guide explains how to run `scripts/train_qlora.py` to produce per-agent LoRA/QLoRA adapters for the Mistral
rollout.

## Dependencies

- Python 3.10+

- CUDA-enabled GPU (RTX 3090 baseline)

- Packages: `transformers`,`datasets`,`accelerate`,`bitsandbytes`,`peft`,`torch`,`sentencepiece`

- Optional: `MODEL_STORE_ROOT` for publishing adapters directly after training

Install (conda env example):

```bash
mamba run -n ${CANONICAL_ENV:-justnews-py312} pip install -r training_system/requirements-qlora.txt || conda run -n ${CANONICAL_ENV:-justnews-py312} pip install -r training_system/requirements-qlora.txt

```bash

(Or install the packages listed above manually.)

## Data expectations

- Provide either `--train-files path/to/*.jsonl`or`--dataset-name org/dataset_id`

- JSON/JSONL rows should include:

- `text`: full prompt+response string **or**

- `prompt`and`response`fields that the script will combine via`--prompt-template`

- Use `--max-train-samples` for smoke tests before longer runs.

## Common command patterns

Dry-run sanity check (no training, creates stub output directory):

```bash
conda run -n ${CANONICAL_ENV:-justnews-py312} \
  python scripts/train_qlora.py \
    --agent synthesizer \
    --adapter-name mistral_synth_v1 \
    --model_name_or_path mistralai/Mistral-7B-Instruct-v0.3 \
    --train-files data/synth_samples.jsonl \
    --output_dir output/adapters/mistral_synth_v1 \
    --dry-run

```

Full training run with ModelStore publish:

```bash
MODEL_STORE_ROOT=/opt/justnews/model_store HF_TOKEN=$HF_TOKEN \
conda run -n ${CANONICAL_ENV:-justnews-py312} \
  python scripts/train_qlora.py \
    --agent synthesizer \
    --adapter-name mistral_synth_v1 \
    --model_name_or_path mistralai/Mistral-7B-Instruct-v0.3 \
    --train-files data/synth_finetune.jsonl \
    --output_dir output/adapters/mistral_synth_v1 \
    --epochs 3 \
    --train-batch-size 1 \
    --gradient-accumulation 8 \
    --adapter-r 64 \
    --adapter-alpha 16 \
    --publish

```

## Publishing workflow

- When `--publish`is set, the script copies`--output_dir` into the ModelStore version for the selected agent.

- Version labels default to `vYYYYMMDD-HHMM`unless`--adapter-version` is provided.

- Metadata describing hyperparameters, dataset source, and timestamps is written to `training_summary.json` and embedded
  in the ModelStore manifest.

## Tips

- Always run with `--dry-run` first on any new host to verify packages/CUDA.

- Keep `output/adapters/<adapter_name>`under`.gitignore`; only publish artifacts to ModelStore.

- For CI validation, run `--dry-run --max-train-samples 10` to keep runtimes low.

- Update `AGENT_MODEL_MAP.json` once an adapter version is published so orchestrator + loader can resolve it.
