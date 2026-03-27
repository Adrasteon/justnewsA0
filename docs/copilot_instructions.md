# Copilot / Assistant Instructions (project canonical)

This document formalizes the model-and-assistant guidelines for the JustNews repository. Keep this tracked and visible
to contributors; it complements the private `.copilot-instructions` file which individuals may keep locally.

Purpose ------- Make the repository's expectations explicit when automated assistants (GitHub Copilot, other LLM
helpers, or CI agents) suggest or apply fixes and edits.

Mandatory guardrails for multi-source refactor -------------------------------------------

For any task related to the Multi-Source Integrity Refactor, assistants must treat the following as required
preflight context before proposing edits:

- `docs/operations/AI_ASSISTANT_REFACTOR_GUARDRAILS_2026-02-22.md`
- `docs/operations/MULTI_SOURCE_REFACTOR_PROJECT_PLAN_2026-02-22.md`
- `docs/operations/MULTI_SOURCE_REFACTOR_ACTION_CHECKLIST_2026-02-22.md`

Required behavior for refactor tasks:

- State which guardrail section(s) the implementation follows.
- Keep changes strictly in approved scope unless human approval expands scope.
- Include acceptance-test evidence and rollback notes in task output.
- Refuse silent policy-threshold changes in production-first workflows.

Task preflight checklist (must pass):

- [ ] Confirm objective maps to project-plan milestone
- [ ] Confirm in-scope vs out-of-scope boundaries
- [ ] Confirm validation checks and success criteria
- [ ] Confirm rollback path and revert signals
- [ ] Confirm evidence artifact(s) to attach

Python runtime (project default) -------------------------------- The canonical project Python environment is a conda
environment system with phase-specific variants:

- `justnews-py312-phase1` (Ingestion & Embedding, GPU-heavy)
- `justnews-py312-phase2` (Clustering & Linkage, CPU-only)
- `justnews-py312-phase3` (Synthesis & LLM inference, GPU-heavy)
- `justnews-py312-phase4` (Publication & CMS push, CPU-only)

For local development, use the project `.venv` (`make env-bootstrap`) and run commands via `.venv/bin/python`.

When invoking scripts or running code snippets in documentation, prefer either:

- `conda run -n ${CANONICAL_ENV:-justnews-py312-phase1} python <script>` or

- `PYTHON_BIN=$HOME/miniconda3/envs/${CANONICAL_ENV:-justnews-py312-phase1}/bin/python <script>`

When adding examples or CI configuration, prefer using `${CANONICAL_ENV:-justnews-py312-phase1}` by default (unless a different
environment is explicitly requested). ------------------

- Always consult `/etc/justnews/global.env`(or the configured`SERVICE_DIR`variant) for runtime configuration such
  as`PYTHON_BIN` before making changes that affect runtime, startup or agent behavior.

- If documentation or generated startup scripts introduce a new `PYTHON_BIN`path, update`global.env` (and include a
  human-reviewed note in the PR) — do not hardcode environment-dependent interpreter paths in unrelated source files.

- Assistants should prefer to update `global.env`(or`infrastructure/systemd/examples/justnews.env.example`) rather than
  leaving users with out-of-sync example values.

- Automation exists to help keep `PYTHON_BIN`present:`infrastructure/systemd/scripts/ensure_global_python_bin.sh`(run at
  startup) and a repo validation script`infrastructure/scripts/validate-global-env.sh` (CI-friendly). When proposing
  runtime changes, update both the example and the global env, and ensure a validation step is added or existing
  validation passes.

Core rules (must follow) ------------------------

- Do not create or commit secrets (API keys, credentials, tokens) into the repository.

- Any change that affects authentication, authorization, admin endpoints, data export, or privacy must include an
  explanation, tests, and an audit plan.

- Provide tests for new functionality or changes to existing behavior where practical.

Behavioral guidelines for assistants -----------------------------------

- Limit the scope of edits in a single commit/PR; prefer small, reviewable changes.

- Prefer writing clear, readable code with early returns and small helper functions.

- Add or update `docs/` for any non-trivial change in behavior, API surface, or operational processes.

Package installation policy ---------------------------

- When performing package installs for this project, prefer `conda install` or `mamba install` targeting the canonical
  UV/venv environment (`.venv`) and `requirements-bootstrap.txt` for dependency resolution.

- Only use `pip`as a last resort when a required package or specific wheel is not available via conda; if`pip`is used,
  document the reason and pin the exact version/wheel in the PR and add an update to`environment.yml` where appropriate.

- Avoid modifying the runtime environment using `pip`in CI or system-wide installation steps; prefer conda operations so
  environments remain reproducible. If`pip` must be used in CI, ensure a clear justification is recorded in the change
  and validations are added.

Testing & CI -----------

- Assistants should add tests or update tests when changing functionality. If the change has unavoidable infra
  dependencies (e.g., Redis, MariaDB, Chroma), gate tests behind environment flags and document how to run them locally.

Security & privacy details -------------------------

- Never output or expand private / system-level files (e.g., `/etc/`, private keys) into tracked files or PRs.

- If a change requires secrets for local testing, document the expected local environment variables and keep them out of
  tracked files.

Review & escalation -------------------

- For architectural or large refactors, include a short design rationale and request review from the relevant subsystem
  owners.

- When uncertain about safety or side effects (especially in “synthesizer”, “critic”, or anything producing public
  content), escalate to a human reviewer before merging.

Recommended local file (.copilot-instructions) --------------------------------------------- Keep a short, private
`.copilot- instructions` file at the repo root (gitignored) for any personal preferences and developer-specific
guardrails. See `.gitignore`which already includes`.copilot-instructions`.

Examples --------

- Good: Small bugfix + unit test + updated docs + short PR message explaining the rationale.

- Bad: Large sweeping refactor to security/auth code pushed without tests or a design note.

Where automation can help ------------------------

- Reformatting, import cleanup, unit test scaffolding, small bugfixes, and doc generation (provided tests remain green).

Contact & ownership -------------------

- Keep a link to the teams or owners for major modules in the PRs. Codeowners (if present) should be requested to review
  sensitive or production-impacting changes.

Maintainers can update this file to reflect evolving policies.
