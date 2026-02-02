# Phased Environment Rollout Plan - Final Implementation

**Date Created:** February 2, 2026  
**Status:** Ready for Execution  
**Total Estimated Time:** 2-2.5 hours

---

## Overview

This document outlines the complete plan to validate and activate all 4 phased conda environments (phase1-phase4) for the JustNews workflow orchestrator. Execution follows a dependency-ordered sequence from quick validation through end-to-end testing.

---

## Execution Strategy

Each phase depends on successful completion of previous phases. If a blocker is found, context is preserved and next phase can be attempted after fix is applied.

---

## Phase 1: Quick Validation (15 min)

**Goal:** Confirm all 4 environments are functionally ready before expensive full test runs.

**Steps:**

### 1.1 Phase 1 (GPU-enabled imports)
```bash
conda run -n justnews-py312-phase1 pytest tests/adapters/test_adapter_base.py -v -x
```

### 1.2 Phase 2 (CPU clustering)
```bash
conda run -n justnews-py312-phase2 pytest tests/adapters/test_adapter_base.py -v -x
```

### 1.3 Phase 3 (LLM/GPU)
```bash
conda run -n justnews-py312-phase3 pytest tests/adapters/test_adapter_base.py::test_base_adapter_methods_raise -v -x
```

### 1.4 Phase 4 (Django/CPU)
```bash
conda run -n justnews-py312-phase4 pytest tests/adapters/test_adapter_base.py -v -x
```

**Success Criteria:** 
- All 4 pass without import/dependency errors
- Minimum 5 min per phase for full test execution

**Blocker Response:** 
If any phase fails, logs show missing dependency → install via conda/pip and retry.

**Expected Output:**
```
tests/adapters/test_adapter_base.py::test_base_adapter_methods_raise PASSED
tests/adapters/test_adapter_base.py::test_base_adapter_helpers_and_batch_infer PASSED
```

---

## Phase 2: CI/CD Verification (10 min)

**Goal:** Ensure GitHub Actions workflows use correct phase environments.

**Steps:**

### 2.1 Audit CI workflow files
```bash
grep -r "environment\|CANONICAL_ENV\|conda.*activate" .github/workflows/
```

### 2.2 Verify expected patterns

- Testing workflows → phase2 (CPU-only)
- GPU orchestrator tests → phase1 or phase3
- vLLM tests → phase3
- Dashboard/Django tests → phase4

### 2.3 Document current state

Create summary:
```bash
grep -l "environment\|pytest\|conda" .github/workflows/*.yml | while read f; do
  echo "=== $f ===" 
  grep "conda\|environment" "$f" | head -5
done
```

**Success Criteria:** 
- All workflows reference phase-specific environments or use CANONICAL_ENV variable
- No workflows explicitly reference unified `justnews-py312` environment

**Blocker Response:** 
If workflows use wrong phases, note them for update in next iteration.

**Expected Output:**
```
Uses: pytorch/pytorch-docker-action@v1.1
  with:
    environment_file: conda/environment.phase2.yml
```

---

## Phase 3: Systemd Service Activation (20 min)

**Goal:** Verify systemd services can activate with phased environments.

**Steps:**

### 3.1 Check systemd service files for environment references
```bash
grep -r "PYTHON_BIN\|CANONICAL_ENV\|Environment=" infrastructure/systemd/
```

### 3.2 Dry-run canonical startup
```bash
./infrastructure/systemd/canonical_system_startup.sh --dry-run
```

Expected output shows environment variable resolution without actual service start.

### 3.3 Attempt actual startup on test service

```bash
sudo systemctl start justnews@gpu_orchestrator
```

### 3.4 Verify service status and logs
```bash
sudo systemctl status justnews@gpu_orchestrator
sudo journalctl -u justnews@gpu_orchestrator -n 50
sudo journalctl -u justnews@gpu_orchestrator -n 50 --follow
```

**Success Criteria:**
- Dry-run completes without errors
- Service starts and transitions to `active (running)`
- Logs show correct PYTHON_BIN path (includes phase name)
- No "command not found" or "PYTHON_BIN not set" errors

**Blocker Response:**
If service fails to start:
1. Check logs for specific error (missing path, conda env not found, permission denied)
2. Verify global.env has correct CANONICAL_ENV set
3. Verify PYTHON_BIN path exists: `ls -la /home/adra/miniconda3/envs/justnews-py312-phase1/bin/python`
4. Check systemd service file has correct EnvironmentFile reference

