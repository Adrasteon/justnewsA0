# JustNews Phased Environment Strategy

**Date:** February 2, 2026  
**Purpose:** Define clean dependency boundaries across 4 workflow phases to eliminate CUDA/GPU friction.

---

## Overview

The JustNews system executes in 4 sequential, GPU-gated phases aligned with the Living Stories workflow. Each phase runs independently, allowing:
- **Isolated CUDA versions**: GPU phases use dedicated environments; CPU phases avoid CUDA overhead.
- **Faster builds**: Phase-specific conda envs skip unnecessary dependencies.
- **Easy switching**: Select active phase via `scripts/dev/select_phase_env.sh`.

---

## Phase-to-Agent Mapping

### **Phase 1: Ingestion & Vectorization** (GPU-Heavy)
*Entry condition*: New crawl job initiated  
*Exit condition*: All articles parsed & embedded

**Primary Agents:**
- `crawler` / `crawler_control`: Web scraping (Crawl4AI, Playwright)
- `memory`: Sentence embedding (sentence-transformers, torch)

**Secondary (Support):**
- `scout`: Source evaluation (lightweight)
- Infrastructure: ChromaDB client (read/write embeddings)

**Key Dependencies:**
- PyTorch (CUDA-enabled) + torchvision, torchaudio
- `sentence-transformers` (requires torch)
- `transformers` (for tokenization)
- `faster-whisper` (if audio support needed)
- `crawl4ai`, `playwright`, `beautifulsoup4`, `trafilatura`
- ChromaDB (vector store client)
- MariaDB (articles table)

**Shared Deps:**
- Python 3.12, numpy, pandas, scipy, networkx
- FastAPI, uvicorn (agent server)
- MCP Bus client
- Database connectors (mysql-connector-python, SQLAlchemy)
- Observability (OpenTelemetry)

---

### **Phase 2: Clustering & Linkage** (CPU-Only)
*Entry condition*: Articles embedded, pending pool populated  
*Exit condition*: All articles assigned to clusters or archived

**Primary Agents:**
- `memory`: Pending pool management, ChromaDB queries
- Discovery logic: HDBSCAN clustering (runs as part of workflow_orchestrator or standalone)

**Secondary (Support):**
- `workflow_orchestrator`: Orchestrates Phase 2 policies (IncrementalClusteringPolicy)

**Key Dependencies:**
- `hdbscan` (density-based clustering)
- `umap-learn` (dimensionality reduction)
- `scikit-learn` (clustering utilities)
- ChromaDB (query operations only)
- MariaDB (cluster assignment)
- **NO PyTorch, NO vllm, NO CUDA**

**Shared Deps:**
- Same as Phase 1

---

### **Phase 3: Synthesis & Curation** (GPU-Heavy)
*Entry condition*: Clusters complete, story updates ready  
*Exit condition*: All synthesized_articles populated with summaries & critiques

**Primary Agents:**
- `synthesizer`: LLM synthesis via vLLM (aggregate_cluster, summarize_article)
- `critic`: Critique generation
- `analyst`: Re-analysis of synthesized content (if needed)

**Secondary (Support):**
- `memory`: Context retrieval
- `workflow_orchestrator`: Orchestrates Phase 3 policies (ClusterToSynthesisPolicy, SynthesisToCritiquePolicy, HeavyClusterRetryPolicy)

**Key Dependencies:**
- vLLM (inference server, quantized models)
- PyTorch (CUDA-enabled)
- `transformers` (for model loading)
- `bitsandbytes` (4-bit/8-bit quantization)
- `accelerate` (distributed inference)
- `sentence-transformers` (helper embeddings)
- MariaDB (read clusters, write synthesized_articles)
- ChromaDB (optional context lookup)
- **GPU memory critical**: 8GB+ VRAM recommended

**Shared Deps:**
- Same as Phase 1

---

### **Phase 4: Publication & CMS Push** (CPU-Only)
*Entry condition*: Stories critiqued and ready for publication  
*Exit condition*: Stories published to CMS/RSS

**Primary Agents:**
- `chief_editor`: Story publication to CMS
- `journalist`: Story formatting & metadata
- Optional: `archive`: Long-term storage

**Secondary (Support):**
- `workflow_orchestrator`: Orchestrates Phase 4 policy (SynthesisToPublishingPolicy)

**Key Dependencies:**
- MariaDB (read synthesized_articles, write publication status)
- HTTP clients for CMS push (aiohttp, httpx)
- Optional: `django` (if CMS is integrated)
- **NO PyTorch, NO vllm, NO CUDA**

**Shared Deps:**
- Same as Phase 1

---

## Environment File Structure

```
conda/
├── README.md                          # Phased env guide & troubleshooting
├── PHASED_ENVIRONMENT_MAPPING.md      # This file
├── environment.base.yml               # Shared base (Python, common libs, no GPU)
├── environment.phase1.yml             # Ingestion: +PyTorch, +sentence-transformers
├── environment.phase2.yml             # Clustering: +hdbscan, +umap, CPU-only
├── environment.phase3.yml             # Synthesis: +vllm, +bitsandbytes, GPU
└── environment.phase4.yml             # Publishing: minimal, CPU-only
```

---

## Dependency Split Strategy

### **Base Environment** (`environment.base.yml`)
Shared by all phases:
- Python 3.12.11
- gcc/gxx (build tools)
- numpy, scipy, pandas, scikit-learn, networkx, numba
- mysql-connector-python, SQLAlchemy, aiosqlite
- FastAPI, uvicorn, starlette, Django
- requests, httpx, aiohttp, aiofiles, uvloop
- testing: pytest, pytest-asyncio, pytest-cov, ruff, mypy
- parsing: trafilatura, beautifulsoup4, lxml, dateparser, etc.
- opentelemetry (tracing)

