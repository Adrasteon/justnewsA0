# Implementation Summary: Phased Conda Environments for JustNews

**Date**: February 2, 2026  
**Status**: ✅ Implementation Complete  
**Scope**: Clean, maintainable dependency management for 4-phase workflow

---

## What Was Implemented

### 1. ✅ Phase-to-Agent Mapping Document
**File**: [PHASED_ENVIRONMENT_MAPPING.md](PHASED_ENVIRONMENT_MAPPING.md)

Maps the 4 Living Stories workflow phases to agents, dependencies, and GPU requirements:

- **Phase 1** (Ingestion & Vectorization): GPU-enabled crawler, memory (embeddings)
- **Phase 2** (Clustering & Linkage): CPU-only clustering (hdbscan, umap)
- **Phase 3** (Synthesis & Curation): GPU-enabled synthesizer, critic, analyst  
- **Phase 4** (Publication & CMS): CPU-only chief_editor, journalist

Includes dependency breakdown, conflict resolution matrix, testing strategies, and lock file guidance.

---

### 2. ✅ Split Environment YAML Files
**Location**: `/conda/`

| File | Scope | GPU | Size |
|------|-------|-----|------|
| `environment.base.yml` | Shared (Python, FastAPI, DB, parsing, testing) | ❌ | ~60 deps |
| `environment.phase1.yml` | Ingestion + base (PyTorch, sentence-transformers, crawl4ai) | ✅ | +15 deps |
| `environment.phase2.yml` | Clustering + base (hdbscan, umap, NO torch/vllm) | ❌ | +5 deps |
| `environment.phase3.yml` | Synthesis + base (vLLM, bitsandbytes, transformers) | ✅ | +12 deps |
| `environment.phase4.yml` | Publishing + base (minimal, django extensions) | ❌ | +2 deps |

**Benefits**:
- Base shared cleanly across all 4 phases
- GPU deps isolated to Phases 1 & 3 only
- CPU phases avoid CUDA overhead entirely
- Each phase resolved independently without dependency conflicts

---

### 3. ✅ Phase Selection Script
**File**: `scripts/dev/select_phase_env.sh`

**Features**:
- Select active phase with `--phase 1|2|3|4`
- Updates `global.env` with phase-specific CANONICAL_ENV and PYTHON_BIN
- View all available phases with `--list-only`
- Verify phase exists without switching (`--verify`)
- Provides helpful phase descriptions and instructions

**Usage**:
```bash
bash scripts/dev/select_phase_env.sh --phase 2
source ./global.env  # Env vars now point to phase2
```

---

### 4. ✅ Extended Setup Script
**File**: `scripts/dev/setup_dev_environment.sh` (updated)

**New Features**:
- `--create-all-phases`: Creates all 4 environments at once
- `--update-phases`: Safely updates existing phase envs
- Maintains backward compatibility with `--create-dev` and `--install-into-existing`

**Usage**:
```bash
bash scripts/dev/setup_dev_environment.sh --create-all-phases  # ~5-15 min
```

---

### 5. ✅ Updated Setup Guide
**File**: `docs/operations/SETUP_GUIDE.md`

**New Section**: Phase 1B "Phased Environment Setup (Recommended for GPU Systems)"

Covers:
- Overview of 4-phase model and benefits
- Step-by-step creation of all phases
- Phase selection and verification
- GPU availability checking (Phase 1 & 3)
- Phase switching workflow
- Tips for multi-terminal development

**Diagram**:
```
Phase 1: Crawl → Phase 2: Cluster → Phase 3: Synthesize → Phase 4: Publish → [Loop]
```

---

### 6. ✅ Conda Directory Documentation
**File**: `conda/README.md` (updated)

Quick start guide + reference to full PHASED_ENVIRONMENT_MAPPING.md

---

## Verification & Testing

### Smoke Test Protocol

Each phase can be validated independently:

**Phase 1** (GPU ingestion):
```bash
bash scripts/dev/select_phase_env.sh --phase 1
bash scripts/run_with_env.sh python -c "
import torch
import sentence_transformers
import crawl4ai
print('✅ Phase 1 GPU stack loaded')
"
```

**Phase 2** (CPU clustering, no GPU):
```bash
bash scripts/dev/select_phase_env.sh --phase 2
bash scripts/run_with_env.sh python -c "
import hdbscan
import umap
try:
    import torch
    print('❌ ERROR: Phase 2 should NOT have torch!')
    exit(1)
except ImportError:
    print('✅ Phase 2 correctly excludes GPU deps')
"
```

**Phase 3** (GPU synthesis):
```bash
bash scripts/dev/select_phase_env.sh --phase 3
bash scripts/run_with_env.sh python -c "
import vllm
import torch
import bitsandbytes
print('✅ Phase 3 GPU synthesis stack loaded')
"
```

**Phase 4** (CPU publishing, minimal):
```bash
bash scripts/dev/select_phase_env.sh --phase 4
bash scripts/run_with_env.sh python -c "
import django
try:
    import torch
    print('❌ ERROR: Phase 4 should NOT have torch!')
except ImportError:
    print('✅ Phase 4 correctly excludes GPU deps')
"
```

---

## How It Works

### Environment Flow

1. **Initial Setup**:
   ```bash
   bash scripts/dev/setup_dev_environment.sh --create-all-phases
   ```
   Creates 4 conda envs: `justnews-py312-phase{1,2,3,4}`

