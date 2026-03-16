# Multi-Source Refactor — Dev/Staging Parity Runsheet

Date: 2026-02-22  
Scope: Execute and capture remaining non-local artifacts for post-approval parity  
Owner: Ops/QA (shared)

## 1) Objective

Collect dev/staging evidence artifacts referenced by the M2 sign-off evidence index:

- imported dashboard URL + screenshots/exports,
- metrics snapshot,
- rollback drill artifact,
- provenance sample export.

## 2) Prerequisites

- Access to target environment (`dev` or `staging`) and orchestrator endpoint.
- Access to Grafana and alerting system in target environment.
- Ticket/issue to attach artifacts.

Set environment baseline:

```bash
export ORCH_URL="http://<orchestrator-host>:8023"
export ENV_TAG="<dev|staging>"
```

Optional helper script (recommended):

```bash
python scripts/ops/capture_refactor_parity_artifacts.py \
   --orch-url "$ORCH_URL" \
   --env-tag "$ENV_TAG" \
   --dashboard-url "https://<grafana-host>/d/<uid>/multi-source-refactor" \
   --panel-id 101 --panel-id 102 --panel-id 103 --panel-id 104 --panel-id 105 \
   --alert-id "multi_source_refactor_low_verified_share" \
   --alert-id "multi_source_refactor_cluster_promotion_failures" \
   --screenshot-link "https://<artifact-store>/<env>/dashboard-overview.png"
```

The helper writes JSON + Markdown artifacts to:
- `logs/operations/refactor_parity/`

## 3) Dashboard/Alert Parity Capture

1. Import dashboard definition from:
   - `docs/grafana/multi-source-refactor-observability-dashboard.json`
2. Record dashboard URL and panel IDs (`101,102,103,104,105`).
3. Verify alert rules loaded from:
   - `monitoring/alerts/multi_source_refactor_alerts.yml`
4. Capture screenshot/export artifacts.

Evidence fields to record:
- Environment, dashboard URL, panel IDs, alert IDs, screenshot/export links.

## 4) Metrics Snapshot (Dev/Staging)

Preferred (helper-generated): use the `.json`/`.md` files under `logs/operations/refactor_parity/`.

Manual fallback:

```bash
curl -sS "$ORCH_URL/metrics" | grep -E "published_verified_share|published_total_|cluster_promotion_failures|singleton_to_verified_conversion" > "metrics_snapshot_${ENV_TAG}.txt"
```

Attach output file and timestamp.

## 5) Rollback Drill (Dev/Staging)

Preferred (helper-assisted): rerun the helper with `--run-rollback-drill` after confirming target rollback version:

```bash
python scripts/ops/capture_refactor_parity_artifacts.py \
   --orch-url "$ORCH_URL" \
   --env-tag "$ENV_TAG" \
   --run-rollback-drill \
   --rollback-target-version <known-good-version>
```

Use template:
- `docs/operations/MULTI_SOURCE_REFACTOR_ROLLBACK_DRILL_ARTIFACT_TEMPLATE_2026-02-22.md`

Expected core checks:
- apply and rollback responses are `status: ok`,
- latency within agreed bound,
- `owner_overrides` return to baseline,
- lane behavior reverts as expected.

## 6) Provenance Sample Export (Dev/Staging)

Use template:
- `docs/operations/MULTI_SOURCE_REFACTOR_PROVENANCE_SAMPLE_EVIDENCE_TEMPLATE_2026-02-22.md`

Expected core checks:
- required fields present on sampled records,
- completeness summary reported,
- exceptions (if any) documented with remediation owner/ETA.

## 7) Completion Checklist

- [ ] Dashboard URL + alert IDs captured
- [ ] Dashboard screenshots/exports attached
- [ ] Dev/staging metrics snapshot attached
- [ ] Dev/staging rollback drill artifact attached
- [ ] Dev/staging provenance sample artifact attached
- [ ] Links copied into M2 evidence index

## 8) Update Targets

After collection, update:
- `docs/operations/MULTI_SOURCE_REFACTOR_M2_SIGNOFF_EVIDENCE_INDEX_2026-02-22.md`
- `docs/operations/MULTI_SOURCE_REFACTOR_M2_SIGNOFF_SUMMARY_2026-02-22_DRAFT.md` (follow-up status)
