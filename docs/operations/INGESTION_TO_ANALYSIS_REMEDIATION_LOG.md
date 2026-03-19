# Ingestion → Analysis Remediation Log

## Session: 2026-02-18 (Phase 0 Baseline)

### Scope
- Runbook followed: `docs/operations/INGESTION_TO_ANALYSIS_BACKLOG_RUNBOOK.md`
- Phase executed: **Phase 0 — Baseline and Guardrails**
- Behavior/config/code changes applied: **None**

### 0.1 Canonical baseline checks
Command:
```bash
set -a && source /app/global.env && set +a
/app/.venv/bin/python /app/canonical_status_check.py
/app/.venv/bin/python /app/check_workflow_progress.py
/app/.venv/bin/python /app/final_pipeline_status.py
```

Results:
- `canonical_status_check.py`: **System Status 🟢 GO** (13/13 OK)
- `check_workflow_progress.py`:
  - `Total Articles: 2236`
  - `Sources Crawled: 269/274`
  - `Sources With Articles: 202/274`
  - `Analyzed: 1079`
  - `Embedded: 2236`
- `final_pipeline_status.py`:
  - `Crawl Tasks: 67`
  - `Articles Found: 2236`
  - `Articles Ingested: 2236`
  - `Documents Embedded: 2236`
  - `Timestamp: 2026-02-18 14:13:43`

### 0.2 Backlog and throughput metrics
Command:
```bash
set -a && source /app/global.env && set +a && /app/.venv/bin/python - <<'PY'
import os, mysql.connector
conn=mysql.connector.connect(host=os.getenv('MARIADB_HOST','mariadb'),port=int(os.getenv('MARIADB_PORT','3306')),user=os.getenv('MARIADB_USER','justnews'),password=os.getenv('MARIADB_PASSWORD','dev_justnews_password'),database=os.getenv('MARIADB_DB','justnews'))
cur=conn.cursor()
cur.execute("SELECT COUNT(*) FROM articles WHERE analyzed=0")
print('backlog_analyzed0=', cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM articles WHERE analyzed=1 AND updated_at >= (NOW() - INTERVAL 60 MINUTE)")
print('newly_analyzed_last60m=', cur.fetchone()[0])
cur.close(); conn.close()
PY
```

Results:
- `backlog_analyzed0= 1157`
- `newly_analyzed_last60m= 131`

### 0.3 Reliability baseline (log-derived)
Command:
```bash
/app/.venv/bin/python - <<'PY'
import re
from pathlib import Path
log = Path('/tmp/justnews_services_logs/analyst.startup.log').read_text(errors='ignore')
req = len(re.findall(r"Received analyze_article request", log))
err = len(re.findall(r"Lost connection to MySQL server", log))
print('analyst_requests=', req)
print('mysql_disconnect_errors=', err)
print('error_rate_pct=', round((err/req)*100,2) if req else 0)
PY
```

Results:
- `analyst_requests= 181`
- `mysql_disconnect_errors= 16`
- `error_rate_pct= 8.84`

### Phase 0 checkpoint
- Baseline metrics captured and timestamped: ✅
- Rollback owner identified: ✅ **Current operator (session user)**

### Notes
- No remediation actions were applied in this phase.
- Next step (after rollback owner assignment): begin **Phase 1 (config-only throughput lift)** with 15-minute observation windows per runbook.

---

## Session: 2026-02-18 (Phase 1 Blocker Resolution)

### Phase 1 blocker observed
- Symptom: `workflow_orchestrator /status` repeatedly reported defaults (`polling_interval_seconds=10`, `max_concurrent_tasks=5`) after restart.
- Symptom: `config/system_config.json` repeatedly lost the `orchestrator` section.

### Root cause
- Dashboard shutdown path persisted unified config through the typed config manager.
- Unified schema (`config/schemas/__init__.py`) did not include top-level `orchestrator`.
- On persistence, unknown keys were dropped from `system_config.json`, removing Phase 1 orchestrator settings.

### Changes applied
- Added `OrchestratorConfig` + `OrchestratorResourceLimitsConfig` to unified schema and added `orchestrator` to `JustNewsConfig`.
- Updated dashboard config persistence to skip no-op writes when dashboard port is unchanged.
- Re-applied Phase 1 orchestrator values in `config/system_config.json`:
  - `polling_interval_seconds: 5`
  - `max_concurrent_tasks: 10`
  - `resource_limits`: unchanged from runbook defaults.

### Verification evidence
- Full restart cycle completed (`stop_all_services.sh --skip-db` + `start_all_services.sh --skip-db --skip-migrations`).
- Post-restart file check:
  - `has_orchestrator=True` in `config/system_config.json`.
- Post-restart runtime check:
  - `http://127.0.0.1:8023/status` reports `polling_interval_seconds=5` and `max_concurrent_tasks=10`.

### Decision
- Phase 1 config persistence blocker: ✅ **resolved**.
- Next action: run the Phase 1 15-minute observation window and evaluate keep/rollback/iterate criteria per runbook.

---

## Session: 2026-02-18 (Phase 1 Observation Window #1)

### Observation setup
- Window length: 15 minutes (runbook-compliant)
- Runtime config at start (`/status`):
  - `polling_interval_seconds=5`
  - `max_concurrent_tasks=10`

### Metrics (start)
- `backlog_analyzed0=1074`
- `newly_analyzed_last60m=120`
- `fact_checks=5159`
- `synthesized_articles=869`
- `analyst_requests=12`
- `mysql_disconnect_errors=0`

### Metrics (end)
- `backlog_analyzed0=1044` (delta: **-30**)
- `newly_analyzed_last60m=104`
- `newly_analyzed_last15m=19` (approx **76/hour**)
- `fact_checks=5392` (delta: **+233**)
- `synthesized_articles=899` (delta: **+30**)
- `analyst_requests=78`
- `mysql_disconnect_errors=12`
- `analyst_error_rate_pct=15.38`

