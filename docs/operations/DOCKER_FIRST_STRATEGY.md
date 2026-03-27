---
title: Docker-First Runtime Strategy
description: Near-term Docker canonical runtime, systemd role reduction, and Kubernetes migration runway
---

# Docker-First Runtime Strategy

Decision
- JustNews runtime is moving to Docker-first for near-term production/dev operations.
- systemd remains optional for host-level wrappers and legacy compatibility during transition.

Why
- Align runtime with current operational reality and reduce split-brain deployment modes.
- Improve portability and simplify eventual Kubernetes migration.

Current policy
- Canonical app runtime: Docker Compose managed services.
- systemd app orchestration: legacy compatibility path (not preferred).
- systemd host wrappers: allowed for bootstrapping host-level processes if needed.

Transition phases

Phase 1 (now)
- Add Docker lifecycle scripts/Make targets.
- Route development deploy target to Docker path.
- Keep systemd targets available but not preferred.

Phase 2
- Harden compose healthchecks/restart/dependency behavior to match or exceed current systemd reliability.
- Normalize env/secrets strategy for container runtime.

Phase 3
- Add Kubernetes readiness contracts and migration scaffolding.
- Use Docker runtime contracts as migration baseline.

Guardrails
- Retired legacy root scripts must fail non-zero and point to archive_local.
- Canonical environment checks remain active.
- Changes should be reversible during transition.

Operational note
- During transition, avoid introducing new systemd-first app orchestration dependencies.
- Prefer docker lifecycle entrypoints and compose-native health semantics.
