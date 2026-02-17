# systemd-nspawn dev helper for JustNews

**TODO: This workflow is currently disabled due to setup complexity and time requirements. It needs to be revisited and
simplified before being re-enabled.**

This project contains an optional developer helper to spin up a systemd-based local container using systemd-nspawn. It
is intentionally opt-in for developers who need to test system-level behaviors (service units, init ordering, realistic
systemd semantics) that are difficult to reproduce with in-memory emulators.

Important: this is not a required workflow for most development — your existing fast, in-memory tests remain the
recommended default. The systemd-nspawn workflow is useful for deeper debugging and reproducing systemd-specific issues.

## Current Status

The systemd-nspawn test infrastructure has proven to be awkward and time- consuming to set up reliably, particularly
around:

- DNS resolution inside containers

- Network veth configuration and host NAT setup

- Cross-distribution compatibility (debootstrap suite versions)

- iptables/firewall rule coordination

This needs further work to become a robust, reproducible developer and CI workflow. For now, prefer using Docker or
other container solutions for E2E testing with real services — note that the docker-compose PoC is intended for
lightweight testing and CI only. In typical developer and production setups MariaDB is expected to run on the host
(outside Docker) or as a managed DB service.

## Where the helper lives

scripts/dev/run_systemd_nspawn_env.sh

## Prerequisites

- Linux host with systemd

- `systemd-nspawn`/`machinectl` available (provides systemd-nspawn on most systemd-enabled systems)

- `debootstrap` (used to bootstrap the container filesystem). Install on Debian/Ubuntu hosts with:

sudo apt-get update && sudo apt-get install -y debootstrap

Note: You will typically need to run the script as root (sudo) since it manipulates systemd machines and filesystem
under `/var/lib/machines`.

## Quick workflow

1. Create a fresh container filesystem (only the first time):

sudo scripts/dev/run_systemd_nspawn_env.sh create

1. Start the container (boots systemd inside):

sudo scripts/dev/run_systemd_nspawn_env.sh start

1. Install services (mariadb, redis):

sudo scripts/dev/run_systemd_nspawn_env.sh install

1. Open an interactive shell in the container:

sudo scripts/dev/run_systemd_nspawn_env.sh shell

1. Stop or destroy when done:

sudo scripts/dev/run_systemd_nspawn_env.sh stop sudo scripts/dev/run_systemd_nspawn_env.sh destroy

## Notes & tips

- Exposing ports to host: the helper does not automatically forward ports. Use `machinectl shell <container>`to work
  inside the container, or configure`systemd-nspawn`with networking options or use`lxc`/LXD if you prefer bridged
  networking.

- Containers created with systemd-nspawn rely on the host kernel — they are lightweight and fast to start but don't give
  hypervisor-level isolation.

- This workflow is useful for reproducing systemd-service unit issues, DB service start ordering, or interactions
  between system units.
If you want me to extend this script to provide automatic port forward rules (e.g., expose 3306 and 6379 on localhost)
or to include an automated test-runner that executes the test suite inside the container, I can add that next.

Note: because the systemd-nspawn flow is disabled for now, a Docker-based proof- of-concept is provided to run a
lightweight E2E suite using Docker Compose for testing and CI only. See `scripts/dev/docker-compose.e2e.yml`,
`scripts/dev/run_e2e_docker.sh`and`.github/workflows/e2e-docker.yml` for details; for normal local development and
production the project expects the canonical MariaDB to run on the host or as a managed service.
