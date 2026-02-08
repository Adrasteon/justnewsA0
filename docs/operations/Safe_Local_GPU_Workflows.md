# Safe Local GPU Workflows ✅

This document records recommended, quick controls to reduce the chance that running GPU workloads locally will crash the
desktop or take down other services.

## Quick safe run

Use the repository helper to run a command with safe defaults that avoid using GPUs and set PyTorch fragmentation
mitigation:

```

./scripts/safe_local_run.sh -- pytest -q

## or a long-running agent

./scripts/safe_local_run.sh -- scripts/run_agent_locally.sh

```

What the script sets by default (can be overridden by pre-exporting variables):

- CUDA_VISIBLE_DEVICES="" (disables visible GPUs)

- VLLM_SKIP_START=1 (prevents vLLM from auto-starting during tests)

- PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True (reduces PyTorch GPU fragmentation edge cases)

## Run with memory cap

Run a command under a memory cap so it cannot trigger a system-wide OOM that kills GUI processes.

Example — cap to 32GiB:

```

./scripts/run_capped.sh 32G -- pytest -q

```

This uses `systemd-run --scope -p MemoryMax=...` to ensure the job's memory is contained.

## Monitoring (short-term)

Start the monitor in background to capture GPU and host memory usage:

```bash

nohup ./scripts/gpu_monitor.sh /tmp/gpu_monitor.log 1 &

## or run as a user systemd unit: copy scripts/gpu_monitor.service.example to ~/.config/systemd/user/gpu-monitor.service

## systemctl --user daemon-reload && systemctl --user start gpu-monitor.service

```

The log includes `nvidia-smi` compute app listings, memory/temperature summaries, and the top host RSS processes.

## Suggested additions for /etc/justnews/global.env

Add these (commented) defaults to your `/etc/justnews/global.env` so local runs and tests can pick them up if desired:

```bash

## Safe local GPU defaults (uncomment to apply globally):

## CUDA_VISIBLE_DEVICES=

## VLLM_SKIP_START=1

## PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

```

Note: editing `/etc/justnews/global.env` affects system services that use it — prefer per-shell usage or developer
dotfiles.

## When to escalate

- If you see repeated driver Xid/NVRM messages in `dmesg`or`journalctl`, collect`nvidia-smi -q -a`,`dmesg -T`, and the
  monitor logs and file a follow-up for deeper hardware/driver investigation.

---
