#!/bin/bash
# Build all 4 phased conda environments sequentially
# Usage: ./scripts/build_phased_envs.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONDA_DIR="$PROJECT_ROOT/conda"

PHASES=(1 2 3 4)
timestamp=$(date +%s)

echo "=========================================="
echo "Building JustNews Phased Environments"
echo "=========================================="
echo "Project Root: $PROJECT_ROOT"
echo "Conda Dir: $CONDA_DIR"
echo "Build started: $(date)"
echo ""

for phase in "${PHASES[@]}"; do
  env_name="justnews-py312-phase${phase}"
  env_file="$CONDA_DIR/environment.phase${phase}.yml"
  
  if [ ! -f "$env_file" ]; then
    echo "❌ ERROR: $env_file not found!"
    exit 1
  fi
  
  echo "=========================================="
  echo "Phase $phase: Building $env_name"
  echo "=========================================="
  echo "Spec file: $env_file"
  echo "Start time: $(date)"
  
  # Check if environment already exists
  if conda env list | grep -q "^$env_name "; then
    echo "⚠️  Environment $env_name already exists"
    echo "   Removing old environment..."
    conda env remove -n "$env_name" -y
  fi
  
  # Create environment from YAML
   # YAML uses >= constraints to automatically get latest compatible versions
   echo "Creating environment (this may take 15-30 minutes)..."
   conda env create \
     -f "$env_file" \
     -n "$env_name" \
     2>&1 | tee "/tmp/build_phase${phase}_${timestamp}.log"
  
  if [ $? -eq 0 ]; then
    echo "✅ Phase $phase environment created successfully"
  else
    echo "❌ Phase $phase environment creation FAILED"
    echo "   See log: /tmp/build_phase${phase}_${timestamp}.log"
    exit 1
  fi
  
  echo "End time: $(date)"
  echo "Activating environment for quick validation..."
  # Quick validation that the env works
  conda run -n "$env_name" python -c "import sys; print(f'✅ Python {sys.version}')" || exit 1
  echo ""
done

echo "=========================================="
echo "✅ All 4 phased environments built successfully!"
echo "=========================================="
echo ""
echo "Environments created:"
conda env list | grep "justnews-py312-phase"
echo ""
echo "To activate Phase 1: conda activate justnews-py312-phase1"
echo "To activate Phase 2: conda activate justnews-py312-phase2"
echo "To activate Phase 3: conda activate justnews-py312-phase3"
echo "To activate Phase 4: conda activate justnews-py312-phase4"
echo ""
echo "Total build time: $(date)"