**Common Issues & Fixes:**
| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: No module named 'X'` | Missing dependency in phase env; reinstall with `pip install X` |
| `/home/adra: command not found` | Path not using `$HOME` variable; update systemd service file |
| `conda: command not found` | conda not in PATH; verify CONDA_PREFIX in global.env |
| `Permission denied` | Run with `sudo`; check service user permissions |

---

## Phase 4: Full Test Suite per Phase (60+ min total)

**Goal:** Comprehensive validation of each phase environment.

**Steps:**

### 4.1 Phase 1 full test suite (GPU-heavy)
```bash
conda run -n justnews-py312-phase1 pytest tests/ -v --tb=short --timeout=30 2>&1 | tee /tmp/phase1_tests.log
```

Expected: 500+ tests collected, ~90% passing

### 4.2 Phase 2 full test suite (CPU-only)
```bash
conda run -n justnews-py312-phase2 pytest tests/ -v --tb=short --timeout=30 2>&1 | tee /tmp/phase2_tests.log
```

Expected: 450+ tests collected, ~90% passing

### 4.3 Phase 3 full test suite (LLM/GPU)
```bash
conda run -n justnews-py312-phase3 pytest tests/agents/gpu_orchestrator/ -v --tb=short --timeout=30 2>&1 | tee /tmp/phase3_tests.log
```

Expected: 50+ tests collected for GPU orchestrator, ~85% passing (some vLLM tests may be skipped)

### 4.4 Phase 4 full test suite (Django)
```bash
conda run -n justnews-py312-phase4 pytest tests/dashboard/ -v --tb=short --timeout=30 2>&1 | tee /tmp/phase4_tests.log
```

Expected: 100+ tests collected, ~90% passing

**Success Criteria:**
- ≥90% tests passing per phase
- Failures are phase-incompatible tests (expected, not blockers)
- No import errors or dependency issues

**Failure Analysis:**
```bash
# Extract failed tests
grep FAILED /tmp/phase*_tests.log | head -20

