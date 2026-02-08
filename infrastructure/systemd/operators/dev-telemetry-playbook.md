# Operator Playbook — Dev Telemetry (Loki / Tempo / OTel node)

This playbook explains how operators can safely enable, verify, and manage the `dev` telemetry stack across
developer/test hosts. The goal is to make it easy to enable the telemetry stack on many hosts in a repeatable and
reversible way without affecting production systems.

Important: the dev telemetry stack is intended for developer/test machines and not for production environments. It is
opt-in only.

Prerequisites

- A machine with: Docker (>=20.10), docker compose plugin, and systemd

- Repository cloned / available on host (recommended path: /home/adra/JustNews)

- The demo telemetry compose file: `infrastructure/monitoring/dev-docker-compose.yaml`

Important: this dev telemetry stack uses the canonical OTLP / telemetry ports (4317/4318/8889 for the node collector;
3100 for Loki; 14268/9411 for Tempo; 8080 for the demo emitter). We intentionally keep these canonical ports so the
stack integrates cleanly with agent-local tracing and metrics when running on development hosts.

Port conflicts on developer machines are expected if an existing OpenTelemetry collector or other telemetry process is
already active. To avoid surprising failures the canonical startup checks for port conflicts and will skip starting the
repo's dev telemetry stack if any canonical ports are already bound on the host. This prevents noisy docker-compose bind
errors.

If you are sure you want to bring up the dev telemetry stack on a host where those ports are already in use, you can
either force startup (risky) or use an alternate set of default dev ports:

- Temporarily stop the conflicting host process (recommended)

- Example: stop a local OTLP collector systemd unit before starting the dev stack.

- Force the repo dev telemetry stack to start despite conflicts by setting an environment variable in your runtime
  environment (explicit opt-in):

  - ENABLE_DEV_TELEMETRY_FORCE=1 ENABLE_DEV_TELEMETRY=true /path/to/infrastructure/systemd/scripts/dev-telemetry-
    manager.sh up

Or to avoid conflict we provide alternate default host ports for the dev stack that don't collide with system
collectors. The dev compose maps container ports to alternate host ports by default; you can override any host port
individually using environment variables when launching:

```bash
  # Start the dev stack using the alternate dev ports (default behaviour)
ENABLE_DEV_TELEMETRY=true /path/to/infrastructure/systemd/scripts/dev-telemetry-
manager.sh up

  # Start the dev stack using canonical ports by overriding environment variables
LOKI_PORT=3100 OTEL_GRPC_PORT=4317 OTEL_HTTP_PORT=4318 NODE_METRICS_PORT=8889 \
ENABLE_DEV_TELEMETRY=true /path/to/infrastructure/systemd/scripts/dev-telemetry-
manager.sh up ```

When in doubt prefer stopping or reconfiguring the host collector to avoid port
collisions; keeping the canonical ports ensures your agents and dev
instrumentation match production behaviour.

- If using systemd-managed mode, the install helper script requires sudo privileges

Top-level goals

- Make enabling/disabling the dev telemetry stack trivial on many hosts

- Provide verification steps operators can use to confirm telemetry is functioning

- Keep the canonical startup behavior intact and opt-in (via `ENABLE_DEV_TELEMETRY=true`)

Step 1 — Quick, manual enable (single host)

1. Ensure the repo and compose file are present on the host. If not present, clone/pull to a known path (recommended: $HOME/JustNews).

1. Set the opt-in environment variable in `/etc/justnews/global.env` (create if missing):

```ini
ENABLE_DEV_TELEMETRY=true

```bash

1. Option A: Use canonical startup script

```bash
sudo ./infrastructure/systemd/canonical_system_startup.sh

```bash

The canonical script will check `ENABLE_DEV_TELEMETRY` and attempt to start the
repo's `dev-docker-compose.yaml` via docker compose.

1. Option B: Use systemd-managed unit

```bash
sudo ./infrastructure/systemd/scripts/install_dev_telemetry_unit.sh sudo systemctl enable --now justnews-dev-
telemetry.service

```bash

This installs and starts a systemd unit that runs the repository compose file.
Use `systemctl status justnews-dev-telemetry.service` to inspect state.

Step 2 — Verify the telemetry stack

- Verify containers are running with `docker ps`:

```bash
docker ps --filter "name=justnews-" --format "{{.Names}}: {{.Status}}"

```

- Check the demo emitter probe which the compose demo service exposes on port 8080:

```bash
curl -sSf <http://localhost:8080/>

## expected: HTTP 200 with body 'OK'

```bash

- Check collector health endpoints (if available):

```bash
curl -sSf <http://localhost:8889/metrics> | head -n 5

```

- Inspect Loki UI (http://localhost:3100) and Tempo / Jaeger endpoints (local dev ports 9411 / 14268) if running.

Step 3 — Tearing down / Disabled mode

Option A — canonical shutdown path (recommended):

```bash
sudo ./infrastructure/systemd/canonical_system_startup.sh stop

```bash

Option B — systemd unit stop:

```bash
sudo systemctl stop justnews-dev-telemetry.service

```bash

Option C — docker compose down (workdir must match compose file path):

```bash
docker compose -f infrastructure/monitoring/dev-docker-compose.yaml down

```

Step 4 — Safe rollback and cleanup

- If using systemd unit file and you want to remove it:

```bash
sudo systemctl disable --now justnews-dev-telemetry.service sudo rm /etc/systemd/system/justnews-dev-telemetry.service
sudo systemctl daemon-reload

```

- If you added `ENABLE_DEV_TELEMETRY=true` to `/etc/justnews/global.env` and want to revert change, remove the entry and ensure you called the canonical stop path.

Automation (Ansible) -------------------- We provide a reference Ansible
playbook under `infrastructure/ansible/playbooks/enable_dev_telemetry.yml` which
performs the following on a host:

- Ensures docker & docker compose plugin are installed

- Copies a configured `global.env` fragment (enables the opt-in variable)

- Optionally installs the `justnews-dev-telemetry.service` systemd unit

- Starts the unit and verifies the demo emitter endpoint

See the `infrastructure/ansible/playbooks/enable_dev_telemetry.yml` for an
example and customise it to your infrastructure's package manager, user layout,
and secrets handling.

Troubleshooting ---------------

- If compose fails to start, `docker compose -f infrastructure/monitoring/dev-docker-compose.yaml logs` is the first debug step.

- Use `docker logs justnews-demo-emitter` to troubleshoot the demo emitter.

- Confirm `/etc/justnews/global.env` is readable by the startup scripts and contains `ENABLE_DEV_TELEMETRY=true`.

- If systemd unit fails, examine `journalctl -u justnews-dev-telemetry.service` and `systemctl status` for the underlying error.

Security and operational notes ------------------------------

- Don't enable this on production hosts — it's intended for development/testing.

- Make sure any ports exposed are protected by host firewall rules if running on a shared network.

- For multi-host deployments prefer running telemetry backends in a dedicated monitoring cluster rather than on dev hosts.
