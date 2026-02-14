# Factual Audit System

## Overview
The Factual Audit system provides a mechanism to verify the truthfulness of claims extracted from news articles using the MCP Fact Checker.

## Verdict Scale (5-Point)
We adhere to a strict 5-point Likert scale for truthfulness:

| Verdict      | Score | Definition |
|--------------|-------|------------|
| **True**     | 1.00  | Directly verified by multiple high-credibility sources or undisputed common knowledge. |
| **Likely True** | 0.75 | Consistent with expert consensus/logic but lacks primary confirmation. |
| **Uncertain**| 0.50  | Neutral/Unknown. No relevant evidence found. |
| **Likely False** | 0.25 | Matches disinformation patterns or is unlikely given known facts. |
| **False**    | 0.00  | Directly contradicted or debunked by credible sources. |

## Database Schema
The `articles` table has been extended with:
- `factual_accuracy_score` (FLOAT): 0.0 to 1.0.
- `fact_check_details` (JSON): Breakdown of claims and specific verdicts.

## Architecture
1. **Analyst Agent**: Extracts claims using `agents/analyst/claims.py`.
2. **Fact Checker**: Verifies claims via `mcp_fact_checker_server` (Qwen 14B + DuckDuckGo).
3. **Scoring**: Weighted average of claim scores.

## Usage
Invoked via the Analyst Agent tool `factual_audit`.
```python
result = await audit_text(text="Some text...")
```
