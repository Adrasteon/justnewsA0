#!/usr/bin/env bash
# Simple GPU telemetry collector for experiments
# Writes CSV rows with timestamp, power draw, temp, util, mem usage, fan

set -euo pipefail

OUT_DIR="${1:-/var/log/justnews-perf}"
mkdir -p "$OUT_DIR"

TS=$(date -u +%Y%m%dT%H%M%SZ)
OUTFILE="$OUT_DIR/gpu_telemetry_$TS.csv"

echo "timestamp,power_draw_w,temperature_c,util_gpu_percent,util_mem_percent,memory_used_mb,fan,cpu_pkg_w,cpu_pkg_temp_c,cpu_core_max_c,t_sensor_temp_c,chipset_temp_c,vrm_temp_c,system_total_w" > "$OUTFILE"

echo "Writing telemetry to $OUTFILE (Ctrl-C to stop)"
# Pre-flight: check if RAPL energy interface is readable or if sudo can be used
RAPL_PATH="/sys/class/powercap/intel-rapl:0/energy_uj"
RAPL_MODE="none"
if [ -r "$RAPL_PATH" ]; then
  RAPL_MODE="direct"
elif command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1 && sudo test -r "$RAPL_PATH" >/dev/null 2>&1; then
  RAPL_MODE="sudo"
fi
echo "RAPL mode: $RAPL_MODE (cpu package power requires read-access to $RAPL_PATH)" >> "$OUTFILE"

