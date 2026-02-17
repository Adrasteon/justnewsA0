# Fact Checker Troubleshooting (DevContainer + Docker Backend)

## Scope

This runbook documents the recurring failure mode where:

- `fact_checker` shim (`:8018`) starts but `/health` or `/fact_check` fails
- MCP bus returns `Circuit breaker open for agent fact_checker`
- Docker Desktop reports backend healthy on host port `:8003`

It also captures the fixes applied during the Feb 15, 2026 incident.

---

## Symptoms

- `GET http://localhost:8018/health` returns `500`
- `POST http://localhost:8018/fact_check` returns `502` or auth errors
- `POST http://localhost:8000/call` for `fact_checker` returns `400` with circuit breaker open
- `GET http://localhost:8018/fact_check` returns `405` (this one is expected; endpoint is POST-only)

---

## Root Causes Observed

### 1) Wrong upstream URL from inside devcontainer

Inside the devcontainer, `localhost` is the container itself, not the Docker Desktop host.

- Failing setting:
  - `FACT_CHECKER_EXTERNAL_URL=http://localhost:8003`
- Working setting in this environment:
  - `FACT_CHECKER_EXTERNAL_URL=http://fact-checker:8000`

### 2) Missing API key for backend authentication

Backend responded with `401 Unauthorized` until key was provided.

- Required env:
  - `FACT_CHECKER_API_KEY=dev_key_123` (dev default in current compose)

### 3) Shim circuit-breaker time source bug impacting `/health`

`/health` could error due to event-loop-dependent timing in a sync path.

- Fixed in `agents/fact_checker/shim.py` by using `time.monotonic()` for breaker timing.

### 4) `verify_article` failed due to articles schema mismatch (`url` vs `source_url`)

Workflow policy `summary_to_fact_check` calls `fact_checker.verify_article` with `article_id`.
In this environment, `articles` stores source links in `source_url` (not `url`).

- Failure mode:
  - shim returned `503` with `{"detail":"Unable to load article <id>"}`
  - MCP bus retried then opened breaker for `fact_checker`
  - workflow logs showed repeated `400`/`502` and `Success: 0/5`

- Fix applied:
  - In `agents/fact_checker/shim.py`, article loader query changed to:
    - `SELECT ..., source_url AS url, ... FROM articles WHERE id = %s`

- Post-fix expected state:
  - `POST /call` with `fact_checker.verify_article` returns `200`
  - MCP breaker for `fact_checker` stays closed
  - workflow logs show `Fact check batch complete. Success: 5/5`

---

## Canonical DevContainer Configuration

In `global.env`:

```bash
FACT_CHECKER_AGENT_PORT=8018
FACT_CHECKER_EXTERNAL_URL=http://fact-checker:8000
FACT_CHECKER_API_KEY=dev_key_123
```

---

## Verification Sequence

Run in `/app` after startup stabilizes:

```bash
# Backend reachability from container
curl -sS -o /tmp/fc_dns.json -w '%{http_code}\n' http://fact-checker:8000/health

# Shim health
curl -sS -o /tmp/fc_shim_h.json -w '%{http_code}\n' http://localhost:8018/health

# Direct shim fact-check
curl -sS -o /tmp/fc_shim_post.json -w '%{http_code}\n' \
  -X POST http://localhost:8018/fact_check \
  -H 'Content-Type: application/json' \
  -d '{"fact":"The sky is blue.","context":"General knowledge"}'

# MCP path
curl -sS -o /tmp/fc_mcp.json -w '%{http_code}\n' \
  -X POST http://localhost:8000/call \
  -H 'Content-Type: application/json' \
  -d '{"agent":"fact_checker","tool":"fact_check","kwargs":{"fact":"The sky is blue."}}'
```

Expected:

- backend health `200`
- shim health `200`
- shim fact_check `200`
- MCP fact_checker call `200`

---

## If MCP Still Says "Circuit breaker open"

The bus breaker can stay open briefly after failures.

1. Confirm shim direct POST is already `200`
2. Wait cooldown window and retry MCP call
3. Inspect breaker status:

```bash
curl -sS http://localhost:8000/circuit_breaker_status
```

---

## Resource Pressure Notes

During startup, high memory pressure/model load can delay readiness and produce transient errors.

Recommended:

- Re-run probes after startup settles
- Check memory/CPU snapshot:

```bash
free -h
ps -eo pid,pmem,pcpu,cmd --sort=-pmem | head -n 12
```

Transient startup delays should not persist once the system is idle. Persistent `401/502` indicates config/auth/network path issues (not just load).
