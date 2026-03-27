#!/usr/bin/env python3
"""Portable JustNews memory governor.

Monitors host RAM pressure and applies tiered mitigation to managed agent processes:
- soft pressure: pause one non-critical process (SIGSTOP)
- resume window: resume paused processes (SIGCONT)
- hard pressure: pause additional process, then terminate one non-critical if already exhausted
- emergency pressure: terminate highest-RSS non-critical process

This script is environment-agnostic (works without systemd/docker assumptions) and relies on /proc.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class ManagedProc:
    name: str
    pid: int
    critical: bool
    paused: bool = False
    terminated: bool = False


def read_children_pids(pid: int) -> list[int]:
    path = Path(f"/proc/{pid}/task/{pid}/children")
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except Exception:
        return []
    if not raw:
        return []
    result: list[int] = []
    for token in raw.split():
        try:
            result.append(int(token))
        except Exception:
            continue
    return result


def process_tree_pids(root_pid: int) -> list[int]:
    if root_pid <= 0 or not pid_exists(root_pid):
        return []
    seen: set[int] = set()
    queue = [root_pid]
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        for child in read_children_pids(current):
            if child not in seen and pid_exists(child):
                queue.append(child)
    return sorted(seen)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def log(message: str, *, level: str = "INFO", log_file: Path | None = None) -> None:
    line = f"{utc_now()} [{level}] {message}"
    print(line, flush=True)
    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            pass


def read_mem_usage_percent() -> int | None:
    total_kb = None
    available_kb = None
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available_kb = int(line.split()[1])
                if total_kb is not None and available_kb is not None:
                    break
    except Exception:
        return None

    if not total_kb or available_kb is None or total_kb <= 0:
        return None

    used_kb = total_kb - available_kb
    return max(0, min(100, int((used_kb * 100) / total_kb)))


def pid_exists(pid: int) -> bool:
    return Path(f"/proc/{pid}").exists()


def read_rss_kb(pid: int) -> int:
    status_path = Path(f"/proc/{pid}/status")
    try:
        with status_path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except Exception:
        return 0
    return 0


def read_tree_rss_kb(pid: int) -> int:
    total = 0
    for tree_pid in process_tree_pids(pid):
        total += read_rss_kb(tree_pid)
    return total


def send_signal(proc: ManagedProc, sig: int, *, log_file: Path | None = None) -> bool:
    try:
        os.kill(proc.pid, sig)
        return True
    except ProcessLookupError:
        proc.terminated = True
        return False
    except Exception as exc:
        log(f"Signal {sig} failed for {proc.name} pid={proc.pid}: {exc}", level="WARN", log_file=log_file)
        return False


def send_signal_tree(proc: ManagedProc, sig: int, *, log_file: Path | None = None) -> bool:
    pids = process_tree_pids(proc.pid)
    if not pids:
        proc.terminated = True
        return False

    ok = False
    for tree_pid in reversed(pids):
        try:
            os.kill(tree_pid, sig)
            ok = True
        except ProcessLookupError:
            continue
        except Exception as exc:
            log(
                f"Signal {sig} failed for {proc.name} tree_pid={tree_pid}: {exc}",
                level="WARN",
                log_file=log_file,
            )
    return ok


def load_managed(path: Path, *, log_file: Path | None = None) -> list[ManagedProc]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"Failed to load managed process map {path}: {exc}", level="ERROR", log_file=log_file)
        return []

    result: list[ManagedProc] = []
    for item in payload.get("processes", []):
        try:
            proc = ManagedProc(
                name=str(item["name"]),
                pid=int(item["pid"]),
                critical=bool(item.get("critical", False)),
            )
            if pid_exists(proc.pid):
                result.append(proc)
        except Exception:
            continue

    return result


def pick_by_order(candidates: list[ManagedProc], ordered_names: list[str]) -> ManagedProc | None:
    candidate_by_name = {proc.name: proc for proc in candidates}
    for name in ordered_names:
        proc = candidate_by_name.get(name)
        if proc is not None:
            return proc
    return None


def choose_emergency_victim(candidates: list[ManagedProc]) -> ManagedProc | None:
    if not candidates:
        return None
    return max(candidates, key=lambda proc: read_tree_rss_kb(proc.pid))


def terminate_proc(proc: ManagedProc, *, grace_seconds: int, log_file: Path | None = None) -> bool:
    if proc.terminated:
        return False

    if not pid_exists(proc.pid):
        proc.terminated = True
        return False

    target_pids = process_tree_pids(proc.pid)
    if not target_pids:
        proc.terminated = True
        return False

    if send_signal_tree(proc, signal.SIGTERM, log_file=log_file):
        log(f"Terminating {proc.name} pid={proc.pid} with SIGTERM", level="WARN", log_file=log_file)

    deadline = time.time() + max(1, grace_seconds)
    while time.time() < deadline:
        if not any(pid_exists(pid) for pid in target_pids):
            proc.terminated = True
            proc.paused = False
            log(f"{proc.name} pid={proc.pid} terminated gracefully", level="WARN", log_file=log_file)
            return True
        time.sleep(0.5)

    if any(pid_exists(pid) for pid in target_pids):
        send_signal_tree(proc, signal.SIGKILL, log_file=log_file)
        time.sleep(0.25)

    if not any(pid_exists(pid) for pid in target_pids):
        proc.terminated = True
        proc.paused = False
        log(f"{proc.name} pid={proc.pid} force-killed after grace timeout", level="ERROR", log_file=log_file)
        return True

    log(f"Failed to terminate {proc.name} pid={proc.pid}", level="ERROR", log_file=log_file)
    return False


def run(args: argparse.Namespace) -> int:
    log_file = Path(args.log_file) if args.log_file else None
    state_file = Path(args.state_file) if args.state_file else None
    managed = load_managed(Path(args.pid_map), log_file=log_file)

    if not managed:
        log("No managed processes found; exiting governor", level="WARN", log_file=log_file)
        return 0

    soft_pct = args.soft_percent
    hard_pct = args.hard_percent
    emergency_pct = args.emergency_percent
    resume_pct = args.resume_percent

    if not (0 < resume_pct < soft_pct < hard_pct < emergency_pct < 100):
        log(
            "Invalid thresholds; expected resume < soft < hard < emergency within 1..99",
            level="ERROR",
            log_file=log_file,
        )
        return 1

    pause_order = [value.strip() for value in args.pause_order.split(",") if value.strip()]
    terminate_order = [value.strip() for value in args.terminate_order.split(",") if value.strip()]

    check_interval = max(1.0, float(args.check_interval_seconds))
    cooldown = max(1.0, float(args.action_cooldown_seconds))
    term_grace = max(1, int(args.terminate_grace_seconds))
    stale_exit = max(10, int(args.stale_exit_seconds))
    soft_dwell = max(1.0, float(args.soft_dwell_seconds))
    hard_dwell = max(1.0, float(args.hard_dwell_seconds))
    status_log_interval = max(10.0, float(args.status_log_interval_seconds))

    last_action_at = 0.0
    last_status_log_at = 0.0
    last_live_seen = time.time()
    above_soft_since: float | None = None
    above_hard_since: float | None = None

    log(
        (
            f"Memory governor started: soft={soft_pct}% hard={hard_pct}% emergency={emergency_pct}% "
            f"resume={resume_pct}% interval={check_interval}s cooldown={cooldown}s"
        ),
        log_file=log_file,
    )

    while True:
        live = [proc for proc in managed if pid_exists(proc.pid) and not proc.terminated]

        if live:
            last_live_seen = time.time()
        elif time.time() - last_live_seen >= stale_exit:
            log("No managed processes alive; governor exiting", log_file=log_file)
            return 0

        usage = read_mem_usage_percent()
        if usage is None:
            log("Unable to read host memory usage; retrying", level="WARN", log_file=log_file)
            time.sleep(check_interval)
            continue

        now = time.time()
        can_act = (now - last_action_at) >= cooldown

        if state_file:
            try:
                state_payload = {
                    "timestamp": utc_now(),
                    "host_ram_used_percent": usage,
                    "live_processes": [
                        {
                            "name": proc.name,
                            "pid": proc.pid,
                            "critical": proc.critical,
                            "paused": proc.paused,
                            "rss_kb": read_tree_rss_kb(proc.pid),
                            "tree_size": len(process_tree_pids(proc.pid)),
                        }
                        for proc in live
                    ],
                }
                state_file.parent.mkdir(parents=True, exist_ok=True)
                state_file.write_text(json.dumps(state_payload, indent=2), encoding="utf-8")
            except Exception:
                pass

        if usage <= resume_pct:
            above_soft_since = None
            above_hard_since = None
            resumed = 0
            for proc in live:
                if proc.paused:
                    if send_signal_tree(proc, signal.SIGCONT, log_file=log_file):
                        proc.paused = False
                        resumed += 1
            if resumed:
                log(f"RAM {usage}% <= resume threshold; resumed {resumed} paused process(es)", log_file=log_file)
                last_action_at = now
            time.sleep(check_interval)
            continue

        if usage >= hard_pct:
            if above_hard_since is None:
                above_hard_since = now
        else:
            above_hard_since = None

        if usage >= soft_pct:
            if above_soft_since is None:
                above_soft_since = now
        else:
            above_soft_since = None

        if (now - last_status_log_at) >= status_log_interval:
            top = sorted(live, key=lambda proc: read_tree_rss_kb(proc.pid), reverse=True)[:3]
            top_desc = ", ".join(
                f"{proc.name}:{read_tree_rss_kb(proc.pid)//1024}MB"
                for proc in top
            )
            log(
                f"RAM usage {usage}% (soft={soft_pct}, hard={hard_pct}, emergency={emergency_pct}) top={top_desc}",
                log_file=log_file,
            )
            last_status_log_at = now

        if not can_act:
            time.sleep(check_interval)
            continue

        noncritical = [proc for proc in live if not proc.critical]

        if usage >= emergency_pct:
            victim = choose_emergency_victim(noncritical)
            if victim is not None:
                terminate_proc(victim, grace_seconds=term_grace, log_file=log_file)
                victim.terminated = True
                last_action_at = now
            else:
                log(f"Emergency RAM {usage}% but no non-critical victims available", level="ERROR", log_file=log_file)
            time.sleep(check_interval)
            continue

        if usage >= hard_pct:
            hard_elapsed = (now - above_hard_since) if above_hard_since is not None else 0.0
            if hard_elapsed >= hard_dwell:
                term_target = pick_by_order(noncritical, terminate_order)
                if term_target is None:
                    term_target = choose_emergency_victim(noncritical)
                if term_target is not None:
                    terminate_proc(term_target, grace_seconds=term_grace, log_file=log_file)
                    term_target.terminated = True
                    last_action_at = now
                else:
                    log(f"Hard pressure RAM {usage}%: no non-critical targets available", level="ERROR", log_file=log_file)
            time.sleep(check_interval)
            continue

        if usage >= soft_pct:
            soft_elapsed = (now - above_soft_since) if above_soft_since is not None else 0.0
            if soft_elapsed >= soft_dwell:
                term_target = pick_by_order(noncritical, terminate_order)
                if term_target is not None:
                    terminate_proc(term_target, grace_seconds=term_grace, log_file=log_file)
                    term_target.terminated = True
                    last_action_at = now
            time.sleep(check_interval)
            continue

        time.sleep(check_interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JustNews memory governor")
    parser.add_argument("--pid-map", required=True, help="Path to JSON file with managed process map")
    parser.add_argument("--log-file", required=True, help="Path to governor log file")
    parser.add_argument("--state-file", required=True, help="Path to governor state file")
    parser.add_argument("--soft-percent", type=int, default=85)
    parser.add_argument("--hard-percent", type=int, default=88)
    parser.add_argument("--emergency-percent", type=int, default=92)
    parser.add_argument("--resume-percent", type=int, default=80)
    parser.add_argument("--check-interval-seconds", type=float, default=5.0)
    parser.add_argument("--action-cooldown-seconds", type=float, default=20.0)
    parser.add_argument("--terminate-grace-seconds", type=int, default=12)
    parser.add_argument("--stale-exit-seconds", type=int, default=45)
    parser.add_argument("--soft-dwell-seconds", type=float, default=30.0)
    parser.add_argument("--hard-dwell-seconds", type=float, default=12.0)
    parser.add_argument("--status-log-interval-seconds", type=float, default=30.0)
    parser.add_argument(
        "--pause-order",
        default="crawler,synthesizer,newsreader,archive,analytics,dashboard,training_system,workflow_orchestrator,reasoning,analyst,critic,chief_editor,fact_checker",
    )
    parser.add_argument(
        "--terminate-order",
        default="crawler,synthesizer,newsreader,archive,analytics,dashboard,training_system,workflow_orchestrator,reasoning,analyst,critic",
    )
    return parser


if __name__ == "__main__":
    cli = build_parser().parse_args()
    sys.exit(run(cli))