while true; do
  # Query GPU metrics and append CSV line
  # Avoid breaking if nvidia-smi is temporarily unavailable
  if nvidia-smi -q > /dev/null 2>&1; then
    read -r TIMESTAMP PWR TEMP UTILGPU UTILMEM MEMUSED FAN < <(nvidia-smi --query-gpu=timestamp,power.draw,temperature.gpu,utilization.gpu,utilization.memory,memory.used,fan.speed --format=csv,noheader,nounits | sed -n '1p' | awk -F", " '{for(i=1;i<=NF;i++) gsub(/^[ \t]+|[ \t]+$/,"",$i); print $1" "$2" "$3" "$4" "$5" "$6" "$7}')
    # Memory used may include units — try to strip non-digits
    MEMNUM=$(echo "$MEMUSED" | sed 's/[^0-9]*//g')
    # Gather CPU package energy (RAPL) to estimate CPU power in W (if available).
    CPU_PKG_W=""
    # prefer a direct read — but on many kernels energy_uj is root-only, so
    # if not readable try to use sudo (passwordless) as fallback
    RAPL_PATH="/sys/class/powercap/intel-rapl:0/energy_uj"
    if [ -r "$RAPL_PATH" ]; then
      NOW_UJ=$(cat "$RAPL_PATH" 2>/dev/null || echo 0)
    elif command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1 && sudo test -r "$RAPL_PATH" >/dev/null 2>&1; then
      NOW_UJ=$(sudo cat "$RAPL_PATH" 2>/dev/null || echo 0)
    else
      NOW_UJ=""
    fi
    if [ -n "$NOW_UJ" ]; then
      NOW_T=$(date +%s.%N)
      if [ -n "${PREV_RAPL_UJ:-}" ]; then
        # delta energy (uJ) / delta seconds -> uJ/s -> W (1 W = 1 J/s -> 1e6 uJ/s)
        DT=$(awk -v a="$NOW_T" -v b="$PREV_RAPL_T" 'BEGIN{print a-b}')
        if [ "$DT" != "" ] && awk "BEGIN{exit($DT<=0)}"; then
          DUJ=$(awk -v a="$NOW_UJ" -v b="$PREV_RAPL_UJ" 'BEGIN{print a-b}')
          CPU_PKG_W=$(awk -v duj="$DUJ" -v dt="$DT" 'BEGIN{printf("%.2f", (duj/dt)/1000000.0)}')
        fi
      fi
      PREV_RAPL_UJ=$NOW_UJ
      PREV_RAPL_T=$NOW_T
    fi

    # Query hwmon/sysfs for CPU/chipset/VRM temps. Prefer /sys/class/hwmon lookups
    # because `sensors` CLI may not be installed or populated on minimal systems.

    # helper to read hwmon label-mapped temps (returns raw value, usually millidegrees)
    read_hwmon_val() {
      local match="$1"
      for hw in /sys/class/hwmon/hwmon*; do
        [ -d "$hw" ] || continue
        # look for labelled inputs
        for lbl in "$hw"/temp*_label; do
          [ -f "$lbl" ] || continue
          L=$(cat "$lbl" 2>/dev/null || echo)
          if echo "$L" | grep -qiE "$match"; then
            base=${lbl%_label}
            val=$(cat "${base}_input" 2>/dev/null || echo)
            if [ -n "$val" ]; then printf "%s" "$val"; return 0; fi
          fi
        done
        # fallback: read unlabeled tempN_input values and accept first when no label is present
        for tmp in "$hw"/temp*_input; do
          [ -f "$tmp" ] || continue
          lfile="${tmp%_input}_label"
          if [ ! -f "$lfile" ]; then val=$(cat "$tmp" 2>/dev/null || echo); if [ -n "$val" ]; then printf "%s" "$val"; return 0; fi; fi
        done
      done
    }

    CPU_PKG_TEMP=$(read_hwmon_val 'Package|Tctl|Tdie|CPU') || true

    # For per-core max, scan labels containing Core or Tccd and take max
    CPU_CORE_MAX=""
    for hw in /sys/class/hwmon/hwmon*; do
      for l in "$hw"/temp*_input; do
        [ -e "$l" ] || continue
        labfile="${l%_input}_label"
        lab="$(cat "$labfile" 2>/dev/null || echo)"
        if echo "$lab" | grep -qiE 'Core|Tccd|Core [0-9]|CPU'; then
          val=$(cat "$l" 2>/dev/null || echo)
          [ -n "$val" ] || continue
          if [ -z "$CPU_CORE_MAX" ] || awk -v a="$val" -v b="$CPU_CORE_MAX" 'BEGIN{exit(!(a > b))}'; then
            CPU_CORE_MAX=$val
          fi
        fi
      done
    done

    T_SENSOR_TEMP=$(read_hwmon_val 'T_Sensor|T Sensor|T_Sensor|T-Sensor|T_Sensor') || true
    CHIPSET_TEMP=$(read_hwmon_val 'Chipset|PCH|Motherboard') || true
    VRM_TEMP=$(read_hwmon_val 'VRM|vrm') || true

    # normalize to Celsius degrees (hwmon values are millidegrees) if present
    CPU_PKG_TEMP=$(echo "$CPU_PKG_TEMP" | sed 's/[^0-9.-]*//g' | awk '{if($0=="") print ""; else printf("%.2f", $0/1000)}') || true
    CPU_CORE_MAX=$(echo "$CPU_CORE_MAX" | sed 's/[^0-9.-]*//g' | awk '{if($0=="") print ""; else printf("%.2f", $0/1000)}') || true
    T_SENSOR_TEMP=$(echo "$T_SENSOR_TEMP" | sed 's/[^0-9.-]*//g' | awk '{if($0=="") print ""; else printf("%.2f", $0/1000)}') || true
    CHIPSET_TEMP=$(echo "$CHIPSET_TEMP" | sed 's/[^0-9.-]*//g' | awk '{if($0=="") print ""; else printf("%.2f", $0/1000)}') || true
    VRM_TEMP=$(echo "$VRM_TEMP" | sed 's/[^0-9.-]*//g' | awk '{if($0=="" ) print ""; else printf("%.2f", $0/1000)}') || true

    # If we got numbers like '+43.0' that are strings, ensure numeric format (or empty)
    CPU_PKG_TEMP=$(echo "$CPU_PKG_TEMP" | sed 's/[^0-9.\-]*//g')
    CPU_CORE_MAX=$(echo "$CPU_CORE_MAX" | sed 's/[^0-9.\-]*//g')
    CHIPSET_TEMP=$(echo "$CHIPSET_TEMP" | sed 's/[^0-9.\-]*//g')
    VRM_TEMP=$(echo "$VRM_TEMP" | sed 's/[^0-9.\-]*//g')

    # system_total_w: estimated = gpu power + cpu package power (if available)
    SYSTEM_TOTAL=""
    if [ -n "$CPU_PKG_W" ]; then
      SYSTEM_TOTAL=$(awk -v g="$PWR" -v c="$CPU_PKG_W" 'BEGIN{printf("%.2f", (g+0)+(c+0))}')
    fi

    echo "$TIMESTAMP,$PWR,$TEMP,$UTILGPU,$UTILMEM,$MEMNUM,$FAN,$CPU_PKG_W,$CPU_PKG_TEMP,$CPU_CORE_MAX,$T_SENSOR_TEMP,$CHIPSET_TEMP,$VRM_TEMP,$SYSTEM_TOTAL" >> "$OUTFILE"
  else
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ),nvidia-smi-unavailable,,,,,, ,,, ,," >> "$OUTFILE"
  fi
  sleep 1
done
