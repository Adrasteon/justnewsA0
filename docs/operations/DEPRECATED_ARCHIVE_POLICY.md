---
title: Deprecated Script Archive Policy
description: Policy for archiving obsolete or experimental scripts outside active runtime paths
---

# Deprecated Script Archive Policy

This repository keeps active runtime paths focused on required functional code.

## Local archive location

Deprecated or experimental scripts that should not remain in active paths are moved to:

- `archive_local/deprecated-scripts/`

`archive_local/` is gitignored and intended for local retention/reference only.

## What gets archived

- Deprecated scripts with unconditional early exit followed by large dead code bodies
- Legacy deployment paths no longer supported (e.g., retired Kubernetes/Helm generators)
- Old one-off experimental utilities superseded by canonical workflows

## Compatibility stubs in active paths

When a historical path may still be invoked by users, tests, or external automation, keep a minimal compatibility stub in place that:

1. Prints a clear deprecation/retirement message
2. Points to the archived copy path
3. Exits safely (`exit 0` for no-op compatibility, `exit 1` for invalid operation)

## Current archived examples

- `infrastructure/kubernetes/generate-agent-manifests.sh`
- `infrastructure/docker/generate-agent-dockerfiles.sh`
- `infrastructure/helm/justnews/deploy-single-node.sh`
- `scripts/deploy/setup_postgres.sh`

Archived copies are under `archive_local/deprecated-scripts/` preserving original relative structure.