### Reliability confirmation (recent log slice)
- Recent analyst log slice (`last 800 lines`):
  - `req=28`
  - `mysql_disconnect=4`
  - `error_rate_pct=14.29`
- Repeated error observed:
  - `2055: Lost connection to MySQL server at 'mariadb:3306'`

### Runbook gate evaluation
- ✅ Backlog trended down.
- ✅ Downstream continued progressing (`fact_checks`, `synthesized_articles`).
- ❌ Analyst reliability gate failed (`>3%` for sustained checks).
- ❌ Throughput target failed (well below `>=300/hour` target).

### Decision
- **Rollback Phase 1 tuning applied** per rollback matrix.

### Rollback actions applied
- `global.env`:
  - Disabled explicit MCP Phase 1 timeout/retry overrides.
  - Set `ANALYST_WORKERS=1`.
- `config/system_config.json`:
  - Reverted orchestrator to `polling_interval_seconds=10` and `max_concurrent_tasks=5`.

### Next action
- Restart services to apply rollback values.
- Run stabilization check window before any further phase advancement.

---

## Session: 2026-02-18 (Post-Rollback Stabilization Window #1)

### Observation setup
- Window length: 15 minutes (post-rollback)
- Runtime config start/end (`/status`):
  - `polling_interval_seconds=10`
  - `max_concurrent_tasks=5`
- Analyst worker setting confirmed on startup: `ANALYST_WORKERS=1`

### Metrics (start)
- `backlog_analyzed0=1030`
- `newly_analyzed_last60m=87`
- `newly_analyzed_last15m=19`
- `fact_checks=5505`
- `synthesized_articles=904`
- `analyst_requests=10`
- `mysql_disconnect_errors=0`

### Metrics (end)
- `backlog_analyzed0=1011` (delta: **-19**)
- `newly_analyzed_last60m=69`
- `newly_analyzed_last15m=18` (approx **72/hour**)
- `fact_checks=5674` (delta: **+169**)
- `synthesized_articles=922` (delta: **+18**)
- `analyst_requests=32`
- `mysql_disconnect_errors=6`
- `analyst_error_rate_pct=18.75`

### Reliability confirmation (recent slice)
- Recent analyst log slice (`last 600 lines`):
  - `req=27`
  - `mysql_disconnect=6`
  - `error_rate_pct=22.22`

### Gate evaluation
- ✅ Backlog continued to decrease.
- ✅ Downstream stages continued advancing.
- ❌ Reliability still failing badly (disconnect/error rate far above threshold).
- ❌ Throughput still below target.

### Decision
- Post-rollback stabilization is **not sufficient** to clear reliability gates.
- Continue with runbook escalation path: prioritize **Phase 3 (DB resilience in analyst path)** before any new throughput increases.

---

## Session: 2026-02-18 (Phase 3 Implementation)

### Scope
- Runbook section implemented: **Phase 3 — DB resilience in analyst path**
- Target file: `agents/analyst/tools.py`

### Changes applied
1. **Per-call cursor/connection handling in `analyze_article` path**
   - Replaced direct `db.mb_conn.cursor()` usage with compatibility-safe per-call acquisition:
     - `_acquire_cursor(..., per_call semantics via get_safe_cursor)`
     - `_close_cursor_conn(...)` with safe close behavior for non-shared connections.

2. **Transient DB retry wrapper for critical operations**
   - Added retry logic for MySQL transient disconnect classes:
     - error codes: `2006`, `2013`, `2055`
   - Applied to:
     - article fetch (`_fetch_article_row_with_retry`)
     - article update/commit (`_execute_update_with_retry`)
   - Backoff: incremental short sleep (`0.2s * attempt`), max 2 retries.

3. **Idempotence enforcement**
   - Before analysis, fetch now includes `analyzed` flag.
   - If `analyzed=1`, returns success no-op:
     - `{..., "no_op": true, "reason": "already analyzed"}`
   - Preserved update write shape for analyzed path:
     - `structured_metadata`
     - `factual_accuracy_score`
     - `fact_check_details`
     - `updated_at = NOW()`

4. **Structured metadata safety**
   - Added resilient JSON parse fallback for existing `structured_metadata`.

### Runtime activation
- Restarted stack (`stop_all_services.sh --skip-db` + `start_all_services.sh --skip-db --skip-migrations`).
- Analyst confirmed running with current baseline worker count (`ANALYST_WORKERS=1`).

### Verification evidence
1. **Idempotence no-op validation**
   - Call: `/analyze_article` on already analyzed article `2237`
   - Response: `status=200` with `no_op=true`, `reason="already analyzed"`.

2. **Normal analyzed-write path validation**
   - Call: `/analyze_article` on unanalyzed article `189`
   - Response: `status=200`, `analysis_result.status="success"`.
   - DB post-check for article `189`:
     - `analyzed=1`
     - `factual_accuracy_score=0.5`
     - `fact_check_details IS NOT NULL = 1`
     - `structured_metadata IS NOT NULL = 1`

### Decision
- **Phase 3 implementation complete and deployed.**
- Next step: run a new 15-minute observation window focused on MySQL disconnect/error rate reduction before any new throughput tuning.

---

## Session: 2026-02-18 (Phase 3 Validation Window #1)

### Observation setup
- Window length: 15 minutes
- Runtime config start/end (`/status`):
  - `polling_interval_seconds=10`
  - `max_concurrent_tasks=5`

### Metrics (start)
- `backlog_analyzed0=993`
- `newly_analyzed_last60m=76`
- `newly_analyzed_last15m=21`
- `fact_checks=5777`
- `synthesized_articles=934`
- `analyst_requests=7`
- `mysql_disconnect_errors=0`
- `analyst_error_rate_pct=0.00`

### Metrics (end)
- `backlog_analyzed0=963` (delta: **-30**)
- `newly_analyzed_last60m=76`
- `newly_analyzed_last15m=20` (approx **80/hour**)
- `fact_checks=5995` (delta: **+218**)
- `synthesized_articles=961` (delta: **+27**)
- `analyst_requests=37`
- `mysql_disconnect_errors=0`
- `analyst_error_rate_pct=0.00`

