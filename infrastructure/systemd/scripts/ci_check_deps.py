#!/usr/bin/env python3
"""CI helper: check that required runtime Python modules for production agents
are present in the test environment. This mirrors the runtime dependency checks
performed by the startup scripts and prevents missing-module surprises in
production venvs.

Usage: run inside CI where requirements.txt has been installed (or in a venv
that represents the production environment).
"""

from __future__ import annotations

from importlib import util

AGENT_MODULE_MAP = {
    "mcp_bus": ["requests"],
    "gpu_orchestrator": ["requests", "uvicorn"],
    "chief_editor": ["requests"],
    # fall-back default for other agents (keeps checks conservative)
    "default": ["requests"],
}


def find_missing(mods: list[str]) -> list[str]:
    missing = []
    for m in mods:
        if util.find_spec(m) is None:
            missing.append(m)
    return missing


def main() -> int:
    all_missing = {}
    # Check each agent mapping
    for agent, mods in AGENT_MODULE_MAP.items():
        miss = find_missing(mods)
        if miss:
            all_missing[agent] = miss

    if all_missing:
        print("ERROR: Missing runtime Python modules detected for production agents:\n")
        for agent, miss in all_missing.items():
            print(f" - {agent}: {', '.join(miss)}")
        print(
            "\nFix: add the missing packages to requirements.txt and the deployment step that builds /opt/justnews/venv. Example:\n  sudo /opt/justnews/venv/bin/pip install "
        )
        for agent, miss in all_missing.items():
            print(
                f"    sudo /opt/justnews/venv/bin/pip install {' '.join(miss)}  # for {agent}"
            )
        return 2

    print("All required runtime Python modules appear available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
