# Extraction Pipeline — Design and Interfaces

Overview

- Trafilatura-first extraction pipeline with layered fallbacks (readability-lxml, jusText, plain-sanitizer). The
  pipeline is intended to provide high-quality cleaned article text with metadata suitable for indexing and downstream
  consumption.

Files of interest

- `agents/crawler/extraction.py`

Pipeline stages

1. Raw HTML normalization and quick heuristics (language detection, word-count checks).

1. Primary extractor: Trafilatura — returns main text, title, and metadata.

1. Secondary extractor: Readability/JusText for cases where primary fails.

1. Plain sanitizer fallback: strip tags, basic heuristics to create a usable text.

Outputs

- `cleaned_text` (string) — main article body used for indexing and ingestion.

- `extraction_metadata`(dict) — includes extractor used, confidence, word_count, coverage stats, and`crawl4ai`
  provenance if available.

Quality gates

- Minimum word_count threshold for downstream ingestion.

- Flags for manual review via HITL if heuristics indicate low-confidence extraction.

Extensibility

- Extraction can consume Crawl4AI markdown output when Trafilatura underperforms for a site (profile flag to toggle).

Testing

- Regression tests with sample HTML fixtures and expected cleaned text.

- Parity tests via the `evaluation` harness comparing Trafilatura output to ground-truth.