### Reliability confirmation (recent slice)
- Recent analyst log slice (`last 700 lines`):
  - `req=27`
  - `mysql_disconnect=0`
  - `error_rate_pct=0.00`

### Gate evaluation
- ✅ MySQL disconnect errors reduced to zero in observed window.
- ✅ Analyst reliability improved to 0% disconnect-derived error rate in-window and recent slice.
- ✅ Backlog continued to drain.
- ✅ Downstream progression remained healthy.

### Decision
- **Phase 3 accepted** (DB resilience fix effective).
- Next recommended step: re-enter **Phase 1 config-only throughput lift** cautiously (single increment + 15-minute gate) now that reliability baseline is stable.

---

## Session: 2026-02-18 (Retune #1 after Phase 3)

### Change applied
- Single controlled increment:
  - `orchestrator.polling_interval_seconds: 10 -> 8`
  - `max_concurrent_tasks` unchanged at `5`
  - `ANALYST_WORKERS` unchanged at `1`

### Runtime verification
- `/status` confirmed start/end config:
  - `polling_interval_seconds=8`
  - `max_concurrent_tasks=5`

### Metrics (start)
- `backlog_analyzed0=920`
- `newly_analyzed_last60m=79`
- `newly_analyzed_last15m=18`
- `fact_checks=6304`
- `synthesized_articles=992`
- `analyst_requests=4`
- `mysql_disconnect_errors=0`

### Metrics (end)
- `backlog_analyzed0=898` (delta: **-22**)
- `newly_analyzed_last60m=83`
- `newly_analyzed_last15m=21` (approx **84/hour**)
- `fact_checks=6440` (delta: **+136**)
- `synthesized_articles=1015` (delta: **+23**)
- `analyst_requests=26`
- `mysql_disconnect_errors=0`
- `analyst_error_rate_pct=0.00`

### Reliability confirmation (recent slice)
- `req=27`, `mysql_disconnect=0`, `error_rate_pct=0.00`

### Gate evaluation
- ✅ Reliability maintained (no disconnect regression).
- ✅ Backlog continued to drain.
- ✅ Downstream continued to advance.

### Decision
- **Retune #1 accepted and kept**.
- Next cautious step (optional): `max_concurrent_tasks 5 -> 6` with unchanged polling (`8`) and another 15-minute gate.

---

## Session: 2026-02-18 (Retune #2 after Phase 3)

### Change applied
- Single controlled increment:
  - `orchestrator.max_concurrent_tasks: 5 -> 6`
  - `polling_interval_seconds` unchanged at `8`
  - `ANALYST_WORKERS` unchanged at `1`

### Runtime verification
- `/status` confirmed start/end config:
  - `polling_interval_seconds=8`
  - `max_concurrent_tasks=6`

### Metrics (start)
- `backlog_analyzed0=888`
- `newly_analyzed_last60m=81`
- `newly_analyzed_last15m=24`
- `fact_checks=6486`
- `synthesized_articles=1018`
- `analyst_requests=4`
- `mysql_disconnect_errors=0`

### Metrics (end)
- `backlog_analyzed0=863` (delta: **-25**)
- `newly_analyzed_last60m=85`
- `newly_analyzed_last15m=22` (approx **88/hour**)
- `fact_checks=6642` (delta: **+156**)
- `synthesized_articles=1036` (delta: **+18**)
- `analyst_requests=29`
- `mysql_disconnect_errors=0`
- `analyst_error_rate_pct=0.00`

### Reliability confirmation (recent slice)
- `req=28`, `mysql_disconnect=0`, `error_rate_pct=0.00`

### Gate evaluation
- ✅ Reliability maintained (no disconnect regression).
- ✅ Backlog continued to drain.
- ✅ Downstream progression remained healthy.

### Decision
- **Retune #2 accepted and kept**.
- Next cautious step (optional): `max_concurrent_tasks 6 -> 7` with unchanged polling (`8`) and another 15-minute gate.

---

## Session: 2026-03-17 (Historical Review + Next Increment Plan)

### Why this checkpoint was revisited
- Current backlog drain remains below runbook target (`>= 300 analyzed/hour`) while reliability is stable.
- We reviewed prior remediation outcomes to avoid repeating failed high-risk jumps.

### Current live baseline (pre-increment)
- Runtime (`http://127.0.0.1:8023/status`):
  - `polling_interval_seconds=3`
  - `max_concurrent_tasks=8`
  - `gpu_util` observed low (single digits in status snapshots).
- Persisted config (`config/system_config.json`) currently shows `max_concurrent_tasks=20`, but runtime effective value is `8`.
  - Operational rule: treat runtime `/status` as source of truth for active tuning.
- Environment:
  - `ANALYST_WORKERS=2`

### Current checkpoint metrics (15-minute window)
- Window: `2026-03-17T23:14:48` → `2026-03-17T23:28:49`
- Samples: `14`
- Throughput:
  - `delta_analyzed=29`
  - `mean_analyzed_per_hour=123.06`
  - `median_analyzed_per_hour=111.56`
- Backlog:
  - `remaining_backlog=1576`
  - `eta_mean_hours=12.81`
- Reliability:
  - `analyst_requests_total=910`
  - `mysql_disconnect_total=0`
  - `disconnect_error_rate_pct=0.0`
  - `analyst_500_markers=0`

### Historical findings applied
1. Large jumps in Phase 1 raised instability (notably MySQL disconnect bursts) before DB resilience fixes.
2. Phase 3 (per-call DB handling + transient retry on `2006/2013/2055`) eliminated disconnect bursts in observed windows.
3. Post-Phase 3 improvements were achieved with single-step increments and strict 15-minute gates.

### Next increment plan (runbook-aligned)
#### Step A (execute first)
- Change only one hot knob:
  - `orchestrator.max_concurrent_tasks: 8 -> 9`
