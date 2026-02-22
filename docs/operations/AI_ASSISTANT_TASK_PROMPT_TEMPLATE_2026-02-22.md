# AI Assistant Task Prompt Template (Multi-Source Refactor)

Use this template to increase compliance with refactor guardrails in every AI-assisted implementation task.

## Template

**Objective**
- Implement `<specific outcome>` for milestone `<M0/M1/M2/M3/M4>`.

**Mandatory Context (Read First)**
- `docs/operations/AI_ASSISTANT_REFACTOR_GUARDRAILS_2026-02-22.md`
- `docs/operations/MULTI_SOURCE_REFACTOR_PROJECT_PLAN_2026-02-22.md`
- `docs/operations/MULTI_SOURCE_REFACTOR_ACTION_CHECKLIST_2026-02-22.md`

**In Scope**
- `<exact components/files allowed>`

**Out of Scope**
- `<forbidden changes>`

**Implementation Requirements**
- Keep changes minimal and auditable.
- Include lane/provenance behavior impact summary.
- Include rollback steps and revert-signal checks.

**Validation Requirements**
- Required tests: `<unit/integration/regression>`
- Required metrics checks: `<specific dashboards/queries>`
- Acceptance criteria: `<AT-xx or explicit criteria>`

**Rollout Constraints**
- Environment order: `dev -> canary -> full`
- No production-first behavior changes.

**Required Output Format**
1. Files changed + why
2. Tests run + results
3. Metrics checks + observations
4. Rollback procedure + verification signals
5. Risks or blockers

## Ready-to-Paste Short Prompt

Proceed with this task under strict refactor guardrails. First read and follow:
- docs/operations/AI_ASSISTANT_REFACTOR_GUARDRAILS_2026-02-22.md
- docs/operations/MULTI_SOURCE_REFACTOR_PROJECT_PLAN_2026-02-22.md
- docs/operations/MULTI_SOURCE_REFACTOR_ACTION_CHECKLIST_2026-02-22.md

Implement only the scoped changes, provide validation evidence, and include rollback notes.
