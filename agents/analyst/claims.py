"""
Analyst Claim Extraction

Provides heuristic claim extraction suitable for the Analyst agent. The
implementation uses spaCy sentence splitting and simple heuristics to
identify verifiable claims. This is intentionally conservative for MVP.
"""

from __future__ import annotations

import re
from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)

try:
    from spacy.lang.en import English as SpacyEnglish

    HAS_SPACY = True
except Exception:  # pragma: no cover - tests may not have spacy
    SpacyEnglish = None
    HAS_SPACY = False


CLAIM_PATTERN = re.compile(
    r"\b(?:is|are|was|were|reported|claims|say|says|said|according to|revealed|announced|shows|found|shows|found|estimate|estimated)\b",
    flags=re.IGNORECASE,
)


def _sentences_spacy(text: str) -> list[str]:
    nlp = SpacyEnglish()
    nlp.add_pipe("sentencizer")
    doc = nlp(text)
    return [sent.text.strip() for sent in doc.sents]


def _sentences_regex(text: str) -> list[str]:
    # fallback: split by sentence-like punctuation
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def extract_claims(text: str, max_claims: int = 8) -> list[dict[str, Any]]:
    """
    Extract candidate claims from text using heuristics.

    Returns a list of dicts with keys: claim_text, start, end, confidence, claim_type.
    """
    if not text or not text.strip():
        return []

    try:
        sentences = _sentences_spacy(text) if HAS_SPACY else _sentences_regex(text)
    except Exception:
        sentences = _sentences_regex(text)

    candidates = []
    for sent in sentences:
        if len(candidates) >= max_claims:
            break

        # look for indicative claim words or numeric facts
        if CLAIM_PATTERN.search(sent) or re.search(
            r"\d{1,3}(?:,\d{3})*(?:\.|%|\b)", sent
        ):
            confidence = 0.6
            if re.search(r"\d", sent):
                confidence = 0.75
            if "according to" in sent.lower() or "reported" in sent.lower():
                confidence = 0.8

            candidates.append(
                {
                    "claim_text": sent,
                    "start": None,
                    "end": None,
                    "confidence": confidence,
                    "claim_type": "assertion",
                }
            )

    # If we found nothing, optionally return the first sentence as a weak claim
    if not candidates and sentences:
        first = sentences[0]
        candidates.append(
            {
                "claim_text": first,
                "start": None,
                "end": None,
                "confidence": 0.3,
                "claim_type": "weak_assertion",
            }
        )

    logger.info(f"Extracted {len(candidates)} claim(s) from text")
    return candidates