- Keep unchanged:
  - `polling_interval_seconds=3`
  - `ANALYST_WORKERS=2`

#### Step B (observe for 15 minutes)
- Required checks:
  - `backlog_analyzed0` trend down
  - `newly_analyzed_last60m` up materially
  - `mysql_disconnect_errors` remains `0`
  - no `HTTP 500` spike from analyst
  - downstream progression continues (`fact_checks`, synthesis/publish counters)

#### Keep criteria
- Reliability remains within runbook guardrails for the full window.
- Throughput improves versus pre-step baseline (`~123/hour` mean in this snapshot).

#### Rollback criteria (immediate)
- Any sustained disconnect/error burst (especially MySQL `2055`, or analyst 500 trend).
- Downstream policy advancement stalls for 15+ minutes.
- Resource saturation sustained beyond configured limits.

#### Rollback action
- Revert `orchestrator.max_concurrent_tasks: 9 -> 8`.

### Optional follow-on (only if Step A is stable)
- Consider `max_concurrent_tasks: 9 -> 10` with the same 15-minute gate.
- Defer any `ANALYST_WORKERS` increase until after at least one stable concurrency increment at current worker count.

---

## Session: 2026-03-17 (Step A Applied: `max_concurrent_tasks 8 -> 9`)

### Change applied
- Runtime hot patch via `/runtime-config`:
  - `orchestrator.max_concurrent_tasks: 8 -> 9`
- Validation response: `ok=true` (no warnings, no blocked keys).
- Apply response:
  - `version: 361 -> 362`
  - `owner_apply_result.applied` includes `orchestrator.max_concurrent_tasks=9`.

### Runtime verification
- `/status` immediately reflected:
  - `polling_interval_seconds=3`
  - `max_concurrent_tasks=9`
  - `runtime_config_version=362`

### 15-minute gate window
- Window:
  - `gate_start=2026-03-17T23:32:43`
  - `gate_end=2026-03-17T23:47:49`
  - `duration=15.09m`

### Metrics (pre -> post)
- Workflow:
  - `analyzed: 491 -> 526` (delta: `+35`)
  - `embedded: 2059 -> 2059` (no regression)
- Backlog:
  - `backlog_analyzed0: 1568 -> 1533` (delta: `-35`)
  - `newly_analyzed_last60m: 129 -> 130` (delta: `+1`)
- Downstream:
  - `fact_checks: 19865 -> 20037` (delta: `+172`)
  - `synthesized_articles: 312 -> 335` (delta: `+23`)

### Reliability (window deltas)
- `analyst requests: +68`
- `mysql_disconnect: +0`
- `analyst_500_markers: +0`
- `window_disconnect_error_rate_pct: 0.0`

### Sampler checkpoint (15-minute rolling)
- `samples=14`
- `delta_analyzed=30`
- `mean_analyzed_per_hour=129.72`
- `median_per_hour=113.63`
- `remaining_backlog=1537`

### Decision
- **KEEP Step A** (`max_concurrent_tasks=9`) based on:
  - zero reliability regressions,
  - continued backlog drain,
  - continued downstream advancement.

### Next cautious step
- Optional Step B: `max_concurrent_tasks: 9 -> 10` with unchanged polling/workers and another strict 15-minute gate.

---

## Session: 2026-03-17/18 (Step B Applied: `max_concurrent_tasks 9 -> 10`)

### Change applied
- Runtime hot patch via `/runtime-config`:
  - `orchestrator.max_concurrent_tasks: 9 -> 10`
- Validation response: `ok=true` (no warnings, no blocked keys).
- Apply response:
  - `version: 362 -> 363`
  - `owner_apply_result.applied` includes `orchestrator.max_concurrent_tasks=10`.

### Runtime verification
- `/status` reflected effective runtime config during gate:
  - `polling_interval_seconds=3`
  - `max_concurrent_tasks=10`
  - `runtime_config_version=363`

### 15-minute gate window
- Window:
  - `gate_start=2026-03-17T23:50:56`
  - `gate_end=2026-03-18T00:06:01`
  - `duration=15.09m`

### Metrics (pre -> post)
- Workflow:
  - `analyzed: 533 -> 566` (delta: `+33`)
  - `embedded: 2059 -> 2059` (no regression)
- Backlog:
  - `backlog_analyzed0: 1526 -> 1493` (delta: `-33`)
  - `newly_analyzed_last60m: 131 -> 132` (delta: `+1`)
- Downstream:
  - `fact_checks: 20064 -> 20252` (delta: `+188`)
  - `synthesized_articles: 341 -> 359` (delta: `+18`)

### Reliability (window deltas)
- `analyst requests: +64`
- `mysql_disconnect: +0`
- `analyst_500_markers: +0`
- `window_disconnect_error_rate_pct: 0.0`

### Sampler checkpoint (15-minute rolling)
- `samples=15`
- `delta_analyzed=32`
- `mean_analyzed_per_hour=136.05`
- `median_per_hour=114.15`
- `remaining_backlog=1493`

### Decision
- **KEEP Step B** (`max_concurrent_tasks=10`) based on:
  - zero reliability regressions,
  - continued backlog drain,
  - continued downstream progression.

### Next cautious step
- Hold current settings for one additional 15-minute checkpoint to confirm repeatability before any further increase.
- If repeatability holds, consider `max_concurrent_tasks: 10 -> 11` as next single-step increment.

---

## Session: 2026-03-18 (Step C Applied: analysis_to_fact_check lane rebalance)

### Why Step C
- Step A/B increased global orchestrator concurrency safely, but measured analyzed throughput remained below target.
- Live diagnosis showed explicit analysis-to-fact-check lane throttling remained conservative during backlog drain.

### Step C change set
- Updated env-backed policy controls in `global.env`:
  - `ORCH_POLICY_LIMIT_ANALYSIS_TO_FACT_CHECK: 3 -> 5`
  - `ORCH_POLICY_EXECUTION_PARALLELISM_ANALYSIS_TO_FACT_CHECK: 2 -> 3`
