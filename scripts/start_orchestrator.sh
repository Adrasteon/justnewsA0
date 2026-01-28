#!/bin/bash
export WORKFLOW_ORCHESTRATOR_PORT=8020
export PYTHONPATH=$PYTHONPATH:.
# Source conda.sh to get the activate command
source /home/adra/miniconda3/etc/profile.d/conda.sh
conda activate justnews-py312

exec python -m uvicorn agents.workflow_orchestrator.main:app --host 0.0.0.0 --port 8020
