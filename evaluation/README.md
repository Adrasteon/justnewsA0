# Evaluation Framework

This folder contains a lightweight evaluation framework for common acceptance tests and metrics used by the JustNews
project.

Features

- CLI runner to run evaluation modules (`run_evaluation.py`).

- Basic token-level metrics (precision / recall / F1) in `metrics.py`.

- Small example dataset under `datasets/bbc/` to exercise extraction-parity.

Goals

- Provide a repeatable harness to run staging acceptance checks (extraction parity, HITL lifecycle smoke tests, etc.).

- Keep the framework dependency-light so it can run in CI or locally.

Usage

1. Install the project environment (use `environment.yml`or`requirements.txt`).

1. Run a parity evaluation:

```bash
JUSTNEWS_PYTHON evaluation/run_evaluation.py --mode extraction_parity --dataset evaluation/datasets/bbc

```

The runner will look for paired files in the dataset directory with `.html`and`.txt` (ground truth) suffixes.