- Left unchanged:
  - `orchestrator.max_concurrent_tasks=10`
  - `orchestrator.polling_interval_seconds=3`

### Pre-change baseline
- Runtime control plane (`/runtime-config`):
  - `config_version=363`
  - hot overrides unchanged from Step B
- Workflow progress snapshot (pre-apply):
  - `Total Articles: 2059`
  - `Analyzed: 648`
  - `Embedded: 2059`
- Orchestrator telemetry snapshot (pre-apply):
  - `analysis_to_fact_check.last_limit=3`

### Apply method
- Step C keys are env-driven (not exposed as hot runtime-config keys), so change required orchestrator process reload.
- Performed targeted restart of `workflow_orchestrator` only:
  - updated `global.env`
  - stopped prior orchestrator process
  - relaunched orchestrator with `global.env` sourced
  - no full-stack recycle performed

### Post-apply verification
- Health:
  - `http://localhost:8023/health` => `ok`
- Process-level env verification (`/proc/<pid>/environ`):
  - `ORCH_POLICY_LIMIT_ANALYSIS_TO_FACT_CHECK=5`
  - `ORCH_POLICY_EXECUTION_PARALLELISM_ANALYSIS_TO_FACT_CHECK=3`
- Orchestrator status verification:
  - `running=True`
  - `analysis_to_fact_check.last_limit=5` (Step C effective)
  - `max_concurrent_tasks=10` (unchanged)
- Immediate post-apply progress snapshot:
  - `Total Articles: 2059`
  - `Analyzed: 655`
  - `Embedded: 2059`

### 15-minute gate plan (initiated)
- Gate objective:
  - increase analyzed drain by improving analysis-to-fact-check lane feed without reliability regression.
- Keep criteria:
  - analyzed throughput improves materially vs pre-Step C baseline window,
  - backlog slope remains clearly negative,
  - no sustained MySQL disconnect or analyst/fact-check 5xx burst.
- Rollback criteria:
  - no meaningful throughput gain after full gate,
  - reliability regression on analyst/fact-check/orchestrator policies.
- Rollback action:
  - revert env keys to `3` and `2`, restart `workflow_orchestrator`.

### Current decision state
- **Step C APPLY complete and verified active.**
- **Gate observation in progress** (full 15-minute decision checkpoint pending).

### 15-minute gate execution (completed)
- Window (from persisted checkpoint files):
  - `gate_start=2026-03-18T00:49:45Z`
  - `gate_end=2026-03-18T01:05:41Z`
  - `duration≈15.9m`

#### 5-minute checkpoints
- `T+5m`:
  - `analyzed=674`
  - `backlog_analyzed0=1385`
  - `newly_analyzed_last60m=132`
- `T+10m`:
  - `analyzed=685`
  - `backlog_analyzed0=1374`
  - `newly_analyzed_last60m=132`
- `T+15m` (final):
  - `analyzed=697`
  - `backlog_analyzed0=1362`
  - `newly_analyzed_last60m=131`

### Metrics (pre -> post)
- Workflow:
  - `analyzed: 664 -> 697` (delta: `+33`)
  - `embedded: 2059 -> 2059` (no regression)
- Backlog:
  - `backlog_analyzed0: 1395 -> 1362` (delta: `-33`)
  - implied analyzed rate in gate: `132/hour`
  - `newly_analyzed_last60m: 134 -> 131` (delta: `-3`)
- Downstream:
  - `fact_checks: 20711 -> 20884` (delta: `+173`)
- Policy telemetry (`analysis_to_fact_check`):
  - `last_limit: 5 -> 5` (Step C remained active)
  - `total_items_seen: 15 -> 55` (delta: `+40`)
  - `last_execute_ms: 23106.537 -> 21734.207`

### Reliability (window deltas)
- `analyst requests: +68`
- `mysql_disconnect: +0`
- `analyst_500_markers: +0`

### Gate evaluation
- ✅ Reliability gate passed (no disconnect burst, no 500 burst).
- ✅ Backlog continued to drain.
- ⚠️ Throughput improvement gate **not met** vs recent Step B reference windows (Step B ~`136/hour`; Step C gate observed `132/hour`).

### Decision
- **Step C stability: PASS**
- **Step C throughput uplift: NOT DEMONSTRATED**
- Operational disposition: keep current setting temporarily for stability, but do **not** treat Step C as a confirmed throughput win and do not stack further concurrency increases based on this gate alone.
- Conditional rollback note: if instability appears during subsequent tuning (for example MySQL disconnect growth, analyst/fact-check 5xx bursts, or sustained downstream stalls), rollback Step C lane settings to:
  - `ORCH_POLICY_LIMIT_ANALYSIS_TO_FACT_CHECK=3`
  - `ORCH_POLICY_EXECUTION_PARALLELISM_ANALYSIS_TO_FACT_CHECK=2`
  - then restart `workflow_orchestrator` and re-check `/status`.

### Next candidate change
- Preferred next experiment: increase analyst worker count with strict gating.
- Proposed step:
  - `ANALYST_WORKERS: 2 -> 3` (restart-required)
  - keep Step C unchanged during this test to isolate analyst capacity impact.
- Gate (15 minutes):
  - keep/rollback criteria unchanged from prior windows,
  - plus watch host memory pressure and per-request latency tails.

---

## Session: 2026-03-18 (Analyst Workers Gate: `2 -> 3`)

### Change applied
- Updated env in `global.env`:
  - `ANALYST_WORKERS: 2 -> 3`
- Restarted analyst service only (no orchestrator restart) to isolate analyst capacity impact.
- Kept Step C lane settings unchanged during this gate:
  - `ORCH_POLICY_LIMIT_ANALYSIS_TO_FACT_CHECK=5`
  - `ORCH_POLICY_EXECUTION_PARALLELISM_ANALYSIS_TO_FACT_CHECK=3`