# Extract error summary
tail -100 /tmp/phase*_tests.log | grep -A5 "FAILED\|ERROR"
```

**Blocker Response:**
If failures exceed 10% per phase:
1. Investigate root cause (missing dep, environment isolation issue)
2. Check if failures are phase-specific (expected) or environment setup issue
3. If missing dependency: `conda run -n justnews-py312-phaseX pip install <package>`
4. Re-run test to confirm fix

---

## Phase 5: End-to-End Workflow Test (30-60 min)

**Goal:** Validate complete pipeline works across all 4 phases in sequence.

**Steps:**

### 5.1 Switch to Phase 1 - Ingestion
```bash
./scripts/dev/select_phase_env.sh --phase 1
source global.env
conda run -n justnews-py312-phase1 python -c "from agents.crawler import CrawlerAgent; print('Phase 1 OK')"
```

### 5.2 Phase 1 - Embedding Generation
```bash
conda run -n justnews-py312-phase1 python -c "from agents.memory import MemoryAgent; print('Phase 1 Embedding OK')"
```

### 5.3 Switch to Phase 2 - Clustering
```bash
./scripts/dev/select_phase_env.sh --phase 2
source global.env
conda run -n justnews-py312-phase2 python -c "import hdbscan; print('Phase 2 OK')"
```

### 5.4 Switch to Phase 3 - Synthesis
```bash
./scripts/dev/select_phase_env.sh --phase 3
source global.env
conda run -n justnews-py312-phase3 python -c "from agents.synthesizer import SynthesizerAgent; print('Phase 3 OK')"
```

### 5.5 Switch to Phase 4 - Publishing
```bash
./scripts/dev/select_phase_env.sh --phase 4
source global.env
conda run -n justnews-py312-phase4 python -c "import django; print('Phase 4 OK')"
```

**Success Criteria:**
- Each phase switch completes without errors
- All phase agents/modules import successfully
- Data serialization compatible across phases (schemas match)
- No environment variable conflicts between phase switches

**Blocker Response:**
If data incompatibility found between phases:
1. Check serialization format (JSON, protobuf, pickle)
2. Compare schemas across phases
3. Trace back to serialization point and fix
4. Example: article schema change from Phase 1 to Phase 2 → update intermediate schema validator

---

## Phase 6: Documentation Review (15 min)

**Goal:** Ensure all docs are accurate and guide users correctly.

**Steps:**

### 6.1 Review critical docs for phase accuracy
```bash
grep -l "environment\|CANONICAL_ENV\|conda" docs/SETUP_GUIDE.md docs/operations/STARTUP_CHECKLIST.md CONTRIBUTING.md
```

### 6.2 Check for remaining hardcoded paths
```bash
grep -r "justnews-py312[^-]" docs/ | grep -v "justnews-py312-phase" | grep -v "legacy\|migration"
grep -r "^/home/adra" docs/ | grep -v "example\|legacy"
```

### 6.3 Update any found references with phase-aware defaults

Expected: No matches for non-phased `justnews-py312` or hardcoded `/home/adra` paths in active docs.

### 6.4 Verification checklist
- [ ] SETUP_GUIDE.md mentions phase selection with `select_phase_env.sh`
- [ ] STARTUP_CHECKLIST.md defaults to phase1
- [ ] CONTRIBUTING.md references `${CANONICAL_ENV:-justnews-py312-phase1}`
- [ ] ENVIRONMENT_CONFIG.md uses `$HOME` for all paths
- [ ] All example commands use `conda run -n ${CANONICAL_ENV:-justnews-py312-phase1}`

**Success Criteria:** 
- All docs reference phased environments
- All docs use multi-user compatible paths (`$HOME` not `/home/adra`)
- Examples are copy-paste ready and reference correct phase defaults

---

## Timeline & Resource Allocation

| Phase | Duration | Dependencies | Owner | Status |
|-------|----------|--------------|-------|--------|
| Phase 1 | 15 min | None | Automated | ⏳ Ready |
| Phase 2 | 10 min | Phase 1 ✓ | Manual review | ⏳ Ready |
| Phase 3 | 20 min | Phase 2 ✓ | Manual/sudo | ⏳ Ready |
| Phase 4 | 60+ min | Phase 3 ✓ | Automated | ⏳ Ready |
| Phase 5 | 30-60 min | Phase 4 ✓ | Manual | ⏳ Ready |
| Phase 6 | 15 min | Phase 5 ✓ | Manual review | ⏳ Ready |

**Total Estimated Time: 2-2.5 hours**

---

## Success/Failure Checkpoints

### ✅ All Green
Proceed to production rollout documentation. Mark implementation complete.

### ⚠️ Phase 1-2 Fail
Environment creation/import issue → rebuild affected phase with `conda env remove -n <env> -y && conda env create -f conda/environment.phaseX.yml`

### ⚠️ Phase 3 Fail
Systemd config issue → fix service unit files in `infrastructure/systemd/`, check EnvironmentFile paths, verify global.env sourcing

### ⚠️ Phase 4-5 Fail
Test/workflow issue → investigate test compatibility, check if failures are phase-expected, add skip markers if needed

### ⚠️ Phase 6 Fail
Documentation gap → update guides with correct phase references and `$HOME` paths

---

## Rollout Decision Gate

Before marking implementation complete, verify all checkboxes:

- [ ] Phase 1: Quick smoke tests PASSED (all 4 phases OK)
- [ ] Phase 2: CI/CD workflows reference correct phases
- [ ] Phase 3: Systemd service activation PASSED
- [ ] Phase 4: Full test suites PASSED (≥90%, no critical failures)
- [ ] Phase 5: End-to-end workflow PASSED (data flows across all phases)
- [ ] Phase 6: Documentation PASSED (accurate, multi-user compatible)
- [ ] No critical blockers in logs
- [ ] At least 1 complete end-to-end workflow successful
- [ ] All documentation reviewed and updated

### Final Approval Criteria

**Ready for Production ✅**
- All 6 phases completed successfully
- Test success rate ≥90% per phase
- Systemd services activate correctly with phased environments
- End-to-end workflow validated
- Documentation accurate and comprehensive

---

## Appendix: Quick Reference Commands

### Environment Management
```bash
# List all phased environments
conda env list | grep phase

# Activate a phase
conda activate justnews-py312-phase1

# Select phase (updates global.env)
./scripts/dev/select_phase_env.sh --phase 1

# View current selection
source global.env && echo "CANONICAL_ENV=$CANONICAL_ENV"
```

### Testing
```bash
# Quick test in phase
conda run -n justnews-py312-phase1 pytest tests/adapters/ -v

# Run specific test
conda run -n justnews-py312-phase2 pytest tests/agents/analyst/test_discovery.py::test_discovery_cycle_creates_story -v

# Run with output capture
conda run -n justnews-py312-phase3 pytest tests/ -v -s --tb=short
```

### Service Management
```bash
# Check service status
sudo systemctl status justnews@gpu_orchestrator

# View service logs (live)
sudo journalctl -u justnews@gpu_orchestrator -f

# View last 50 lines
sudo journalctl -u justnews@gpu_orchestrator -n 50

# Restart service
sudo systemctl restart justnews@gpu_orchestrator
```

### Diagnostics
```bash
# Check PYTHON_BIN correctness
source global.env
$PYTHON_BIN --version

# Verify conda env exists
conda env list | grep phase1

# Check import in phase
conda run -n justnews-py312-phase1 python -c "import torch; print('OK')"

# Check global.env
grep CANONICAL_ENV global.env
grep PYTHON_BIN global.env
```

---

**Document Version:** 1.0  
**Last Updated:** February 2, 2026  
**Next Review:** After Phase 1 execution
