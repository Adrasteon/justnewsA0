# HITL Service (agents/hitl_service)

Short guide for the Human-in-the-Loop (HITL) annotator service used by the JustNews system.

Purpose

- Provides a FastAPI-based annotator UI and a small staging DB for candidate
review and programmatic labeling.

Run locally

- Start the service (development):

- Ensure dependencies are installed (see project `requirements.txt`).

- Run: `uvicorn agents.hitl_service.app:app --reload --host 127.0.0.1 --port 8040`

- The static annotator UI is served at `http://127.0.0.1:8040/`.Importantenvironmentvariables-`HITL_SERVICE_ADDRESS`:URLadvertisedtootherservices(default`http://127.0.0.1:8040`).

- `HITL_DB_PATH`: Path to the local SQLite staging DB (default`agents/hitl_service/hitl_staging.db`).

- `ENABLE_HITL_PIPELINE`: When`false` the crawler will not POST candidates to HITL.

- `HITL_STATS_INTERVAL_SECONDS`: Interval (seconds) for periodic stats polling/logging.

- `HITL_FAILURE_BACKOFF_SECONDS`: Backoff used by the crawler when POSTs to HITL fail.

- Forwarding knobs:

- `HITL_FORWARD_AGENT`/`HITL_FORWARD_TOOL` — configure to enable automatic
ingest-forwarding of labeled items via the MCP Bus.

DB notes

- The default staging DB is local and ignored by git. For production or shared
environments, set `HITL_DB_PATH` to an accessible location and ensure the service has write permissions.

Tests

- Unit and integration tests for the HITL service live under `tests/agents/`.

- Recommended CI: run `pytest -q` in the repo root (CI workflow added).

Troubleshooting

- 422 validation errors: ensure incoming candidate payloads match the
`CandidateEvent`schema (the`id` field is optional).

- If the crawler reports repeated submission failures, check `HITL_SERVICE_ADDRESS`
and `HITL_FAILURE_BACKOFF_SECONDS`.

Contact

- For operational questions, contact the engineering team maintaining the
JustNews HITL integration.

## HITL Service

Human-in-the-loop ingestion service that stores annotator decisions in SQLite and integrates with the shared MCP Bus for
ingest dispatch.

Run locally using your project Conda environment (recommended):

```bash
conda activate ${CANONICAL_ENV:-justnews-py312}

## install minimal runtime deps (conda-first, fallback to pip if needed)

conda install -c conda-forge fastapi uvicorn

## if a package is unavailable via conda, use pip inside the activated env:

pip install -r agents/hitl_service/requirements.txt

## run the service from the repository root (use an unused port; 8040 is open)

uvicorn agents.hitl_service.app:app --reload --port 8040

```

Open the annotator UI at <http://localhost:8040/static/index.html>

Notes:

- Set `MCP_BUS_URL`if the bus is not running on`http://localhost:8000`.-Override`HITL_AGENT_NAME`/`HITL_SERVICE_ADDRESS`whendeployingbehindnon-localhostaddresses.-Use`HITL_FORWARD_AGENT`/`HITL_FORWARD_TOOL`todefinethedownstreamagent+toolthatshouldreceiveingestjobs.ThetargettoolmustacceptaJSONpayloadshapedlike`ingest_payload`from`/api/label`.-Use`HITL_CANDIDATE_FORWARD_AGENT`/`HITL_CANDIDATE_FORWARD_TOOL`ifcandidatesshouldalsobeechoedtoanotherconsumerimmediatelyaftercreation.-Provide`HITL_PRIORITY_SITES`asacomma-separatedlisttoboostqueuepriorityforhigh-valuesources.-Set`HITL_DB_PATH`tochangetheSQLitedatabaselocation;defaultsto`agents/hitl_service/hitl_staging.db`.-AnnotatorsmustsupplytheirIDintheUI;itiscachedlocallyinthebrowserforconvenience.-QAreviewerscanresolvesamplesvia`POST/api/qa/review`witha`pass`/`fail`statustodraintheQAqueue.-Enabletraining-forwarddispatchbyexporting`HITL_TRAINING_FORWARD_AGENT=training_system`and`HITL_TRAINING_FORWARD_TOOL=receive_hitl_label`;monitor`hitl_training_forward_success_total`togetherwiththetrainingsystemcounter`justnews_training_examples_total{example_type="hitl_label"}`toconfirmend-to-endflow.