### Post-change activation verification
- Analyst health endpoint: `ok`
- Analyst process args include `--workers 3`

### 15-minute gate execution (completed)
- Window (from persisted checkpoint files):
  - `gate_start=2026-03-18T01:14:40Z`
  - `gate_end=2026-03-18T01:31:21Z`
  - `duration=16.68m`

#### 5-minute checkpoints
- `T+5m`:
  - `analyzed=732`
  - `backlog_analyzed0=1327`
  - `newly_analyzed_last60m=130`
  - `fact_checks_total=21057`
- `T+10m`:
  - `analyzed=744`
  - `backlog_analyzed0=1315`
  - `newly_analyzed_last60m=132`
  - `fact_checks_total=21095`
- `T+15m` (final checkpoint):
  - `analyzed=754`
  - `backlog_analyzed0=1305`
  - `newly_analyzed_last60m=132`
  - `fact_checks_total=21138`

### Metrics (pre -> post)
- Workflow:
  - `analyzed: 716 -> 754` (delta: `+38`)
  - `embedded: 2059 -> 2059` (no regression)
- Backlog:
  - `backlog_analyzed0: 1343 -> 1305` (delta: `-38`)
  - implied analyzed rate in gate: `136.68/hour`
  - `newly_analyzed_last60m: 130 -> 132` (delta: `+2`)
- Downstream:
  - `fact_checks_total: 20987 -> 21138` (delta: `+151`)
- Policy telemetry (`analysis_to_fact_check`):
  - `last_limit: 5 -> 5` (Step C remained active)
  - `total_items_seen: 80 -> 125` (delta: `+45`)

### Reliability (window deltas)
- `analyst requests: +76`
- `mysql_disconnect: +0`
- `analyst_500_markers: +0`

### Resource notes
- `cpu: 8.7 -> 8.4`
- `memory: 71.4 -> 73.2` (small increase, no pressure event)
- `gpu_util: 4.0 -> 1.0` (still bursty, not sustained)

### Gate evaluation
- ✅ Reliability gate passed (no disconnect burst, no 500 burst).
- ✅ Backlog continued to drain.
- ✅ Throughput is at least on par with recent Step B reference and above Step C gate result (`136.68/hour` vs Step B ~`136/hour`, Step C `132/hour`).

### Decision
- **KEEP `ANALYST_WORKERS=3`** for subsequent windows.
- Keep Step C settings unchanged for now with previously documented conditional rollback if instability appears during future tuning.

---

## Session: 2026-03-18 (Analyst Workers Gate Confirmation #2)

### Purpose
- Run one additional 15-minute confirmation window at unchanged settings before any new tuning.
- Settings held constant during this window:
  - `ANALYST_WORKERS=3`
  - `ORCH_POLICY_LIMIT_ANALYSIS_TO_FACT_CHECK=5`
  - `ORCH_POLICY_EXECUTION_PARALLELISM_ANALYSIS_TO_FACT_CHECK=3`
  - `max_concurrent_tasks=10`, `polling_interval_seconds=3`

### 15-minute gate execution (completed)
- Window (from persisted checkpoint files):
  - `gate_start=2026-03-18T01:37:53Z`
  - `gate_end=2026-03-18T01:52:54Z`
  - `duration=15.02m`

#### 5-minute checkpoints
- `T+5m`:
  - `analyzed=780`
  - `backlog_analyzed0=1279`
  - `newly_analyzed_last60m=134`
  - `fact_checks_total=21257`
- `T+10m`:
  - `analyzed=790`
  - `backlog_analyzed0=1269`
  - `newly_analyzed_last60m=130`
  - `fact_checks_total=21314`
- `T+15m` (final checkpoint):
  - `analyzed=800`
  - `backlog_analyzed0=1259`
  - `newly_analyzed_last60m=130`
  - `fact_checks_total=21378`

### Metrics (pre -> post)
- Workflow:
  - `analyzed: 768 -> 800` (delta: `+32`)
  - `embedded: 2059 -> 2059` (no regression)
- Backlog:
  - `backlog_analyzed0: 1291 -> 1259` (delta: `-32`)
  - implied analyzed rate in gate: `127.85/hour`
  - `newly_analyzed_last60m: 131 -> 130` (delta: `-1`)
- Downstream:
  - `fact_checks_total: 21202 -> 21378` (delta: `+176`)
- Policy telemetry (`analysis_to_fact_check`):
  - `last_limit: 5 -> 5` (Step C remained active)
  - `total_items_seen: 145 -> 185` (delta: `+40`)
  - `last_execute_ms: 19071.363 -> 16854.347`

### Reliability (window deltas)
- `analyst requests: +64`
- `mysql_disconnect: +0`
- `analyst_500_markers: +0`

### Resource notes
- `cpu: 9.6 -> 9.8`
- `memory: 74.4 -> 77.6` (moderate increase, no observed pressure fault)
- `gpu_util: 99.0 -> 99.0` (bursty utilization persisted across the window)

### Gate evaluation
- ✅ Reliability gate passed (no disconnect burst, no 500 burst).
- ✅ Backlog and downstream continued to progress.
- ⚠️ Throughput was lower than the immediately prior AW3 gate (`127.85/hour` vs `136.68/hour`), indicating short-window variability.

### Decision
- **KEEP `ANALYST_WORKERS=3`** based on repeated reliability pass and continued backlog drain.
- Treat throughput gain as **provisionally positive but variable**; gather a longer observation window before any further concurrency increases.

---

## Session: 2026-03-18 (Analyst Workers Trial: `3 -> 4`)

### Change applied
- Updated env in `global.env`:
  - `ANALYST_WORKERS: 3 -> 4`
- Restarted analyst service only (orchestrator/policy unchanged).
- Verified analyst process args show `--workers 4` and analyst health returns `ok`.

