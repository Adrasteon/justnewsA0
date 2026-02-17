#!/bin/bash
export WORKFLOW_ORCHESTRATOR_PORT=8020
export PYTHONPATH=$PYTHONPATH:.
# Source conda.sh to get the activate command
source $HOME/miniconda3/etc/profile.d/conda.sh
conda activate ${CANONICAL_ENV:-justnews-py312-phase1}

exec python -m uvicorn agents.workflow_orchestrator.main:app --host 0.0.0.0 --port 8020
