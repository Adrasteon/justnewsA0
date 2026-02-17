"""
Analyst Audit Module

Implements factual audit logic using the MCP Fact Checker.
This module extracts claims from text and verifies them against the Fact Checker API
to generate a Factual Accuracy Score (0.0 - 1.0).
"""
import os
import httpx
import asyncio
from typing import Any, Dict, List, Optional
from .claims import extract_claims
from common.observability import get_logger

logger = get_logger(__name__)

# Default to localhost:8018; can be overridden by env
FACT_CHECKER_URL = os.getenv("FACT_CHECKER_URL", "http://localhost:8018")
API_KEY = os.getenv("FACT_CHECKER_API_KEY", "")

# Verdict scoring weights (strict canonical 5-point scale)
VERDICT_SCORES = {
    "true": 1.0,
    "likely true": 0.75,
    "uncertain": 0.5,
    "likely false": 0.25,
    "false": 0.0,
}

VERDICT_ALIASES = {
    "proven": "Uncertain",
    "plausible": "Uncertain",
    "unverified": "Uncertain",
    "improbable": "Uncertain",
    "disproven": "Uncertain",
}


def normalize_verdict(raw_verdict: Any) -> str:
    if not raw_verdict:
        return "Uncertain"
    normalized = str(raw_verdict).strip().lower()
    if normalized in VERDICT_SCORES:
        if normalized == "true":
            return "True"
        if normalized == "likely true":
            return "Likely True"
        if normalized == "uncertain":
            return "Uncertain"
        if normalized == "likely false":
            return "Likely False"
        if normalized == "false":
            return "False"
    if normalized in VERDICT_ALIASES:
        logger.warning("Received non-canonical verdict '%s'; coercing to Uncertain", raw_verdict)
        return VERDICT_ALIASES[normalized]
    logger.warning("Received unknown verdict '%s'; coercing to Uncertain", raw_verdict)
    return "Uncertain"

async def verify_claim(client: httpx.AsyncClient, claim: str, headers: dict) -> Dict[str, Any]:
    """Verify a single claim against the Fact Checker API."""
    try:
        payload = {
            "fact": claim,
            "context": "extracted from article",
            "sources": []
        }
        url = f"{FACT_CHECKER_URL}/fact_check"
        resp = await client.post(url, json=payload, headers=headers, timeout=60.0)
        
        if resp.status_code == 200:
            result = resp.json()
            result["verdict"] = normalize_verdict(result.get("verdict"))
            return result
        else:
            logger.warning(f"Fact check failed for '{claim[:30]}...': Status {resp.status_code}")
            return {"error": f"HTTP {resp.status_code}", "verdict": "Uncertain"}
            
    except Exception as e:
        logger.error(f"Exc checking claim '{claim[:30]}...': {e}")
        return {"error": str(e), "verdict": "Uncertain"}

async def audit_text(text: str, max_claims: int = 5) -> Dict[str, Any]:
    """
    Perform a factual audit on the provided text.
    
    Steps:
    1. Extract claims.
    2. Call Fact Checker for top N claims.
    3. Calculate weighted accuracy score.
    
    Returns:
        Dict with keys: score, details, verdicts
    """
    logger.info(f"Starting factual audit on text ({len(text)} chars)...")
    
    # 1. Extract Claims
    claims = extract_claims(text, max_claims=max_claims)
    if not claims:
        logger.info("No verifyable claims extracted.")
        return {
            "score": 0.5, # Neutral score when no claims found (?) 
                          # Or maybe None to indicate N/A. Requirements imply a score is needed.
                          # 0.5 is 'Uncertain' which is safe.
            "details": {"message": "No verifiable claims found"},
            "verdicts": []
        }
    
    api_url = FACT_CHECKER_URL.rstrip("/")
    logger.info(f"Verifying {len(claims)} claims against {api_url}")
    
    # 2. Verify in Parallel
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    tasks = []
    network_error_fallback = False

    async with httpx.AsyncClient() as client:
        # Check health first (optional optimization, but good for diagnostics)
        try:
            health = await client.get(f"{api_url}/health", timeout=5.0)
            if health.status_code != 200:
                logger.warning(f"Fact Checker health check failed: {health.status_code}")
        except Exception as e:
            logger.warning(f"Fact Checker unreachable: {e}. Returning neutral score.")
            network_error_fallback = True

        if network_error_fallback:
             return {
                "score": 0.5,
                "details": {"error": "Fact Checker service unreachable"},
                "verdicts": []
            }

        for claim_obj in claims:
            txt = claim_obj.get('claim_text', '')
            if txt:
                tasks.append(verify_claim(client, txt, headers))
        
        results = await asyncio.gather(*tasks)

    # 3. Calculate Score
    total_score = 0.0
    valid_count = 0
    verdict_counts = {}
    detailed_results = []
    
    for i, res in enumerate(results):
        v_raw = normalize_verdict(res.get("verdict", "Uncertain"))
        v_str = v_raw.lower()
        score = VERDICT_SCORES.get(v_str, 0.5)
        
        # Log unknown verdicts
        if v_str not in VERDICT_SCORES:
            logger.warning(f"Unknown verdict received: '{v_raw}'. Defaulting to 0.5")
        
        total_score += score
        valid_count += 1
        verdict_counts[v_raw] = verdict_counts.get(v_raw, 0) + 1
        
        # Merge extraction info with result
        combined = {
            "claim": claims[i]['claim_text'],
            "confidence": claims[i]['confidence'],
            "fact_check": res
        }
        detailed_results.append(combined)

    final_score = total_score / valid_count if valid_count > 0 else 0.5
    
    # Round to 2 decimals
    final_score = round(final_score, 2)
    
    logger.info(f"Audit Complete. Score: {final_score}. Verdicts: {verdict_counts}")
    
    return {
        "score": final_score,
        "details": {
            "claim_count": len(claims),
            "checked_count": valid_count,
            "verdict_breakdown": verdict_counts
        },
        "verdicts": detailed_results
    }
