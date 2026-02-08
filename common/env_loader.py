"""Utility helpers for loading environment variables from global.env.

This provides a shared implementation so that scripts run outside the
systemd-managed stack can still discover credentials defined in the
standard ``global.env`` file.  Values from existing environment variables
always take precedence so that explicit exports override file contents.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from pathlib import Path

_LOADED_ENV_PATHS: set[Path] = set()


def _iter_candidate_paths(extra_paths: Sequence[Path] | None = None) -> list[Path]:
    """Return candidate locations for the global environment file."""
    candidates: list[Path] = []

    env_override = os.environ.get("JUSTNEWS_GLOBAL_ENV")
    if env_override:
        # When a specific override is set, prefer only that path (and any
        # explicitly passed `extra_paths`) to avoid loading repository or
        # system-level global.env files unexpectedly during tests or when a
        # developer supplies an explicit path.
        candidates.append(Path(env_override).expanduser())
        if extra_paths:
            candidates.extend(list(extra_paths))
        # Short-circuit – we don't want to load all the other candidate
        # locations if a specific explicit path was requested.
        # Note: The downstream loader still enforces a global, single-load
        # policy via the _LOADED_ENV_PATHS set.
        # Return early here; the dedup/ordering is handled below.
        # We'll still remove duplicates in the final pass.
        seen: set[Path] = set()
        ordered: list[Path] = []
        for path in candidates:
            if path not in seen:
                seen.add(path)
                ordered.append(path)
        return ordered
    # Standard system location used by the managed services.
    # When running tests, tests/conftest.py sets PYTEST_RUNNING=1 to avoid
    # loading a system-level /etc/justnews/global.env file and instead prefer
    # a test-local override to prevent tests from picking up system-wide
    # configuration unexpectedly.
    if os.environ.get("PYTEST_RUNNING") != "1":
        candidates.append(Path("/etc/justnews/global.env"))

    # If SERVICE_DIR is defined we expect a sibling global.env next to it.
    service_dir = os.environ.get("SERVICE_DIR")
    if service_dir:
        candidates.append(Path(service_dir).expanduser() / "global.env")

    # Repository root – this module lives in common/, so parents[1] is the
    # package directory and parents[2] is the repo root.  When running
    # under pytest we prefer to avoid repository-level global.env files so
    # that test runs remain deterministic (the top-level conftest already
    # sets a per-run TEST global.env override).  Only append the repo root
    # path if tests are not explicitly requesting pytest isolation.
    if os.environ.get("PYTEST_RUNNING") != "1":
        repo_root = Path(__file__).resolve().parents[2]
        candidates.append(repo_root / "global.env")

    # Current working directory for ad-hoc scripts.
    candidates.append(Path.cwd() / "global.env")

    if extra_paths:
        candidates.extend(extra_paths)

    # Remove duplicates while preserving order.
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in candidates:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def load_global_env(
    *, logger=None, extra_paths: Iterable[Path] | None = None
) -> list[Path]:
    """Load environment variables from the first accessible global.env files.

    Returns a list of paths that were successfully loaded.  The same file is
    never processed more than once per process.
    """
    loaded: list[Path] = []
    extras = list(extra_paths or [])
    for path in _iter_candidate_paths(extras):
        if path in _LOADED_ENV_PATHS:
            continue
        if not path.exists() or not path.is_file():
            continue

        try:
            with open(path, encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # Strip surrounding quotes and inline comments if present.
                    if (
                        value.startswith(("'", '"'))
                        and value.endswith(("'", '"'))
                        and len(value) >= 2
                    ):
                        value = value[1:-1]
                    if " #" in value:
                        value = value.split(" #", 1)[0].strip()
                    if key and key not in os.environ:
                        os.environ[key] = value
            _LOADED_ENV_PATHS.add(path)
            loaded.append(path)
            if logger:
                logger.info("Loaded environment variables from %s", path)
        except Exception as exc:  # pragma: no cover - defensive
            if logger:
                logger.warning("Failed to load environment file %s: %s", path, exc)
            continue

    return loaded


__all__ = ["load_global_env"]
