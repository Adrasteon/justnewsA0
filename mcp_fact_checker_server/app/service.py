import asyncio
import logging
import os
import json
import httpx
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from .models import FactCheckRequest, FactCheckResult, Evidence, EvidenceType

# Database integration
# See /app/MIGRATION_BGE_LARGE_1024.md for model and persistence details.
try:
    from database.models.migrated_models import MigratedDatabaseService
    from database.utils.migrated_database_utils import get_db_config
    DB_AVAILABLE = True
except ImportError as e:
    # Handle cases where mcp server is run in isolation without full repo
    import logging
    logging.getLogger(__name__).warning(f"Database integration unavailable: {e}")
    DB_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enterprise-grade credibility registry
TRUSTED_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "nytimes.com", "wsj.com", 
    "theguardian.com", "npr.org", "bloomberg.com", "economist.com",
    "afp.com", "dw.com", "france24.com", "aljazeera.com"
}

FACT_CHECK_DOMAINS = {
    "snopes.com", "politifact.com", "factcheck.org", "fullfact.org", 
    "reuters.com/fact-check", "apnews.com/hub/ap-fact-check",
    "checkyourfact.com", "leadstories.com"
}

class FactCheckerService:
    def __init__(self):
        self.db_service = None
        self.fact_checks_collection = None
        if DB_AVAILABLE:
            try:
                config = get_db_config()
                self.db_service = MigratedDatabaseService(config)
                logger.info("FactCheckerService: Database persistence enabled.")
                
                # Setup semantic cache for fact checks
                if self.db_service.chroma_client:
                    try:
                        self.fact_checks_collection = self.db_service.chroma_client.get_or_create_collection(
                            name="fact_checks_vector",
                            metadata={"description": "Semantic cache of previously verified facts"}
                        )
                        logger.info("FactCheckerService: Semantic claims cache initialized.")
                    except Exception as ce:
                        logger.warning(f"Failed to initialize fact_checks collection: {ce}")
            except Exception as e:
                logger.warning(f"FactCheckerService: Failed to initialize DB: {e}")

    async def verify_fact(self, request: FactCheckRequest) -> FactCheckResult:
        start_time = asyncio.get_event_loop().time()
        logger.info(f"Verifying fact: {request.fact}")
        
        # 0. Check internal history (Echo Chamber Mitigation / Knowledge Reuse)
        historical_evidence = await self._lookup_history(request.fact)
        
        queries = self._generate_queries(request.fact, request.context)
        
        collect_start = asyncio.get_event_loop().time()
        evidence = await self._collect_evidence(queries, request.sources)
        
        # Merge historical evidence into the results for AI evaluation
        if historical_evidence:
            evidence.extend(historical_evidence)
        
        # Robustness Fix: Deep Crawl if evidence is thin
        if len([e for e in evidence if e.evidence_type != EvidenceType.TEXT or "INTERNAL_DB" not in e.content]) < 5:
             logger.info("Thin evidence detected. Initiating deep crawl of top results.")
             top_urls = [e.source_url for e in evidence if e.source_url and "http" in e.source_url][:2]
             if top_urls:
                 deep_evidence = await self._deep_crawl_sources(top_urls)
                 evidence.extend(deep_evidence)
        
        collect_end = asyncio.get_event_loop().time()
        
        # Deduplicate evidence by URL to ensure AI only sees unique documents
        total_initial = len(evidence)
        unique_evidence = []
        seen_urls = set()
        for e in evidence:
            if not e.source_url or e.source_url not in seen_urls:
                unique_evidence.append(e)
                if e.source_url:
                    seen_urls.add(e.source_url)
        
        dedup_count = total_initial - len(unique_evidence)
        logger.info(f"Evidence collected: {total_initial} raw, {len(unique_evidence)} unique. Removed {dedup_count} duplicates.")
        
        # 1. Fetch source reliability metrics for domains in unique_evidence
        domain_metrics = {}
        if self.db_service:
            domains = set()
            for e in unique_evidence:
                if e.source_url and "http" in e.source_url:
                    from urllib.parse import urlparse
                    d = urlparse(e.source_url).netloc
                    if d: domains.add(d)
            
            if domains:
                domain_metrics = await self._get_domain_reliability(list(domains))

        eval_start = asyncio.get_event_loop().time()
        result = await self._evaluate_evidence(request.fact, unique_evidence, domain_metrics)
        eval_end = asyncio.get_event_loop().time()
        
        # Inject detailed metrics into model_trace
        result.model_trace["metrics"] = {
            "timings": {
                "total_seconds": round(eval_end - start_time, 2),
                "collection_seconds": round(collect_end - collect_start, 2),
                "evaluation_seconds": round(eval_end - eval_start, 2)
            },
            "source_stats": {
                "raw_count": total_initial,
                "unique_count": len(unique_evidence),
                "duplicate_removed": dedup_count
            }
        }
        
        # 2. Persist result and update source reliability
        if self.db_service:
            await self._persist_result(result)
            await self._update_source_metrics(result)
        
        return result

    async def _get_domain_reliability(self, domains: List[str]) -> Dict[str, Dict[str, int]]:
        """Fetch historical performance metrics for specific domains."""
        if not self.db_service:
            return {}
        
        try:
            cursor, conn = self.db_service.get_safe_cursor(per_call=True, dictionary=True)
            try:
                format_strings = ','.join(['%s'] * len(domains))
                query = f"SELECT domain, proven_count, disproven_count, misinfo_count FROM source_reliability_metrics WHERE domain IN ({format_strings})"
                cursor.execute(query, tuple(domains))
                rows = cursor.fetchall()
                return {row['domain']: row for row in rows}
            finally:
                cursor.close()
                conn.close()
        except Exception as e:
            logger.warning(f"Failed to fetch domain metrics: {e}")
        return {}

    async def _lookup_history(self, fact: str) -> List[Evidence]:
        """Query MariaDB/ChromaDB for previously analyzed facts."""
        if not self.db_service:
            return []
        
        results = []
        try:
            # 1. Semantic lookup in ChromaDB (High-Signal Matches)
            if self.fact_checks_collection and self.db_service.embedding_model:
                try:
                    query_embedding = self.db_service.embedding_model.encode(fact).tolist()
                    semantic_results = self.fact_checks_collection.query(
                        query_embeddings=[query_embedding],
                        n_results=1,
                        include=['metadatas', 'documents', 'distances']
                    )
                    
                    if semantic_results['ids'] and semantic_results['ids'][0]:
                        distance = semantic_results['distances'][0][0]
                        if distance < 0.2: # High similarity threshold
                            meta = semantic_results['metadatas'][0][0]
                            logger.info(f"Semantic historical match found (dist={distance:.4f}): {meta['verdict']}")
                            results.append(Evidence(
                                content=f"[INTERNAL_DB] Semantically similar claim previously analyzed (Similarity Distance: {distance:.4f}). Verdict: {meta['verdict']}. Confidence: {meta['confidence']}. Reasoning: {meta.get('explanation', 'N/A')}",
                                source_url="http://internal-history-semantic",
                                evidence_type=EvidenceType.TEXT,
                                confidence=meta['confidence']
                            ))
                except Exception as ce:
                    logger.warning(f"Semantic history lookup failed: {ce}")

            # 2. Direct text search in MariaDB for exact/close matches (Fallback/Additional)
            cursor, conn = self.db_service.get_safe_cursor(per_call=True, dictionary=True)
            try:
                query = "SELECT verdict, confidence, explanation FROM fact_checks WHERE fact LIKE %s ORDER BY created_at DESC LIMIT 1"
                cursor.execute(query, (f"%{fact}%",))
                row = cursor.fetchone()
                if row:
                    logger.info(f"Historical text match found: {row['verdict']}")
                    results.append(Evidence(
                        content=f"[INTERNAL_DB] Previously analyzed. Verdict: {row['verdict']}. Confidence: {row['confidence']}. Reasoning: {row['explanation']}",
                        source_url="http://internal-history",
                        evidence_type=EvidenceType.TEXT,
                        confidence=row['confidence']
                    ))
            finally:
                cursor.close()
                conn.close()
            
        except Exception as e:
            logger.warning(f"History lookup failed: {e}")
        return results

    async def _persist_result(self, result: FactCheckResult):
        """Save the verification result to MariaDB and ChromaDB."""
        if not self.db_service:
            return
            
        try:
            cursor, conn = self.db_service.get_safe_cursor(per_call=True)
            try:
                # Insert core result into MariaDB
                query = """
                INSERT INTO fact_checks (fact, verdict, confidence, explanation, model_name, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                model_name = result.model_trace.get("model", "unknown")
                metrics = result.model_trace.get("metrics", {})
                metadata_json = json.dumps(metrics)
                cursor.execute(query, (result.fact, result.verdict, result.confidence, result.explanation, model_name, metadata_json))
                fact_check_id = cursor.lastrowid
                
                # Semantic Indexing into ChromaDB
                if self.fact_checks_collection and self.db_service.embedding_model:
                    try:
                        emb = self.db_service.embedding_model.encode(result.fact).tolist()
                        self.fact_checks_collection.add(
                            ids=[f"fact_{fact_check_id}"],
                            embeddings=[emb],
                            documents=[result.fact],
                            metadatas=[{
                                "verdict": result.verdict,
                                "confidence": float(result.confidence),
                                "explanation": result.explanation[:500], # Snippet for context
                                "timestamp": datetime.now().isoformat()
                            }]
                        )
                    except Exception as ce:
                        logger.warning(f"Failed to index fact semantically: {ce}")

                # Insert evidence links
                evidence_query = """
                INSERT INTO fact_check_evidence (fact_check_id, content, source_url, domain, credibility_tag)
                VALUES (%s, %s, %s, %s, %s)
                """
                evidence_data = []
                for e in result.evidence:
                    if "INTERNAL_DB" in e.content: continue # Don't re-index internal history as new evidence
                    
                    domain = ""
                    if e.source_url and "http" in e.source_url:
                        from urllib.parse import urlparse
                        domain = urlparse(e.source_url).netloc
                    
                    tag = "GENERAL"
                    if "[" in e.content and "]" in e.content:
                        tag = e.content.split("]")[0].strip("[")
                    
                    evidence_data.append((fact_check_id, e.content[:1000], e.source_url, domain, tag))
                
                if evidence_data:
                    cursor.executemany(evidence_query, evidence_data)
                
                conn.commit()
            finally:
                cursor.close()
                conn.close()
        except Exception as e:
            logger.error(f"Failed to persist result: {e}")

    async def _update_source_metrics(self, result: FactCheckResult):
        """Adjust reliability scores for domains based on their stance in this check."""
        if not self.db_service:
            return
            
        try:
            cursor, conn = self.db_service.get_safe_cursor(per_call=True)
            try:
                from urllib.parse import urlparse
                
                # Update trusted sources
                for url in result.trusted_sources:
                    if not url or "http" not in url: continue
                    domain = urlparse(url).netloc.lower().replace("www.", "")
                    if domain:
                        query = """
                        INSERT INTO source_reliability_metrics (domain, proven_count)
                        VALUES (%s, 1)
                        ON DUPLICATE KEY UPDATE proven_count = proven_count + 1
                        """
                        cursor.execute(query, (domain,))
                
                # Update misleading sources
                for url in result.misleading_sources:
                    if not url or "http" not in url: continue
                    domain = urlparse(url).netloc.lower().replace("www.", "")
                    if domain:
                        query = """
                        INSERT INTO source_reliability_metrics (domain, misinfo_count)
                        VALUES (%s, 1)
                        ON DUPLICATE KEY UPDATE misinfo_count = misinfo_count + 1
                        """
                        cursor.execute(query, (domain,))
                
                conn.commit()
            finally:
                cursor.close()
                conn.close()
        except Exception as e:
            logger.error(f"Failed to update source metrics: {e}")

    async def _deep_crawl_sources(self, urls: List[str]) -> List[Evidence]:
        """Fetch full page content for limited set of sources."""
        results = []
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            tasks = []
            for url in urls:
                tasks.append(client.get(url))
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for i, response in enumerate(responses):
                if isinstance(response, httpx.Response) and response.status_code == 200:
                    # Intelligent text extraction: prioritize article/main content
                    soup = BeautifulSoup(response.text, 'html.parser')
                    for s in soup(["script", "style", "nav", "footer", "header"]):
                        s.decompose()
                    
                    # Try to find main content
                    main_content = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile(r'content|article|body', re.I))
                    if main_content:
                        text = main_content.get_text(separator=' ', strip=True)
                    else:
                        text = soup.get_text(separator=' ', strip=True)
                        
                    results.append(Evidence(
                        content=text[:3500], # Increased limit for better context
                        source_url=urls[i],
                        evidence_type=EvidenceType.TEXT,
                        confidence=0.9, # Higher confidence for full page content
                        metadata={"type": "deep_crawl"}
                    ))
        return results

    def _generate_queries(self, fact: str, context: str = None) -> List[str]:
        # Filter out common stop-words and focus on the core claim for search engine optimization
        sanitized_fact = fact.replace("?", "").replace("!", "").strip()
        
        # Diversified search intents for cross-verification
        base_queries = [
            sanitized_fact,
            f'"{sanitized_fact}" news', # Search for exact claim in news
            f"{sanitized_fact} (site:snopes.com OR site:politifact.com OR site:factcheck.org)", # Targeted fact-check search
            f"{sanitized_fact} debunked hoax conspiracy", # Probing for disinformation patterns
            f"{sanitized_fact} official government statement report", # Seeking primary authority
            f"{sanitized_fact} ClaimReview check" # Targeting schema.org fact check markup
        ]
        if context:
            base_queries.append(f"{sanitized_fact} {context}")
        
        return base_queries[:7]

    async def _collect_evidence(self, queries: List[str], overrides: List[str] = None) -> List[Evidence]:
        logger.info(f"Collecting evidence with queries: {queries}")
        
        ad_patterns = ['ad.', 'doubleclick', 'googleadservices']
        
        async def fetch_query(query: str) -> List[Evidence]:
            local_evidence = []
            try:
                # Run synchronous DDGS in a separate thread to avoid blocking the event loop
                def sync_search():
                    with DDGS() as ddgs:
                        raw_results = ddgs.text(query, max_results=5)
                        results = list(raw_results) if raw_results else []
                        if not results:
                            raw_results = ddgs.text(query)
                            results = list(raw_results)[:5] if raw_results else []
                        return results

                loop = asyncio.get_event_loop()
                results = await loop.run_in_executor(None, sync_search)

                logger.info(f"Query '{query}' returned {len(results)} results")
                for r in results:
                    href = r.get('href', '')
                    if any(pattern in href for pattern in ad_patterns) or not href:
                        continue
                     
                    # Domain credibility scoring
                    source_label = "GENERAL"
                    confidence = 0.7
                    from urllib.parse import urlparse
                    domain = urlparse(href).netloc.lower().replace("www.", "")
                    
                    if any(d in domain or d in href for d in FACT_CHECK_DOMAINS):
                        source_label = "FACT_CHECK"
                        confidence = 0.95
                    elif any(d in domain for d in TRUSTED_DOMAINS):
                        source_label = "TRUSTED_NEWS"
                        confidence = 0.85

                    body = r.get('body', '')
                    title = r.get('title', '')
                    local_evidence.append(Evidence(
                        content=f"[{source_label}] {title}: {body}",
                        source_url=href,
                        evidence_type=EvidenceType.TEXT,
                        confidence=confidence,
                        metadata={"query": query, "source_type": source_label, "domain": domain}
                    ))
            except Exception as e:
                logger.error(f"Error searching for query '{query}': {e}")
            return local_evidence

        # Launch all searches in parallel
        tasks = [fetch_query(q) for q in queries]
        results_lists = await asyncio.gather(*tasks)
        
        evidence_list = []
        for l in results_lists:
            evidence_list.extend(l)
            
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

    async def _evaluate_evidence(self, fact: str, evidence: List[Evidence], domain_metrics: Dict[str, Any] = None) -> FactCheckResult:
        vllm_base_url = os.getenv("VLLM_API_BASE") or os.getenv("VLLM_BASE_URL")
        domain_metrics = domain_metrics or {}
        
        if vllm_base_url:
            try:
                evidence_text = ""
                if evidence:
                    # Construct evidence context with injected reliability metrics
                    evidence_snippets = []
                    for e in evidence:
                        domain = ""
                        if e.source_url and "http" in e.source_url:
                            from urllib.parse import urlparse
                            domain = urlparse(e.source_url).netloc
                        
                        metrics_str = ""
                        if domain in domain_metrics:
                            m = domain_metrics[domain]
                            metrics_str = f" [DB_METRICS: Proven={m['proven_count']}, Misinfo={m['misinfo_count']}]"
                        
                        evidence_snippets.append(f"- {e.content}{metrics_str} (Source: {e.source_url})")
                    
                    evidence_text = "\n".join(evidence_snippets[:20])

                prompt = (
                    f"Analyze the following fact for disinformation or accuracy using the provided evidence and historical domain reliability metrics.\n\n"
                    f"Fact: {fact}\n\n"
                    f"Evidence:\n{evidence_text if evidence_text else 'No search results found.'}\n\n"
                    f"TASK:\n"
                    f"1. Evaluate evidence based on source labels: [FACT_CHECK] > [TRUSTED_NEWS] > [GENERAL].\n"
                    f"2. Consider [DB_METRICS]: Prioritize domains with high 'Proven' counts and be skeptical of those with high 'Misinfo' counts.\n"
                    f"3. Use Chain-of-Thought Reasoning:\n"
                    f"   - Reasoning: Break down the claim and compare against each evidence piece.\n"
                    f"   - Source Assessment: Evaluate which sources are authoritative vs biased.\n"
                    f"   - Logic Check: Identify logical fallacies or disinformation tactics (e.g., emotional manipulation, context stripping).\n"
                    f"   - Conclusion: Synthesize findings into one of the 5 verdicts.\n"
                    f"4. DEFINITIONS (5-Point Scale):\n"
                    f"   - 'proven': Directly verified by multiple high-credibility sources or undisputed common knowledge. No significant counter-evidence exists.\n"
                    f"   - 'plausible': Not explicitly confirmed by a primary source, but consistent with expert consensus, logical, or supported by high-trust circumstantial context.\n"
                    f"   - 'unverified': Truly neutral/unknown; no relevant evidence found and not common knowledge.\n"
                    f"   - 'improbable': Not explicitly debunked, but matches disinformation red flags or is unlikely given known physical/historical facts.\n"
                    f"   - 'disproven': Directly contradicted, debunked, or proven false by multiple credible sources.\n"
                    f"5. Respond with a valid JSON object ONLY: {{'verdict': 'proven'|'plausible'|'unverified'|'improbable'|'disproven', 'confidence': float, 'explanation': string, 'trusted_sources': list[url], 'misleading_sources': list[url]}}.\n"
                )

                async with httpx.AsyncClient() as client:
                    # Append /chat/completions if VLLM_BASE_URL behaves like standard OpenAI base url
                    # Handle trailing slash if present
                    base = vllm_base_url.rstrip('/')
                    url = f"{base}/chat/completions"
                    
                    # Use fact-checker specific adapter if configured, else fallback to global model.
                    # This enables fine-tuning/training loops to target the fact-checker adapter ('qwen_fact_checker_v1').
                    model_name = os.getenv("VLLM_FACT_CHECKER_MODEL", os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ"))
                    
                    response = await client.post(
                        url,
                        json={
                            "model": model_name,
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
                        
                        # Advanced JSON extraction to handle various LLM formatting styles
                        import re
                        json_match = re.search(r'\{.*\}', content, re.DOTALL)
                        if json_match:
                            content = json_match.group(0)
                        
                        try:
                            result_data = json.loads(content.strip())
                        except json.JSONDecodeError:
                            # Strip common markdown prefix/suffix if present
                            content = content.strip().replace("```json", "").replace("```", "").strip()
                            result_data = json.loads(content)
                        
                        # Calibrate confidence and verdict
                        verdict = result_data.get("verdict", "unverified").lower()
                        # Plausible/Proven are treated as 'accurate' in boolean terms
                        is_accurate = verdict in ["proven", "plausible"]
                        confidence = result_data.get("confidence", 0.0)
                        
                        # Logic patch: If model says it's Disproven/Improbable because no evidence was found,
                        # it often sets low confidence. We elevate this if search returned many results.
                        if verdict in ["disproven", "improbable"] and confidence < 0.5 and len(evidence) > 10:
                            if "not mentioned" in result_data.get("explanation", "").lower() or \
                               "no evidence" in result_data.get("explanation", "").lower():
                                confidence = 0.85 # High confidence in absence of evidence for major claims

                        return FactCheckResult(
                            fact=fact,
                            is_accurate=is_accurate,
                            verdict=verdict,
                            confidence=max(confidence, 0.1), # Floor at 0.1 if AI provided an answer
                            evidence=evidence,
                            explanation=result_data.get("explanation", "Evaluated by AI model"),
                            trusted_sources=result_data.get("trusted_sources", []),
                            misleading_sources=result_data.get("misleading_sources", []),
                            model_trace=data
                        )
                    else:
                        logger.error(f"VLLM call failed: {response.status_code} {response.text}")

            except Exception as e:
                logger.error(f"Error during VLLM evaluation: {e}")

        # Graceful degradation to simple heuristic
        logger.info("Using fallback heuristic for evaluation")
        avg_confidence = 0.0
        is_accurate = False
        verdict = "unverified"
        explanation = "Service currently unavailable for deep analysis."
        
        if evidence:
            avg_confidence = 0.4
            explanation = "Evaluated via keyword density (AI Model skipped/failed)."
            
            fact_words = set(w.lower() for w in fact.split() if len(w) > 3)
            match_score = 0
            for e in evidence:
                content_lower = e.content.lower()
                if any(w in content_lower for w in fact_words):
                    match_score += 1
            
            if match_score > 2:
                avg_confidence = 0.6
                is_accurate = True
                verdict = "proven"
                explanation = f"Heuristic: High keyword overlap found across {match_score} independent sources."

        return FactCheckResult(
            fact=fact,
            is_accurate=is_accurate,
            verdict=verdict,
            confidence=avg_confidence,
            evidence=evidence,
            explanation=explanation
        )

    async def get_domain_metrics_summary(self) -> Dict[str, Any]:
        """Fetch summary of domain reliability metrics for all tracked domains."""
        if not self.db_service:
            return {"status": "Database unavailable"}
            
        try:
            cursor, conn = self.db_service.get_safe_cursor(per_call=True, dictionary=True)
            try:
                # Top trusted domains
                cursor.execute("SELECT domain, proven_count FROM source_reliability_metrics ORDER BY proven_count DESC LIMIT 10")
                trusted = cursor.fetchall()
                
                # Top misinformation domains
                cursor.execute("SELECT domain, misinfo_count FROM source_reliability_metrics ORDER BY misinfo_count DESC LIMIT 10")
                misleading = cursor.fetchall()
                
                # General stats
                cursor.execute("SELECT COUNT(*) as total_domains, SUM(proven_count) as total_proven, SUM(misinfo_count) as total_misinfo FROM source_reliability_metrics")
                stats = cursor.fetchone()
                
                return {
                    "top_trusted": trusted,
                    "top_misleading": misleading,
                    "statistics": stats
                }
            finally:
                cursor.close()
                conn.close()
        except Exception as e:
            logger.error(f"Failed to fetch domain metrics summary: {e}")
            return {"error": str(e)}

service = FactCheckerService()