### 15-minute gate execution (completed)
- Deterministic checkpoint sequence (baseline + three 5-minute checkpoints) executed successfully.
- Window (from checkpoint file mtimes):
  - `gate_start=2026-03-18T02:11:51Z`
  - `gate_end=2026-03-18T02:27:38Z`
  - `duration=15.78m`

#### 5-minute checkpoints
- `T+5m`:
  - `analyzed=851`
  - `backlog_analyzed0=1208`
  - `newly_analyzed_last60m=129`
  - `fact_checks_total=21648`
- `T+10m`:
  - `analyzed=861`
  - `backlog_analyzed0=1198`
  - `newly_analyzed_last60m=127`
  - `fact_checks_total=21691`
- `T+15m` (final checkpoint):
  - `analyzed=875`
  - `backlog_analyzed0=1184`
  - `newly_analyzed_last60m=129`
  - `fact_checks_total=21746`

### Metrics (pre -> post)
- Workflow:
  - `analyzed: 840 -> 875` (delta: `+35`)
  - `embedded: 2059 -> 2059` (no regression)
- Backlog:
  - `backlog_analyzed0: 1219 -> 1184` (delta: `-35`)
  - implied analyzed rate in gate: `133.09/hour`
  - `newly_analyzed_last60m: 129 -> 129` (delta: `0`)
- Downstream:
  - `fact_checks_total: 21587 -> 21746` (delta: `+159`)
- Policy telemetry (`analysis_to_fact_check`):
  - `last_limit: 5 -> 5` (Step C remained active)
  - `total_items_seen: 235 -> 275` (delta: `+40`)
  - `last_execute_ms: 20945.470 -> 20374.141`

### Reliability (window deltas)
- `analyst requests: +72`
- `mysql_disconnect: +0`
- `analyst_500_markers: +0`

### Resource notes
- `cpu: 9.6 -> 8.6`
- `memory: 72.2 -> 75.2` (increase without pressure/fault)
- `gpu_util: 99.0 -> 5.0` (bursty utilization persisted)

### Gate evaluation
- ✅ Reliability gate passed (no disconnect burst, no 500 burst).
- ✅ Backlog and downstream continued to progress.
- ⚠️ Throughput remained in the same band as recent AW3 windows and did not show a clear new uplift (`133.09/hour` vs AW3 windows `127.85-136.68/hour`).

### Decision
- **No clear sweet-spot uplift detected from `3 -> 4` in this 15-minute window.**
- Keep/revert call should be made with one longer confirmation window:
  - if stability remains and longer-window average improves, keep `ANALYST_WORKERS=4`;
  - otherwise revert to `ANALYST_WORKERS=3` and test a different lever.

---

## Session: 2026-03-18 (Polling Interval Lever: `3 -> 2`)

### Change applied
- Applied hot runtime-config patch via control plane (no restart required):
  - `orchestrator.polling_interval_seconds: 3 -> 2`
- Validation endpoint accepted patch before apply.
- Apply result:
  - `runtime_config_version: 363 -> 364`
  - `owner_apply_result` showed orchestrator config updated on next tick.

### 15-minute gate execution (completed)
- Window (from checkpoint files):
  - `gate_start=2026-03-18T02:33:02Z`
  - `gate_end=2026-03-18T02:48:29Z`
  - `duration=15.44m`

#### 5-minute checkpoints
- `T+5m`:
  - `analyzed=901`
  - `backlog_analyzed0=1158`
  - `newly_analyzed_last60m=133`
  - `fact_checks_total=21839`
- `T+10m`:
  - `analyzed=912`
  - `backlog_analyzed0=1147`
  - `newly_analyzed_last60m=132`
  - `fact_checks_total=21905`
- `T+15m` (final checkpoint):
  - `analyzed=924`
  - `backlog_analyzed0=1135`
  - `newly_analyzed_last60m=132`
  - `fact_checks_total=21948`

### Metrics (pre -> post)
- Workflow:
  - `analyzed: 888 -> 924` (delta: `+36`)
  - `embedded: 2059 -> 2059` (no regression)
- Backlog:
  - `backlog_analyzed0: 1171 -> 1135` (delta: `-36`)
  - implied analyzed rate in gate: `139.87/hour`
  - `newly_analyzed_last60m: 131 -> 132` (delta: `+1`)
- Downstream:
  - `fact_checks_total: 21791 -> 21948` (delta: `+157`)
- Policy/runtime telemetry:
  - `runtime_config_version: 364 -> 364`
  - `polling_interval_seconds: 2 -> 2` (stayed active through gate)
  - `max_concurrent_tasks: 10 -> 10`
  - `analysis_to_fact_check.last_limit: 5 -> 5`
  - `analysis_to_fact_check.total_items_seen: 295 -> 340` (delta: `+45`)

### Reliability (window deltas)
- `analyst requests: +70`
- `mysql_disconnect: +0`
- `analyst_500_markers: +0`

### Resource notes
- `cpu: 17.7 -> 8.5` (sampled values remained well below guardrails)
- `memory: 76.5 -> 76.7` (flat)
- `gpu_util: 87.0 -> 99.0` (bursty utilization)

### Gate evaluation
- ✅ Reliability gate passed (no disconnect burst, no 500 burst).
- ✅ Backlog and downstream continued to progress.
- ✅ Throughput moved to the top of the recent observed band (`139.87/hour` vs recent ~`127.85-136.68/hour`).

### Decision
- **KEEP polling interval at `2` for now** (`runtime_config_version=364`).
- Recommended next step: run one longer confirmation window at the current stack (`poll=2`, `max_concurrent_tasks=10`, Step C lane caps, `ANALYST_WORKERS=4`) before introducing another lever.
- Rollback path (if instability appears): runtime-config rollback to version `363` or patch `orchestrator.polling_interval_seconds` back to `3`.

---

## Session: 2026-03-18 (Modest Fact-Check Shaping Lever)

### Change applied
- Applied hot runtime-config patch to reduce per-item fact-check workload (modest, not conservative):
  - `fact_checker.search.max_queries: -> 6`
  - `fact_checker.search.deep_crawl_timeout_sec: -> 8.0`