### **Phase 1 Additions** (`environment.phase1.yml`)
*Inherits base via `pip install -e /path/to/repo` or manual conda/pip extension*
- PyTorch (CPU-enabled fallback, CUDA 11.8/12.2 enabled)
- torchvision, torchaudio
- sentence-transformers
- transformers
- crawl4ai, playwright (browser automation)
- faster-whisper (audio transcription)
- chromadb
- nvidia-ml-py (GPU monitoring)

### **Phase 2 Additions** (`environment.phase2.yml`)
*Inherits base*
- hdbscan
- umap-learn
- scikit-learn (extended clustering)
- chromadb (lighter install, query-only)
- **Explicitly exclude**: torch, vllm, bitsandbytes, cuda-toolkit

### **Phase 3 Additions** (`environment.phase3.yml`)
*Inherits base, shares GPU stack with Phase 1*
- vllm (inference engine)
- PyTorch (CUDA-enabled)
- transformers
- bitsandbytes (4-bit quantization)
- accelerate (distributed inference)
- sentence-transformers (for embeddings)
- peft (adapter fine-tuning)
- chromadb

### **Phase 4 Additions** (`environment.phase4.yml`)
*Inherits base only*
- Minimal: Django extensions, logging, optional HTTP middleware
- **No GPU deps**

---

## Activation Workflow

### **Setup** (First Time)
```bash
# Create all phase envs
cd /path/to/JustNews
bash scripts/dev/setup_dev_environment.sh --create-all-phases

# Select active phase (default: phase1)
bash scripts/dev/select_phase_env.sh --phase 1
```

### **Switching Phases** (Ongoing)
```bash
# Switch from Phase 1 to Phase 2 (e.g., after crawl finishes)
bash scripts/dev/select_phase_env.sh --phase 2

# Verify
source global.env
echo $CANONICAL_ENV  # Should print: justnews-py312-phase2
which python        # Should show: <conda>/justnews-py312-phase2/bin/python
```

### **Running with Selected Phase**
```bash
# All existing scripts automatically inherit the selected phase env
bash scripts/run_with_env.sh python -c "import torch; print(torch.__version__)"
```

---

## CUDA Configuration

### **Recommended Setup (GPU-enabled hosts)**
```bash
# Set in scripts/dev/select_phase_env.sh or global.env
export BNB_CUDA_VERSION=122              # bitsandbytes CUDA 12.2
export CUDA_VISIBLE_DEVICES=0            # Restrict to GPU 0 during dev
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True  # Reduce fragmentation OOMs
```

### **CPU-Only Fallback** (for Phase 2/4 or GPU-unavailable hosts)
```bash
# Phase 2/4 envs skip CUDA entirely; no config needed
# Phase 1/3 on CPU hosts: PyTorch auto-detects no GPU
export CUDA_VISIBLE_DEVICES=""  # Hide any GPU
export CPU_ONLY=1               # Optional override
```

---

## Dependency Conflict Resolution

### **Common Issues & Fixes**

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| `ImportError: No module named 'torch'` in Phase 2 | GPU env not deactivated | Run `select_phase_env.sh --phase 2` |
| vLLM fails to initialize | CUDA version mismatch | Check `BNB_CUDA_VERSION`, reinstall bitsandbytes |
| ChromaDB segfault on startup | Shared library conflict | Pre-init disables Chroma in orchestrator (by design) |
| `hdbscan` build fails | Missing C compiler | Ensure `gcc_linux-64`, `gxx_linux-64` in conda |
| Pickle incompatibility across phases | Env version drift | Regenerate locks: `conda-lock lock -f environment.phaseX.yml` |

---

## Lock Files (Optional, for Production)

To stabilize CUDA/pip resolution across machines:

```bash
# Install conda-lock
conda install -c conda-forge conda-lock

# Generate lock for each phase
conda-lock lock -f conda/environment.base.yml -o conda/locks/base.lock
conda-lock lock -f conda/environment.phase1.yml -o conda/locks/phase1.lock
# ... repeat for phases 2-4

# Use locked env in CI/staging
conda-lock install -p /path/to/env conda/locks/phase1.lock
```

---

## Testing & Validation

### **Per-Phase Smoke Tests**
Each `environment.phaseX.yml` should pass:

**Phase 1:**
```python
import torch
import sentence_transformers
import crawl4ai
print("✅ Phase 1 GPU stack loaded")
```

**Phase 2:**
```python
import hdbscan
import umap
assert hdbscan.__version__, print("✅ Phase 2 clustering loaded")
try:
    import torch
    print("❌ Phase 2 should NOT have torch!")
except ImportError:
    print("✅ Phase 2 GPU deps correctly excluded")
```

**Phase 3:**
```python
import vllm
import torch
import bitsandbytes
print("✅ Phase 3 synthesis stack loaded")
```

**Phase 4:**
```python
try:
    import torch
    print("❌ Phase 4 should NOT have torch!")
except ImportError:
    print("✅ Phase 4 GPU deps correctly excluded")
```

---

## Notes & Future Improvements

1. **Conda-lock**: Consider adding `conda-lock` files for production reproducibility.
2. **Docker integration**: Phase envs can be mapped to separate Dockerfile stages (multi-stage builds).
3. **Systemd services**: Each phase can run as its own systemd unit with isolated env vars.
4. **CI/CD**: GitHub Actions can run tests per-phase to catch resolve conflicts early.

