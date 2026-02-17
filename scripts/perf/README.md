gpu_telemetry.sh — telemetry notes

This script collects per-second telemetry for GPU and system sensors and writes a CSV file.

CSV columns (order)

- timestamp

- power_draw_w (GPU power from nvidia-smi, W)

- temperature_c (GPU temperature, °C)

- util_gpu_percent (GPU utilization %)

- util_mem_percent (GPU memory utilization %)

- memory_used_mb (GPU memory used, MB)

- fan (GPU fan speed, percent)

- cpu_pkg_w (CPU package power in W, estimated from RAPL energy_uj) — requires read-access to /sys/class/powercap/intel-
  rapl:0/energy_uj or running the script with sudo

- cpu_pkg_temp_c (CPU package temperature, °C)

- cpu_core_max_c (maximum CPU core temp observed, °C)

- t_sensor_temp_c (T_Sensor / other board-level "T" sensor, °C)

- chipset_temp_c (chipset / PCH / motherboard temp, °C)

- vrm_temp_c (VRM temperature if available, °C)

- system_total_w (estimated total = GPU_w + CPU_pkg_w — will be empty if cpu_pkg_w not available)

Notes and permissions

- CPU package power (cpu_pkg_w) uses the Intel RAPL energy_uj interface. On many systems this file is root-only:
  /sys/class/powercap/intel-rapl:0/energy_uj. To populate cpu_pkg_w you can either:

- run the telemetry script using sudo (passwordless sudo recommended for automated runs), or

- give read permission to the energy_uj file for the telemetry user (admin/security tradeoff).

Example runs

- Run telemetry into /var/log/justnews-perf (recommended):

```bash
mkdir -p /var/log/justnews-perf
chown $USER:$USER /var/log/justnews-perf
./scripts/perf/gpu_telemetry.sh /var/log/justnews-perf

```bash

- Run with cpu package power (passwordless sudo required for automated runs):

```bash
sudo -n true  # ensure passwordless sudo works
sudo ./scripts/perf/gpu_telemetry.sh /var/log/justnews-perf

```bash

If you prefer not to use sudo for a long-running process, ask your system administrator to allow read access to the RAPL
energy_uj file for the telemetry user or group:

```bash

# as root

chown root:system_power /sys/class/powercap/intel-rapl:0/energy_uj
chmod 440 /sys/class/powercap/intel-rapl:0/energy_uj

## add telemetry user to system_power group

usermod -aG system_power $USER

```bash

Limitations

- Not all motherboards expose chipset/VRM sensors; values will be empty when not present.

- `sensors` CLI (lm-sensors) is not required — the script reads hwmon/sysfs directly and prefers label matching.

- `system_total_w` is an estimate (GPU + CPU) and does not include PSU inefficiency, disk, network, fans, or other
  devices.
Automatic telemetry agent ------------------------

To ensure telemetry is captured whenever the GPU is under load we provide a lightweight GPU activity monitor agent
`scripts/perf/gpu_activity_agent.py` which will automatically start the CSV collector and Prometheus exporter when the
GPU utilization exceeds a threshold for a configurable period, and stop them once the GPU becomes idle.

NVML dropout watchdog --------------------- `scripts/perf/nvml_dropout_watchdog.py`uses the`pynvml` bindings to stream
NVML samples, register XID/event callbacks, and dump the last N seconds of context whenever NVML throws (for example
`NVML_ERROR_GPU_IS_LOST`). Run it next to any medium-load scenario so you capture the exact state leading up to the
drop-out:

```bash
mkdir -p /var/log/justnews-perf
python3 scripts/perf/nvml_dropout_watchdog.py \
  --log-file /var/log/justnews-perf/nvml_watchdog.jsonl \
  --context-samples 180 \
  --capture-dmesg &
WATCHDOG_PID=$!

## run the medium load scenario (gpu_activity_agent, simulate_concurrent_inference, etc.)

wait ${WATCHDOG_PID}

```

Afterwards inspect the structured JSONL log for `nvml_exception`or`nvml_event` entries:

```bash
jq 'select(.event == "nvml_exception")' /var/log/justnews-perf/nvml_watchdog.jsonl

```bash

Each exception entry includes the rolling telemetry context (utilisation, memory, clocks, temps, running compute
processes) captured right before NVML failed plus an optional `dmesg` tail, making it easier to pinpoint the trigger.

````

Key options

- `--start-util` / `--start-seconds` — start telemetry when GPU util exceeds start-util %% for start-seconds

- `--stop-util` / `--stop-seconds`   — stop telemetry after GPU util stays at or below stop-util %% for stop-seconds

- `--out-dir`                         — directory for CSV logs (default `/var/log/justnews-perf`)

- `--exporter-port` / `--exporter-interval` — Prometheus exporter options

Test mode is available with `--test` which simulates a short spike to exercise start/stop behaviour.

Example

```

python3 scripts/perf/gpu_activity_agent.py --start-util 20 --start-seconds 5 --stop-util 10 --stop-seconds 15

```

Integration
-----------
This monitor can run as a separate agent/process on each GPU host. It is designed to complement
the existing `gpu_orchestrator` (orchestrator should not be blocked by the agent). If preferred,
the orchestrator can call `gpu_activity_agent.py` hooks (start/stop) when scheduling workloads.

Systemd / deployment
--------------------
There is a ready-to-install systemd unit template under `scripts/perf/systemd/justnews-gpu-telemetry.service` and installer helpers:

- `scripts/perf/install_logrotate.sh` — installs a logrotate policy to rotate files under `/var/log/justnews-perf` (installs `/etc/logrotate.d/justnews-perf`).

- `scripts/perf/install_service.sh` — installs the systemd unit and creates `/etc/default/justnews-gpu-telemetry` with sane defaults (user, workdir, logdir, exporter port).

- `scripts/perf/install_all.sh` — convenience wrapper that runs both installers and starts the service.

The service uses an EnvironmentFile `/etc/default/justnews-gpu-telemetry` so you can tune runtime defaults (user, workdir, logdir, exporter port and thresholds) without editing the unit file directly. After editing the env file, run: `sudo systemctl restart justnews-gpu-telemetry.service`.

Stress Testing
--------------
### Context Window Stress Test (`stress_test_context_window.py`)

Validates the vLLM server's ability to handle increasing context lengths until failure or a defined maximum. Useful for determining safe context limits for your specific hardware.

**Usage:**

```bash
# Basic run (defaults: start=1000, max=8192, step=500)
python scripts/perf/stress_test_context_window.py

# Custom range
python scripts/perf/stress_test_context_window.py --start 4000 --max 16000 --step 1000 --model mistralai/Mistral-7B-Instruct-v0.3

# Specify vLLM URL
python scripts/perf/stress_test_context_window.py --url http://localhost:8000/v1
```

**Output:**
- Prints success/failure for each context length.
- Summary table of tested lengths and results.