- Control-plane apply result:
  - `runtime_config_version: 364 -> 365`

### 15-minute gate execution (completed)
- Window (from checkpoint files):
  - `gate_start=2026-03-18T02:58:54Z`
  - `gate_end=2026-03-18T03:14:19Z`
  - `duration=15.41m`

#### 5-minute checkpoints
- `T+5m`:
  - `analyzed=958`
  - `backlog_analyzed0=1101`
  - `newly_analyzed_last60m=134`
  - `fact_checks_total=22105`
- `T+10m`:
  - `analyzed=969`
  - `backlog_analyzed0=1090`
  - `newly_analyzed_last60m=133`
  - `fact_checks_total=22170`
- `T+15m` (final checkpoint):
  - `analyzed=980`
  - `backlog_analyzed0=1079`
  - `newly_analyzed_last60m=136`
  - `fact_checks_total=22237`

### Metrics (pre -> post)
- Workflow:
  - `analyzed: 948 -> 980` (delta: `+32`)
  - `embedded: 2059 -> 2059` (no regression)
- Backlog:
  - `backlog_analyzed0: 1111 -> 1079` (delta: `-32`)
  - implied analyzed rate in gate: `124.63/hour`
  - `newly_analyzed_last60m: 136 -> 136` (delta: `0`)
- Downstream:
  - `fact_checks_total: 22052 -> 22237` (delta: `+185`)
- Runtime/policy telemetry:
  - `runtime_config_version: 364 -> 365`
  - `polling_interval_seconds: 2 -> 2`
  - `max_concurrent_tasks: 10 -> 10`
  - `fact_checker.search.max_queries: 6 -> 6`
  - `fact_checker.search.deep_crawl_timeout_sec: 8.0 -> 8.0`
  - `analysis_to_fact_check.last_limit: 5 -> 5`
  - `analysis_to_fact_check.total_items_seen: 370 -> 410` (delta: `+40`)

### Reliability (window deltas)
- `analyst requests: +64`
- `mysql_disconnect: +0`
- `analyst_500_markers: +0`

### Gate evaluation
- ✅ Reliability gate passed (no disconnect burst, no 500 burst).
- ✅ Backlog and downstream progressed.
- ❌ Throughput regressed vs current best recent window (`124.63/hour` vs `139.87/hour` with poll=2 and no fact-check shaping patch).

### Decision and rollback
- **Do not keep this shaping patch at these values.**
- Rolled back runtime-config to pre-test version:
  - rollback target: `364`
  - resulting version: `366`
- Post-rollback verification:
  - `fact_checker.search.max_queries=None`
  - `fact_checker.search.deep_crawl_timeout_sec=None`
  - `orchestrator.polling_interval_seconds=2`
  - `orchestrator.max_concurrent_tasks=10`

---

## Session: 2026-03-18 (Modest MCP Fail-Fast Lever)

### Change applied
- Applied hot runtime-config patch to reduce MCP wait/retry tail latency:
  - `mcp_bus.call.read_timeout_sec: -> 12.0`
  - `mcp_bus.call.max_retries: -> 1`
- Control-plane apply result:
  - `runtime_config_version: 366 -> 367`

### 15-minute gate execution (completed)
- Window (from checkpoint files):
  - `gate_start=2026-03-18T03:17:41Z`
  - `gate_end=2026-03-18T03:33:08Z`
  - `duration=15.45m`

#### 5-minute checkpoints
- `T+5m`:
  - `analyzed=997`
  - `backlog_analyzed0=1062`
  - `newly_analyzed_last60m=135`
  - `fact_checks_total=22342`
- `T+10m`:
  - `analyzed=1008`
  - `backlog_analyzed0=1051`
  - `newly_analyzed_last60m=132`
  - `fact_checks_total=22406`
- `T+15m` (final checkpoint):
  - `analyzed=1020`
  - `backlog_analyzed0=1039`
  - `newly_analyzed_last60m=132`
  - `fact_checks_total=22470`

### Metrics (pre -> post)
- Workflow:
  - `analyzed: 987 -> 1020` (delta: `+33`)
  - `embedded: 2059 -> 2059` (no regression)
- Backlog:
  - `backlog_analyzed0: 1072 -> 1039` (delta: `-33`)
  - implied analyzed rate in gate: `128.15/hour`
  - `newly_analyzed_last60m: 135 -> 132` (delta: `-3`)
- Downstream:
  - `fact_checks_total: 22277 -> 22470` (delta: `+193`)
- Runtime/policy telemetry:
  - `runtime_config_version: 366 -> 367`
  - `polling_interval_seconds: 2 -> 2`
  - `max_concurrent_tasks: 10 -> 10`
  - `mcp_bus.call.read_timeout_sec: 12.0 -> 12.0`
  - `mcp_bus.call.max_retries: 1 -> 1`
  - `analysis_to_fact_check.last_limit: 5 -> 5`
  - `analysis_to_fact_check.total_items_seen: 415 -> 460` (delta: `+45`)

### Reliability (window deltas)
- `analyst requests: +64`
- `mysql_disconnect: +0`
- `analyst_500_markers: +0`

### Gate evaluation
- ✅ Reliability gate passed (no disconnect burst, no 500 burst).
- ✅ Backlog and downstream progressed.
- ❌ Throughput did not improve vs current best recent window (`128.15/hour` vs `139.87/hour` at poll=2 without MCP fail-fast patch).

### Decision and rollback
- **Do not keep this MCP fail-fast patch at these values.**
- Rolled back runtime-config to pre-test version:
  - rollback target: `366`
  - resulting version: `368`
- Post-rollback verification:
  - `mcp_bus.call.read_timeout_sec=None`
  - `mcp_bus.call.max_retries=None`
  - `orchestrator.polling_interval_seconds=2`
  - `orchestrator.max_concurrent_tasks=10`

