"""Simple evaluation metrics for text comparison.

Provides token-level precision/recall/f1 utilities used by evaluation runner.
"""

import re
from collections import Counter
from collections.abc import Iterable


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    # simple tokenisation: lowercase, remove punctuation, split on whitespace
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = [t for t in text.split() if t]
    return tokens


def precision_recall_f1(
    pred_tokens: Iterable[str], gold_tokens: Iterable[str]
) -> tuple[float, float, float]:
    """Token-level precision, recall, and F1 between predicted and gold tokens."""
    pred_counts = Counter(pred_tokens)
    gold_counts = Counter(gold_tokens)

    # intersection count
    match = 0
    for tok, cnt in pred_counts.items():
        match += min(cnt, gold_counts.get(tok, 0))

    total_pred = sum(pred_counts.values())
    total_gold = sum(gold_counts.values())

    precision = match / total_pred if total_pred > 0 else 0.0
    recall = match / total_gold if total_gold > 0 else 0.0
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)

    return precision, recall, f1


def _ngrams(tokens: list[str], n: int) -> Counter:
    c = Counter()
    if n <= 0:
        return c
    for i in range(len(tokens) - n + 1):
        c[tuple(tokens[i : i + n])] += 1
    return c


def bleu_score(pred_tokens: list[str], gold_tokens: list[str], n: int = 1) -> float:
    """Compute a simplified BLEU-n score using n-gram precision and a brevity penalty.

    This is a lightweight approximation suitable for parity checks without heavy deps.
    Default `n=1` computes unigram precision (BLEU-1).
    """
    if not pred_tokens or not gold_tokens:
        return 0.0
    pred_ngrams = _ngrams(pred_tokens, n)
    gold_ngrams = _ngrams(gold_tokens, n)
    matches = 0
    total = sum(pred_ngrams.values())
    for ng, cnt in pred_ngrams.items():
        matches += min(cnt, gold_ngrams.get(ng, 0))
    precision = matches / total if total > 0 else 0.0
    # brevity penalty (simplified)
    bp = 1.0
    if len(pred_tokens) < len(gold_tokens):
        bp = pow(2.718281828, 1 - len(gold_tokens) / max(1, len(pred_tokens)))
    return precision * bp


def _lcs_length(a: list[str], b: list[str]) -> int:
    # classic dynamic programming for LCS length
    if not a or not b:
        return 0
    m, n = len(a), len(b)
    dp = [0] * (n + 1)
    for i in range(1, m + 1):
        prev = 0
        for j in range(1, n + 1):
            cur = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev + 1
            else:
                dp[j] = max(dp[j], dp[j - 1])
            prev = cur
    return dp[n]


def rouge_l(
    pred_tokens: list[str], gold_tokens: list[str]
) -> tuple[float, float, float]:
    """Compute ROUGE-L precision/recall/F1 based on LCS."""
    if not pred_tokens or not gold_tokens:
        return 0.0, 0.0, 0.0
    lcs = _lcs_length(pred_tokens, gold_tokens)
    prec = lcs / len(pred_tokens) if pred_tokens else 0.0
    rec = lcs / len(gold_tokens) if gold_tokens else 0.0
    if prec + rec == 0:
        f1 = 0.0
    else:
        f1 = 2 * prec * rec / (prec + rec)
    return prec, rec, f1


def levenshtein_distance(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[lb]


def normalized_levenshtein(a: str, b: str) -> float:
    d = levenshtein_distance(a, b)
    maxlen = max(len(a), len(b))
    if maxlen == 0:
        return 0.0
    return d / maxlen
