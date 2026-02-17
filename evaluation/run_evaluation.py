#!/usr/bin/env python3
"""Evaluation runner CLI.

Usage examples:
  JUSTNEWS_PYTHON evaluation/run_evaluation.py --mode extraction_parity --dataset evaluation/datasets/bbc

Modes:
  extraction_parity  - run token-level parity between extracted text and ground truth files

The runner imports project extraction code and applies it to dataset HTML files.
"""

from __future__ import annotations

import argparse
import os
import sys
from glob import glob

from evaluation.metrics import (
    bleu_score,
    normalized_levenshtein,
    precision_recall_f1,
    rouge_l,
    tokenize,
)


def find_pairs(dataset_dir: str) -> list[tuple[str, str]]:
    """Find (html, txt) pairs in a dataset directory.

    Files should be named `name.html` and `name.txt`.
    """
    html_files = glob(os.path.join(dataset_dir, "*.html"))
    pairs = []
    for html in sorted(html_files):
        base = os.path.splitext(html)[0]
        txt = base + ".txt"
        if os.path.exists(txt):
            pairs.append((html, txt))
    return pairs


def load_file(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def extract_with_project(html: str) -> str:
    """Use the project's extraction pipeline to extract text from HTML.

    Falls back to a naive tag-stripping extraction if the project extractor is unavailable.
    """
    try:
        from agents.crawler.extraction import extract_article_content

        # extract_article_content may expect HTML or (url, html) - try best-effort
        # Many wrappers return a dict with 'cleaned_text' or similar; adapt accordingly.
        result = extract_article_content("", html)
        # result might be a dict or string
        if isinstance(result, dict):
            text = (
                result.get("cleaned_text")
                or result.get("content")
                or result.get("text")
            )
            if text:
                return text
            # fallback to join available pieces
            candidates = []
            for k in ("extracted_text", "content", "raw_text"):
                if k in result and isinstance(result[k], str):
                    candidates.append(result[k])
            if candidates:
                return "\n\n".join(candidates)
            # last resort: return string representation
            return str(result)
    except Exception:
        # fallback naive extractor
        pass

    # Naive fallback: strip tags
    import re

    text = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?>.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def run_extraction_parity(
    dataset_dir: str, metrics: list[str] | None = None, output: str | None = None
) -> int:
    pairs = find_pairs(dataset_dir)
    if not pairs:
        print(f"No (html, txt) pairs found in {dataset_dir}")
        return 2

    scores = []
    for html_path, txt_path in pairs:
        html = load_file(html_path)
        gold = load_file(txt_path)
        pred = extract_with_project(html)
        p_tokens = tokenize(pred)
        g_tokens = tokenize(gold)
        sample_metrics = {}
        # default metrics if none provided
        metrics = metrics or [
            "precision_recall_f1",
            "rouge_l",
            "bleu1",
            "levenshtein_norm",
        ]
        if "precision_recall_f1" in metrics:
            precision, recall, f1 = precision_recall_f1(p_tokens, g_tokens)
            sample_metrics.update({"precision": precision, "recall": recall, "f1": f1})
        if "rouge_l" in metrics:
            r_prec, r_rec, r_f1 = rouge_l(p_tokens, g_tokens)
            sample_metrics.update(
                {
                    "rouge_l_precision": r_prec,
                    "rouge_l_recall": r_rec,
                    "rouge_l_f1": r_f1,
                }
            )
        if "bleu1" in metrics:
            b1 = bleu_score(p_tokens, g_tokens, n=1)
            sample_metrics.update({"bleu1": b1})
        if "levenshtein_norm" in metrics:
            ln = normalized_levenshtein(pred, gold)
            sample_metrics.update({"levenshtein_norm": ln})
        scores.append((os.path.basename(html_path), sample_metrics))

    # print results and aggregate metrics
    import csv
    import json

    print("Extraction parity results:")
    agg = {}
    for name, metrics_map in scores:
        line = f" - {name}: " + ", ".join(
            f"{k}={v:.3f}" for k, v in sorted(metrics_map.items())
        )
        print(line)
        for k, v in metrics_map.items():
            agg.setdefault(k, []).append(v)

    summary = {k: (sum(vs) / len(vs) if vs else 0.0) for k, vs in agg.items()}
    print("Summary:")
    for k, v in sorted(summary.items()):
        print(f" - {k}: {v:.3f}")

    # write outputs if requested
    if output:
        outdir = os.path.dirname(output) or "."
        os.makedirs(outdir, exist_ok=True)
        # JSON report
        with open(output + ".json", "w", encoding="utf-8") as jf:
            json.dump(
                {
                    "samples": [{"name": n, "metrics": m} for n, m in scores],
                    "summary": summary,
                },
                jf,
                indent=2,
            )
        # CSV summary
        csv_path = output + ".csv"
        keys = sorted(summary.keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as cf:
            writer = csv.writer(cf)
            writer.writerow(["metric", "value"])
            for k in keys:
                writer.writerow([k, f"{summary[k]:.6f}"])
        print(f"Wrote reports: {output}.json, {csv_path}")

    # acceptance check uses rouge_l_f1 or fallback to f1
    accept_val = summary.get("rouge_l_f1") or summary.get("f1") or 0.0
    if accept_val >= 0.95:
        print("Acceptance threshold met (>=0.95)")
        return 0
    print("Acceptance threshold not met")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="JustNews evaluation runner")
    parser.add_argument("--mode", choices=("extraction_parity",), required=True)
    parser.add_argument("--dataset", required=True, help="Path to dataset directory")
    parser.add_argument(
        "--metrics",
        help="Comma-separated metrics to compute (precision_recall_f1,rouge_l,bleu1,levenshtein_norm)",
    )
    parser.add_argument(
        "--output", help="Base path for output reports (without extension)"
    )
    args = parser.parse_args(argv)

    if args.mode == "extraction_parity":
        metrics = args.metrics.split(",") if args.metrics else None
        return run_extraction_parity(args.dataset, metrics=metrics, output=args.output)
    print("Unknown mode")
    return 2


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)
