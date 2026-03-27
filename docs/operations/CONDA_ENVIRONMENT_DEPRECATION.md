# Conda Environment Deprecation (JustNews)

Status: fully deprecated
Owner: JustNews platform maintainers
Effective date: 2026-03-26

Summary
- JustNews has migrated from conda-based runtime environments to a UV-managed project-local `.venv`.
- Conda env names (`justnews-py312`, `justnews-py312-phase*`) are deprecated and should not be used for active development, CI, or test execution.

What is now supported
- Primary runtime: `/app/.venv` (or repo-local `.venv`)
- Bootstrap:
  - `make env-bootstrap`
  - or `uv venv .venv && uv pip install -r requirements-bootstrap.txt`
- Test execution:
  - `./scripts/dev/pytest.sh`
  - `make test`

What is deprecated
- Any use of:
  - `conda run -n ...`
  - `mamba run -n ...`
  - `scripts/bootstrap_conda_env.sh` (kept only as a deprecated compatibility wrapper)
  - `scripts/dev/run_pytest_conda.sh`
  - `scripts/dev/select_phase_env.sh`
  - legacy phase environment manifests for runtime/test setup

Hard-clean archive policy
- Legacy conda assets were moved out of active runtime paths into a local gitignored archive:
  - `archive_local/conda-deprecated/`
- This includes prior `conda/` manifests/recipes and conda-only helper scripts.
- Active code, CI, and systemd flows must not depend on archive content.

Migration checklist
1) Ensure UV is installed.
2) Create venv: `make env-bootstrap`.
3) Update shell/editor to use `.venv/bin/python`.
4) Replace conda invocations in local scripts with `.venv/bin/python -m ...`.
5) Run smoke validation:
   - `make lint-no-containers`
   - `make lint`
   - `make test`

Conda removal steps (local machine)
Warning: run only on machines where you intend to remove legacy JustNews conda envs.

- List old envs:
  - `conda env list | grep -E 'justnews-py312|justnews-py312-phase'`
- Remove old envs:
  - `conda env remove -n justnews-py312 || true`
  - `conda env remove -n justnews-py312-phase1 || true`
  - `conda env remove -n justnews-py312-phase2 || true`
  - `conda env remove -n justnews-py312-phase3 || true`
  - `conda env remove -n justnews-py312-phase4 || true`
- Verify removal:
  - `conda env list`

Repository policy
- New code and docs must not introduce active conda runtime instructions.
- Historical/archival references are permitted only in this deprecation document and archival folders.

If you must temporarily use legacy conda
- This is unsupported and at-risk.
- Use `ALLOW_ANY_PYTEST_ENV=1` only for temporary local debugging and never in canonical CI paths.
