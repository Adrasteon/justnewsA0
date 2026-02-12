import asyncio
import logging
import os
import json
import httpx
from typing import List, Dict, Any, Optional
from duckduckgo_search import DDGS
from .models import FactCheckRequest, FactCheckResult, Evidence, EvidenceType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FactCheckerService:
    def __init__(self):
        pass

    async def verify_fact(self, request: FactCheckRequest) -> FactCheckResult:
        logger.info(f"Verifying fact: {request.fact}")
        queries = self._generate_queries(request.fact, request.context)
        evidence = await self._collect_evidence(queries, request.sources)
        result = await self._evaluate_evidence(request.fact, evidence)
        return result

    def _generate_queries(self, fact: str, context: str = None) -> List[str]:
        base_queries = [
            f"Is it true that {fact}",
            f"Evidence for {fact}",
            f"{fact} context"
        ]
        if context:
            base_queries.append(f"{fact} {context}")
        return base_queries

    async def _collect_evidence(self, queries: List[str], overrides: List[str] = None) -> List[Evidence]:
        evidence_list = []
        logger.info(f"Collecting evidence with queries: {queries}")

        try:
            with DDGS() as ddgs:
                for query in queries:
                    try:
                        # Fetch up to 3 results per query
                        results = ddgs.text(query, max_results=3)
                        if results:
                            for r in results:
                                body = r.get('body', '')
                                title = r.get('title', '')
                                href = r.get('href', '')
                                evidence_list.append(Evidence(
                                    content=f"{title}: {body}",
                                    source_url=href,
                                    evidence_type=EvidenceType.TEXT,
                                    confidence=0.7, # Default confidence for search results
                                    metadata={"query": query}
                                ))
                    except Exception as e:
                        logger.error(f"Error searching for query '{query}': {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Failed to initialize DuckDuckGo Search: {e}")
            
        # Fallback/Mock evidence if no results found
        if not evidence_list:
             logger.warning("No web evidence found. Using mock fallback.")
             evidence_list.append(Evidence(
                content="Mock evidence content - enterprise service active (Fallback)",
                source_url="http://internal-db",
                evidence_type=EvidenceType.TEXT,
                confidence=0.1
            ))
            
        return evidence_list

    async def _evaluate_evidence(self, fact: str, evidence: List[Evidence]) -> FactCheckResult:
        vllm_base_url = os.getenv("VLLM_BASE_URL")
        
        if vllm_base_url:
            try:
                evidence_text = ""
                if evidence:
                    # Construct evidence context
                    evidence_snippets = []
                    seen_urls = set()
                    for e in evidence:
                        if e.source_url not in seen_urls:
                            evidence_snippets.append(f"- {e.content} (Source: {e.source_url})")
                            seen_urls.add(e.source_url)
                    # Limit to avoid token limits if necessary
                    evidence_text = "\n".join(evidence_snippets[:20])

                prompt = (
                    f"Analyze the following fact based on the provided evidence:\n\n"
                    f"Fact: {fact}\n\n"
                    f"Evidence:\n{evidence_text}\n\n"
                    f"Determine if the fact is accurate based on the evidence. "
                    f"Respond with a valid JSON object containing:\n"
                    f"1. 'is_accurate' (boolean)\n"
                    f"2. 'confidence' (float between 0.0 and 1.0)\n"
                    f"3. 'explanation' (string summarizing the reasoning)\n"
                    f"Do not include any other text."
                )

                async with httpx.AsyncClient() as client:
                    # Append /chat/completions if VLLM_BASE_URL behaves like standard OpenAI base url
                    # Handle trailing slash if present
                    base = vllm_base_url.rstrip('/')
                    url = f"{base}/chat/completions"
                    
                    response = await client.post(
                        url,
                        json={
                            "model": "gpt-3.5-turbo", # Placeholder model name, VLLM often ignores or needs specific
                            "messages": [
                                {"role": "system", "content": "You are a fact-checking assistant. Output only valid JSON."},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.1
                        },
                        timeout=30.0
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        content = data['choices'][0]['message']['content'].strip()
                        
                        # Handle potential markdown code blocks
                        if content.startswith("```json"):
                            content = content[7:]
                        if content.endswith("```"):
                            content = content[:-3]
                        
                        result_data = json.loads(content.strip())
                        
                        return FactCheckResult(
                            fact=fact,
                            is_accurate=result_data.get("is_accurate", False),
                            confidence=result_data.get("confidence", 0.0),
                            evidence=evidence,
                            explanation=result_data.get("explanation", "Evaluated by AI model"),
                            model_trace=data
                        )
                    else:
                        logger.error(f"VLLM call failed: {response.status_code} {response.text}")

            except Exception as e:
                logger.error(f"Error during VLLM evaluation: {e}")

        # Graceful degradation to simple heuristic
        logger.info("Using fallback heuristic for evaluation")
        avg_confidence = 0.5 # Neutral starting point
        explanation = "Insufficient evidence or service unavailable."
        
        if evidence:
            avg_confidence = 0.4
            explanation = "Fallback: Evidence collected but AI analysis unavailable."

            # Very naive keyword check if fact words appear in evidence
            fact_words = set(fact.lower().split())
            match_score = 0
            for e in evidence:
                content_lower = e.content.lower()
                if any(w in content_lower for w in fact_words):
                    match_score += 1
            
            if match_score > 0:
                avg_confidence = min(0.4 + (0.1 * match_score), 0.8)
                explanation = f"Fallback: Found {match_score} evidence items heavily referencing keywords."

        return FactCheckResult(
            fact=fact,
            is_accurate=(avg_confidence > 0.6),
            confidence=avg_confidence,
            evidence=evidence,
            explanation=explanation
        )

service = FactCheckerService()
