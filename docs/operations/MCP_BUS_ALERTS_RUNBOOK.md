# MCP Bus Alerts Runbook

This runbook provides step-by-step guidance for responding to MCP Bus alerts (MCPBusOverallDegraded,
MCPBusAgentUnreachable, MCPBusAgentDegraded).

## Overview

Alerts covered:

- MCPBusOverallDegraded (severity: warning) — the MCP Bus overall health metric is not 'healthy' for >2m.

- MCPBusAgentUnreachable (severity: critical) — one or more agents reported 'unreachable' for >2m.

- MCPBusAgentDegraded (severity: warning) — one or more agents reported 'degraded' for >5m.

Purpose: Provide quick diagnostic commands and remediation steps for on-call operators.

---

## Immediate triage (first 5 minutes)

1. Fetch the MCP Bus `/health` payload for details:

```bash
curl -s <http://localhost:8017/health> | jq

```bash

1. Inspect the `agent_details`list and`issues` field to see which agents are affected and whether the circuit breaker is
   involved.

1. If a particular agent is listed as `unreachable`or`unhealthy`, query that agent directly:

```bash

## Example for 'synthesizer'

curl -s <http://localhost:8005/health> | jq

```

1. Check logs for the MCP Bus and the affected agent(s):

```bash
sudo journalctl -u justnews-mcp-bus -n 200 --no-pager
sudo journalctl -u justnews@<agent_name> -n 200 --no-pager

```bash

Look for errors such as connection refused, DB errors, or repeated stack traces.

1. Check circuit breaker state for agents via the MCP Bus API:

```bash
curl -s <http://localhost:8017/circuit_breaker_status> | jq

```

If the circuit breaker is open for the agent, note the `open_until` timestamp.

---

## Remediation steps

If an agent is unreachable/unhealthy:

1. Verify the systemd service is active and restart if needed:

```bash
sudo systemctl status justnews@<agent_name>
sudo systemctl restart justnews@<agent_name>

```

1. If restarting fails, check the agent's logs and system resources (disk, memory):

```bash
sudo journalctl -u justnews@<agent_name> -n 500
free -h; df -h

```bash

1. If the agent depends on database or redis and those services are failing, escalate to database team and check
   `systemctl status mariadb redis`.

1. If the problem is sustained OOM on GPU-driven agents (e.g., vLLM-related), check GPU monitoring logs:
   `run/gpu_monitor.log`and consider stopping heavy workloads or restarting the`vllm` systemd unit.

---

## Post-incident

1. Add a short incident note to the operations ticket including: alert name, time, affected agents, remediation steps
   taken, and follow-up actions.

1. If repeat occurrences happen, file a bug with logs, steps to reproduce, and a mitigation plan (e.g., increase
   MemoryLimit on systemd units, add more aggressive circuit breaker thresholds, or tune vLLM memory settings).

---

## Who to escalate to

- On-call backend engineer: ops@example.com

- GPU/infra team: gpu-team@example.com

- Database team: db-team@example.com

---

## Useful commands

- `curl -s <http://localhost:8017/health> | jq`  # MCP Bus composite health

- `curl -s <http://localhost:8005/health> | jq`  # Agent health

- `sudo journalctl -u justnews-mcp-bus -f`  # MCP Bus live logs

- `sudo journalctl -u justnews@<agent> -f`  # Agent live logs

- `systemctl status justnews@<agent>`

- `cat /etc/justnews/global.env`  # Verify env toggles

- `grep -i "circuit breaker" logs`  # Search for CB activity

---

If you'd like, I can also wire an example Alertmanager webhook receiver for on-call paging (PagerDuty/Slack) and provide
a playbook example for on-call rotations.
