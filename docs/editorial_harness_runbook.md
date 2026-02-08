# Editorial Harness Runbook

This runbook explains how to operate the Stage 4 editorial harness that runs normalized articles through the journalist
→ fact_checker → synthesizer adapters, persists results back into MariaDB, and emits Stage B acceptance metrics.

## Prerequisites

- MariaDB + Chroma stack available with the migrated schema.

- `MODEL_STORE_DRY_RUN=1` (or the adapters fully provisioned) so the harness can execute without loading heavy weights
  in CI.

- Prometheus scraping the Stage B metrics endpoint so the counters in `common/stage_b_metrics.py` are exported.

## Running locally

Initialize a fresh MariaDB schema (when using docker-compose or CI):

```bash
python scripts/dev/bootstrap_editorial_harness_db.py

```

```bash
MODEL_STORE_DRY_RUN=1 FACT_CHECKER_DISABLE_QWEN=0 \
    python scripts/dev/run_agent_chain_harness.py --limit 3

```

Useful flags:

- `--article-id 123 --article-id 456` — limit the run to specific rows.

- `--no-artifacts`— skip writing`output/agent_chain_runs/<id>.json` (useful in CI).

- `--artifact-dir /tmp/harness` — override the artifact root.

The script invokes `AgentChainRunner`, which:

1. Uses `NormalizedArticleRepository` to select unsynthesized articles with ≥400 characters of content.

1. Runs `AgentChainHarness` to generate story briefs, fact checks, and drafts.

1. Saves traces (`fact_check_trace`,`synth_trace`,`critic_result`) plus updated`fact_check_status`/`is_synthesized`flags
   back into the`articles` table.

1. Records metrics (`justnews_stage_b_editorial_harness_total`,`justnews_stage_b_editorial_acceptance_*`).

## Scheduling options

### Cron (on the crawler host)

Create `/etc/cron.d/justnews-editorial-harness`:

```

## Run every 15 minutes against the latest normalized rows

*/15 * * * * justnews MODEL_STORE_DRY_RUN=1 \
  /srv/justnews/scripts/run_agent_chain_harness.py --limit 10 --no-artifacts >> /var/log/justnews/editorial_harness.log 2>&1

```

### GitHub Actions (nightly dry-run)

```yaml
name: stage4-editorial-harness
on:
  schedule:

    - cron: '0 7 * * *'
jobs:
  harness:
    runs-on: ubuntu-latest
    steps:

      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install deps
        run: pip install -r requirements.txt

      - name: Run harness
        env:
          MODEL_STORE_DRY_RUN: "1"
          FACT_CHECKER_DISABLE_QWEN: "0"
        run: python scripts/dev/run_agent_chain_harness.py --limit 5 --no-artifacts

```

(The workflow above expects database credentials provided through repository secrets or a self-hosted runner with tunnel
access.)

## Dashboards & alerts

- Follow `docs/grafana/editorial-harness-wiring.md`to expose the Stage 4 metrics, copy the provisioning files, and
  import`docs/grafana/editorial-harness-dashboard.json`.

- Panels cover accepted vs follow-up vs error rates, rolling acceptance ratio, score distribution, and 24 h harness
  volume.

- Add alerts on:

- `justnews_stage_b_editorial_harness_total{result="error"}` > 0 for 3 consecutive runs.

- Acceptance ratio < 0.6 for 15 m.

## Operational checklist

1. Ensure the cron or workflow output is posted to #live-run with the JSON summary from the script.

1. Investigate any `needs_followup`clusters by reviewing the artifact JSON (if enabled) or the`fact_check_trace` column.

1. Before promoting drafts to Stage 5 (publishing), confirm the Grafana dashboard shows green status for the latest
   window.