2. **Phase Selection**:
   ```bash
   bash scripts/dev/select_phase_env.sh --phase 2
   ```
   Updates `global.env`:
   - `CANONICAL_ENV=justnews-py312-phase2`
   - `PYTHON_BIN=/path/to/phase2/bin/python`
   - `CONDA_PREFIX=/path/to/phase2`

3. **Command Execution**:
   ```bash
   bash scripts/run_with_env.sh python script.py
   ```
   `run_with_env.sh` sources `global.env`, which now points to phase2 Python

4. **Phase Switching**:
   ```bash
   bash scripts/dev/select_phase_env.sh --phase 3
   source global.env  # New phase3 vars loaded
   bash scripts/run_with_env.sh python synthesizer.py
   ```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **4 separate YAML files** | Isolates CUDA/GPU to 2 phases, prevents version conflicts |
| **Shared base.yml** | Eliminates duplication of 60+ common deps |
| **Phase selection via global.env** | Uses existing run_with_env.sh wrapper, no new infrastructure |
| **Python 3.12 only** | Matches current standard, no mixed versions needed |
| **mamba support** | Faster conda resolution, especially for Phase 1 & 3 |
| **Backward compatibility** | Old `environment.yml` retained, scripts still work |

---

## Files Modified/Created

### New Files
- ✅ `conda/environment.base.yml` — Shared base deps
- ✅ `conda/environment.phase1.yml` — Ingestion (GPU)
- ✅ `conda/environment.phase2.yml` — Clustering (CPU)
- ✅ `conda/environment.phase3.yml` — Synthesis (GPU)
- ✅ `conda/environment.phase4.yml` — Publishing (CPU)
- ✅ `conda/PHASED_ENVIRONMENT_MAPPING.md` — Detailed mapping & strategy
- ✅ `scripts/dev/select_phase_env.sh` — Phase selection utility
- ✅ `docs/operations/SETUP_GUIDE.md` — Phase 1B section added

### Updated Files
- ✅ `scripts/dev/setup_dev_environment.sh` — Added phase creation/update functions
- ✅ `conda/README.md` — Quick reference for phased envs

---

## Next Steps for Users

### First Time (Local Dev)
```bash
git clone https://github.com/.../JustNews.git
cd JustNews

# 1. Create all 4 phases
bash scripts/dev/setup_dev_environment.sh --create-all-phases

# 2. Select Phase 1 (default for development)
bash scripts/dev/select_phase_env.sh --phase 1
source ./global.env

# 3. Run crawler or embedding code
python agents/crawler/main.py
```

### Workflow Progression
```bash
# Ingestion done, move to clustering
bash scripts/dev/select_phase_env.sh --phase 2
python -m agents.workflow_orchestrator.engine  # Runs clustering policies

# Clustering done, move to synthesis
bash scripts/dev/select_phase_env.sh --phase 3
python agents/synthesizer/main.py

# Synthesis done, publish
bash scripts/dev/select_phase_env.sh --phase 4
python agents/chief_editor/main.py
```

### Ongoing Development
- Keep multiple terminals, each sourcing different phases
- Switch phases when moving between pipeline stages
- Update phases when environment.phaseX.yml changes:
  ```bash
  bash scripts/dev/setup_dev_environment.sh --update-phases
  ```

---

## Troubleshooting

### "ImportError: No module named 'torch'" in Phase 1
→ Verify phase is selected: `bash scripts/dev/select_phase_env.sh --phase 1`

### "vLLM fails with CUDA version mismatch"
→ Check `BNB_CUDA_VERSION` env var, ensure it matches local CUDA toolkit

### Phase 2 (clustering) mysteriously has torch
→ Verify correct phase selected: `echo $CANONICAL_ENV` should be `justnews-py312-phase2`

### Environment creation times out
→ Use mamba instead of conda (faster resolution) or increase timeout:
```bash
export CONDA_SOLVER=libmamba
bash scripts/dev/setup_dev_environment.sh --create-all-phases
```

---

## Future Enhancements (Optional)

1. **Conda Lock Files** (for production reproducibility)
   ```bash
   conda-lock lock -f conda/environment.phaseX.yml
   ```

2. **Docker Multi-Stage Builds** (one stage per phase)
   ```dockerfile
   FROM node AS phase1
   ...GPU setup...

   FROM node AS phase2
   ...CPU setup...
   ```

3. **CI/CD Phase Testing** (GitHub Actions matrix)
   - Test each phase environment independently
   - Catch CUDA/pip conflicts early

4. **Systemd Service Integration** (per-phase units)
   - `justnews-phase1.service` (GPU gated)
   - `justnews-phase2.service` (CPU only)
   - Automatic phase ordering

---

## References

- [PHASED_ENVIRONMENT_MAPPING.md](PHASED_ENVIRONMENT_MAPPING.md) — Complete mapping & strategy
- [conda/README.md](README.md) — Quick reference & recipes
- [docs/operations/SETUP_GUIDE.md](../docs/operations/SETUP_GUIDE.md) — Full system setup (Phase 1B added)
- [docs/LIVING_STORIES_IMPLEMENTATION_PLAN.md](../docs/LIVING_STORIES_IMPLEMENTATION_PLAN.md) — 4-phase workflow definition

---

## Summary

✅ **Clean, maintainable environment structure** achieved through:
- Isolated CUDA/GPU to only GPU-heavy phases
- Shared base deps eliminate duplication
- Easy phase switching via existing `run_with_env.sh` wrapper
- Comprehensive documentation for users and operators
- Backward compatible (old `environment.yml` still available)

**Expected outcome**: Hours of GPU/CUDA dependency debugging eliminated, smoother dev workflow, clearer ops procedures.
