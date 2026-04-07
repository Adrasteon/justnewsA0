#!/usr/bin/env python3
"""Guard against contradictory runtime messaging in Docker-canonical active paths.

Fails if active canonical files or selected active operator docs contain phrases
that imply Docker is deprecated or that systemd is the canonical runtime pathway.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FILE_CHECKS: dict[str, tuple[str, ...]] = {
    "infrastructure/docker/docker-compose.canonical.yml": (
        r"docker\s+compose\s+is\s+deprecated",
        r"use\s+systemd",
    ),
    "start_all_services.sh": (
        r"JUSTNEWS_ENABLE_LEGACY_START_STOP",
        r"legacy\s+start_services_daemon\.sh\s+path",
    ),
    "stop_all_services.sh": (
        r"JUSTNEWS_ENABLE_LEGACY_START_STOP",
        r"legacy\s+stop_services\.sh\s+path",
    ),
    "infrastructure/scripts/validate-deployment.sh": (
        r"legacy\s+compatibility\s+toggle",
    ),
    "scripts/ops/docker_first_migration_check.sh": (
        r"legacy\s+transition\s+toggle",
        r"JUSTNEWS_ENABLE_LEGACY_START_STOP",
    ),
}

# Intentionally scoped to active operator docs only.
#
# Why this scope is narrow:
# - inventory artifacts (e.g., *_inventory.json) preserve historical references
# - changelogs/migration notes may intentionally mention legacy pathways
# - archive/deprecated docs are historical records, not active operator guidance
#
# CI enforcement here is meant to keep *current canonical runbooks* clean and
# unambiguous, without rewriting history in reference artifacts.
DOC_CHECKS: dict[str, tuple[str, ...]] = {
    "START_STOP_SERVICES.md": (
        r"JUSTNEWS_ENABLE_LEGACY_START_STOP",
        r"legacy\s+toggle",
    ),
    "START_STOP_QUICK_REFERENCE.md": (
        r"JUSTNEWS_ENABLE_LEGACY_START_STOP",
        r"legacy\s+toggle",
    ),
    "docs/operations/DOCKER_CANONICAL_COMMANDS.md": (
        r"JUSTNEWS_ENABLE_LEGACY_START_STOP",
        r"docker\s+compose\s+is\s+deprecated",
        r"systemd-first",
        r"primary\s+production\s+path",
    ),
    "docs/operations/STARTUP_CHECKLIST.md": (
        r"JUSTNEWS_ENABLE_LEGACY_START_STOP",
        r"systemd-first",
        r"primary\s+production\s+path",
    ),
    "docs/operations/DOCKER_FIRST_STRATEGY.md": (
        r"systemd-first",
        r"primary\s+production\s+path",
        r"docker\s+compose\s+is\s+deprecated",
    ),
    "docs/operations/ACTIVE_SCRIPT_PATHWAYS_AUDIT.md": (
        r"systemd-first\s+operational\s+pathway\s+\(primary\s+production\s+path\)",
        r"JUSTNEWS_ENABLE_LEGACY_START_STOP",
    ),
}


def run_checks(repo_root: Path, checks: dict[str, tuple[str, ...]], violations: list[str]) -> None:
    for rel_path, patterns in checks.items():
        path = repo_root / rel_path
        if not path.exists():
            violations.append(f"missing required active path: {rel_path}")
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                violations.append(f"{rel_path}: matched forbidden pattern '{pattern}'")


def main() -> int:
    repo_root = Path.cwd()
    violations: list[str] = []

    run_checks(repo_root, FILE_CHECKS, violations)
    run_checks(repo_root, DOC_CHECKS, violations)

    if violations:
        print("[FAIL] Docker canonical runtime guard found contradictions:", file=sys.stderr)
        for line in violations:
            print(f" - {line}", file=sys.stderr)
        return 2

    print("[PASS] Docker canonical runtime guard checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
