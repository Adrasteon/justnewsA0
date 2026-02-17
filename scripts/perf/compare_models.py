#!/usr/bin/env python3
"""Aggregate and plot perf sweep CSVs for multiple models.

Outputs PNG plots into scripts/perf/results/plots
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

BASE = Path(__file__).resolve().parent
ROOT = BASE / "results"
OUT_DIR = ROOT / "plots"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL_FILES = {
    "mistral-7b-v0.3": ROOT / "mistral_v0.3_int8_sweep.csv",
    "mpt-7b-instruct": ROOT / "mpt_7b_instruct_int8_sweep.csv",
    "pythia-6.9b": ROOT / "pythia_6_9b_int8_sweep.csv",
    "falcon-7b-instruct": ROOT / "falcon_7b_instruct_int8_sweep.csv",
}


def load_summary(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # compute median p50/p95/avg across runs grouped by workers
    grouped = df.groupby("workers").agg(
        p50_ms_median=("p50_ms", "median"),
        p95_ms_median=("p95_ms", "median"),
        avg_ms_median=("avg_ms", "median"),
        gpu_before_mb=("gpu_used_before_mb", "median"),
        gpu_after_mb=("gpu_used_after_mb", "median"),
    )
    grouped = grouped.reset_index()
    return grouped


def make_plots(out_dir: Path):
    sns.set(style="whitegrid")

    all_dfs = []
    for name, csv in MODEL_FILES.items():
        if not csv.exists():
            print(f"Warning: results file not found for {name}: {csv}")
            continue
        df = load_summary(csv)
        df["model"] = name
        all_dfs.append(df)

    all_df = pd.concat(all_dfs, ignore_index=True)

    # Plot p50 and p95
    plt.figure(figsize=(10, 6))
    sns.lineplot(data=all_df, x="workers", y="p50_ms_median", hue="model", marker="o")
    plt.title("p50 latency vs workers (median across repeats)")
    plt.xlabel("Workers")
    plt.ylabel("p50 ms")
    plt.xticks(sorted(all_df["workers"].unique()))
    plt.tight_layout()
    p50_out = out_dir / "p50_vs_workers.png"
    plt.savefig(p50_out)
    print("Wrote", p50_out)
    plt.close()

    plt.figure(figsize=(10, 6))
    sns.lineplot(data=all_df, x="workers", y="p95_ms_median", hue="model", marker="o")
    plt.title("p95 latency vs workers (median across repeats)")
    plt.xlabel("Workers")
    plt.ylabel("p95 ms")
    plt.xticks(sorted(all_df["workers"].unique()))
    plt.tight_layout()
    p95_out = out_dir / "p95_vs_workers.png"
    plt.savefig(p95_out)
    print("Wrote", p95_out)
    plt.close()

    # throughput-friendly avg
    plt.figure(figsize=(10, 6))
    sns.lineplot(data=all_df, x="workers", y="avg_ms_median", hue="model", marker="o")
    plt.title("avg latency vs workers (median across repeats)")
    plt.xlabel("Workers")
    plt.ylabel("avg ms")
    plt.xticks(sorted(all_df["workers"].unique()))
    plt.tight_layout()
    avg_out = out_dir / "avg_vs_workers.png"
    plt.savefig(avg_out)
    print("Wrote", avg_out)
    plt.close()

    # Also write an aggregated CSV for inspection
    out_csv = out_dir / "combined_summary.csv"
    all_df.to_csv(out_csv, index=False)
    print("Wrote", out_csv)


if __name__ == "__main__":
    make_plots(OUT_DIR)
