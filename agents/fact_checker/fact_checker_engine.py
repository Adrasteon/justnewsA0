"""
Fact Checker Engine - Multi-Model AI Fact Verification Engine

This module implements the core fact-checking engine using a 4-model AI workflow:
- DistilBERT: Fact verification and classification
- RoBERTa: Source credibility assessment
- SentenceTransformers: Evidence retrieval and similarity matching
- spaCy NER: Claim extraction and entity recognition

The engine provides comprehensive fact-checking capabilities with GPU acceleration
and CPU fallbacks, online training integration, and robust error handling.
"""

import os
import re
import time
from datetime import datetime
from typing import Any

import numpy as np

from common.observability import get_logger

try:
    # Direct usage of Qwen adapter bypassing global shim
    from .model_adapter import FactCheckerQwenAdapter as MistralAdapter
    from .model_adapter import MODEL_ADAPTER_NAME, SYSTEM_PROMPT, ClaimAssessment
except Exception:  # pragma: no cover - optional dependency wiring
    ClaimAssessment = None  # type: ignore
    MistralAdapter = None  # type: ignore

# Configure logging
logger = get_logger(__name__)


class FactCheckerConfig:
    """Configuration for the Fact Checker Engine."""

    def __init__(self):
        self.model_configs = {
            "distilbert": {
                "model_name": "distilbert-base-uncased-finetuned-sst-2-english",
                "max_length": 512,
                "batch_size": 16,
                "device": "cpu",  # Forced CPU to relieve VRAM pressure
            },
            "roberta": {
                "model_name": "roberta-base",
                "max_length": 512,
                "batch_size": 16,
                "device": "cpu",  # Forced CPU to relieve VRAM pressure
            },
            "sentence_transformers": {
                "model_name": "sentence-transformers/all-MiniLM-L6-v2",
                "max_length": 512,
                "batch_size": 32,
                "device": "cpu",  # Forced CPU to relieve VRAM pressure
            },
            "spacy": {"model_name": "en_core_web_sm", "batch_size": 16},
        }

        self.gpu_config = {
            "enable_gpu": False,  # Disabled GPU to relieve VRAM pressure
            "gpu_memory_limit": 0.8,
            "cpu_fallback": True,
            "tensorrt_enabled": False,
        }

        self.training_config = {
            "online_training": True,
            "feedback_collection": True,
            "model_update_interval": 3600,  # seconds
            "max_training_samples": 10000,
        }

        self.performance_config = {
            "cache_enabled": True,
            "cache_ttl": 300,  # seconds
            "parallel_processing": True,
            "max_concurrent_requests": 4,
        }


class FactCheckerEngine:
    """
    Multi-model fact-checking engine with GPU acceleration and online training.

    This engine combines multiple AI models to provide comprehensive fact verification:
    - Fact classification and verification
    - Source credibility assessment
    - Evidence retrieval and matching
    - Claim extraction and analysis
    """

    def __init__(self, config: FactCheckerConfig):
        self.config = config
        self.logger = logger

        # Model instances
        self.distilbert_model = None
        self.roberta_model = None
        self.sentence_transformer = None
        self.spacy_nlp = None

        # GPU acceleration
        self.gpu_available = False
        self.tensorrt_engine = None

        # Training and feedback
        self.feedback_buffer = []
        self.training_data = []
        self.last_model_update = time.time()

        # Performance tracking
        self.processing_stats = {
            "total_requests": 0,
            "gpu_requests": 0,
            "cpu_requests": 0,
            "average_processing_time": 0.0,
            "error_count": 0,
        }

        # Cache
        self.cache = {}
        self.cache_timestamps = {}
        self.mistral_adapter: MistralAdapter | None = None
        self._mistral_cache: dict[str, ClaimAssessment] = {}

        # Investigator (Enterprise Researcher)
        self.investigator = None

        # Initialize models
        self._initialize_models()

    def _initialize_models(self):
        """Initialize all AI models with proper error handling."""
        try:
            self.logger.info("🔧 Initializing Fact Checker Engine models...")

            # Initialize Investigator
            try:
                from .investigator import Investigator
                self.investigator = Investigator()
                self.logger.info("✅ Investigator module initialized for deep research")
            except ImportError:
                self.logger.warning("⚠️ Investigator module not found")
            except Exception as e:
                self.logger.warning(f"⚠️ Investigator initialization failed: {e}")

            # Initialize spaCy (lightweight, always available)
            try:
                import spacy

                self.spacy_nlp = spacy.load(
                    self.config.model_configs["spacy"]["model_name"]
                )
                self.logger.info("✅ spaCy NER model loaded successfully")
            except Exception as e:
                self.logger.warning(f"⚠️ spaCy model loading failed: {e}")
                # Fallback to basic tokenization
                self.spacy_nlp = None

            # Initialize transformers models
            try:
                import torch
                from transformers import pipeline

                # Check GPU availability
                self.gpu_available = (
                    torch.cuda.is_available() and self.config.gpu_config["enable_gpu"]
                )
                device = 0 if self.gpu_available else -1

                # DistilBERT for fact verification
                try:
                    self.distilbert_model = pipeline(
                        "sentiment-analysis",
                        model=self.config.model_configs["distilbert"]["model_name"],
                        device=device,
                        return_all_scores=True,
                    )
                    self.logger.info("✅ DistilBERT model loaded successfully")
                except Exception as e:
                    self.logger.warning(f"⚠️ DistilBERT model loading failed: {e}")
                    self.distilbert_model = None

                # RoBERTa for source credibility
                try:
                    self.roberta_model = pipeline(
                        "text-classification",
                        model=self.config.model_configs["roberta"]["model_name"],
                        device=device,
                        return_all_scores=True,
                    )
                    self.logger.info("✅ RoBERTa model loaded successfully")
                except Exception as e:
                    self.logger.warning(f"⚠️ RoBERTa model loading failed: {e}")
                    self.roberta_model = None

            except ImportError as e:
                self.logger.warning(f"⚠️ Transformers library not available: {e}")
                self.distilbert_model = None
                self.roberta_model = None

            # Initialize SentenceTransformers
            try:
                from sentence_transformers import SentenceTransformer

                device = "cuda" if self.gpu_available else "cpu"
                try:
                    self.sentence_transformer = SentenceTransformer(
                        self.config.model_configs["sentence_transformers"][
                            "model_name"
                        ],
                        device=device,
                    )
                except TypeError:
                    # Some test-time mocks of SentenceTransformer don't accept the
                    # `device` kwarg; fall back to a simple call that works with
                    # mocks that expect only the model name.
                    self.sentence_transformer = SentenceTransformer(
                        self.config.model_configs["sentence_transformers"]["model_name"]
                    )
                self.logger.info("✅ SentenceTransformer model loaded successfully")
            except ImportError as e:
                self.logger.warning(
                    f"⚠️ SentenceTransformers library not available: {e}"
                )
                self.sentence_transformer = None

            # Initialize TensorRT if enabled
            if self.config.gpu_config["tensorrt_enabled"] and self.gpu_available:
                try:
                    self._initialize_tensorrt()
                except Exception as e:
                    self.logger.warning(f"⚠️ TensorRT initialization failed: {e}")

            self._initialize_mistral_adapter()

            self.logger.info("🎯 Fact Checker Engine initialization complete")

        except Exception as e:
            self.logger.error(f"❌ Fact Checker Engine initialization failed: {e}")
            raise

    def _initialize_tensorrt(self):
        """Initialize TensorRT engine for GPU acceleration."""
        try:
            # Import TensorRT components
            from agents.analyst.native_tensorrt_engine import TensorRTEngine

            # Create TensorRT engine for fact-checking
            self.tensorrt_engine = TensorRTEngine(
                model_configs=self.config.model_configs,
                memory_limit=self.config.gpu_config["gpu_memory_limit"],
            )

            self.logger.info("✅ TensorRT engine initialized for GPU acceleration")

        except Exception as e:
            self.logger.warning(f"⚠️ TensorRT engine initialization failed: {e}")
            self.tensorrt_engine = None

    def _initialize_mistral_adapter(self) -> None:
        """Prepare the high-accuracy Qwen adapter (lazy-loaded)."""
        if MistralAdapter is None:
            self.logger.info(
                "Qwen adapter dependencies unavailable; continuing with legacy fact-checking stack"
            )
            return
        try:
            self.mistral_adapter = MistralAdapter()
            if getattr(self.mistral_adapter, "enabled", True):
                self.logger.info(
                    "Fact Checker Qwen adapter enabled (loaded on first use)"
                )
            else:
                self.logger.info(
                    "Fact Checker Qwen adapter disabled via env variable"
                )
        except Exception as exc:
            self.logger.warning(
                f"Failed to initialize Fact Checker Qwen adapter: {exc}"
            )
            self.mistral_adapter = None

    def _evaluate_with_mistral(
        self, claim: str, context: str | None = None
    ) -> ClaimAssessment | None:
        """Run the Mistral adapter for the given claim when available."""
        if not self.mistral_adapter or not claim.strip():
            return None

        cache_key = f"{hash(claim)}:{hash(context or '')}"
        cached = self._mistral_cache.get(cache_key)
        if cached:
            return cached

        try:
            assessment = self.mistral_adapter.evaluate_claim(claim, context)
        except Exception as exc:
            self.logger.warning(f"Mistral adapter claim evaluation failed: {exc}")
            return None

        if assessment:
            if len(self._mistral_cache) > 256:
                self._mistral_cache.clear()
            self._mistral_cache[cache_key] = assessment
            return assessment
        return None

    def get_model_status(self) -> dict[str, Any]:
        """Get status of all models and components."""
        return {
            "distilbert_loaded": self.distilbert_model is not None,
            "roberta_loaded": self.roberta_model is not None,
            "sentence_transformer_loaded": self.sentence_transformer is not None,
            "spacy_loaded": self.spacy_nlp is not None,
            "gpu_available": self.gpu_available,
            "tensorrt_enabled": self.tensorrt_engine is not None,
            "online_training_enabled": self.config.training_config["online_training"],
            "cache_enabled": self.config.performance_config["cache_enabled"],
        }

    def get_performance_stats(self) -> dict[str, Any]:
        """Get performance statistics."""
        return {
            **self.processing_stats,
            "cache_size": len(self.cache),
            "feedback_buffer_size": len(self.feedback_buffer),
            "training_data_size": len(self.training_data),
            "last_model_update": datetime.fromtimestamp(
                self.last_model_update
            ).isoformat(),
        }

    async def verify_claim_deep(self, claim: str) -> dict[str, Any]:
        """
        Perform a deep investigation of a claim using the Investigator.
        
        This triggers:
        1. Research planning (Mistral)
        2. Web/Archive Search & Crawl (Crawl4AI)
        3. Visual/Text Evidence extraction (Qwen2-VL)
        4. Verdict synthesis
        """
        if not self.investigator:
            return {"error": "Investigator not available", "verdict": "UNVERIFIED"}

        try:
            report = await self.investigator.investigate(claim)
            return {
                "claim": claim,
                "verdict": report.verdict,
                "reasoning": report.reasoning,
                "evidence_count": len(report.evidence),
                "traceability": [
                    {
                        "source": e.source_url,
                        "type": e.media_type.value,
                        "confidence": e.confidence
                    } for e in report.evidence
                ]
            }
        except Exception as e:
            self.logger.error(f"Deep verification failed: {e}")
            return {"error": str(e), "verdict": "ERROR"}

    async def verify_facts(
        self, content: str, source_url: str | None = None, context: str | None = None
    ) -> dict[str, Any]:
        """
        Verify factual claims in content using AI models.
        Async update: Supports deep investigation calls.

        Args:
            content: Text content to verify
            source_url: Source URL for context
            context: Additional verification context

        Returns:
            Fact verification results
        """
        start_time = time.time()

        try:
            self.processing_stats["total_requests"] += 1

            # Check cache first
            cache_key = f"verify_{hash(content)}_{hash(source_url or '')}"
            if self._is_cache_valid(cache_key):
                return self.cache[cache_key]

            # Extract claims first
            claims = self.extract_claims(content)
            claim_texts = claims.get("claims", [])

            if not claim_texts:
                return {
                    "verification_score": 0.5,
                    "classification": "no_claims_found",
                    "confidence": 0.0,
                    "claims_analyzed": 0,
                }

            # Verify each claim
            verification_scores = []
            classifications = []

            # We process claims concurrently for speed
            import asyncio
            
            tasks = []
            for claim in claim_texts[:10]:  # Limit to first 10 claims
                # Use the new async verify if available
                tasks.append(self._verify_single_claim_async(claim, context))
            
            results = await asyncio.gather(*tasks)
            
            for claim_verification in results:
                verification_scores.append(claim_verification["score"])
                classifications.append(claim_verification["classification"])

            # Aggregate results
            avg_score = np.mean(verification_scores) if verification_scores else 0.5
            dominant_classification = (
                max(set(classifications), key=classifications.count)
                if classifications
                else "unknown"
            )

            result = {
                "verification_score": float(avg_score),
                "classification": dominant_classification,
                "confidence": float(np.std(verification_scores))
                if len(verification_scores) > 1
                else 1.0,
                "claims_analyzed": len(claim_texts),
                "claims_verified": len(verification_scores),
                "individual_scores": verification_scores,
                "classifications": classifications,
            }

            # Cache result
            self._cache_result(cache_key, result)

            processing_time = time.time() - start_time
            self.processing_stats["average_processing_time"] = (
                (
                    self.processing_stats["average_processing_time"]
                    * (self.processing_stats["total_requests"] - 1)
                )
                + processing_time
            ) / self.processing_stats["total_requests"]

            return result

        except Exception as e:
            self.processing_stats["error_count"] += 1
            self.logger.error(f"Error in fact verification: {e}")
            return {"error": str(e)}

    async def _verify_single_claim_async(
        self, claim: str, context: str | None = None
    ) -> dict[str, Any]:
        """Async wrapper for verify_single_claim."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._verify_single_claim, claim, context
        )

    def _verify_single_claim(
        self, claim: str, context: str | None = None
    ) -> dict[str, Any]:
        """
        Verify a single claim using available models.
        
        Strategy:
        1. Fast Check: Use local LLM (Mistral) or DistilBERT.
        2. Escalation: If confidence is low or classification is questionable, 
           trigger the Investigator to perform deep web research.
        """
        try:
            # 1. Fast Check
            result = self._fast_verify_claim(claim, context)
            
            # Escalation conditions
            needs_escalation = (
                result.get("classification") in ["questionable", "unclear", "refuted"] 
                or result.get("evidence_needed", False)
                or result.get("confidence", 1.0) < 0.7
            )
            
            # 2. Deep Research (if configured and triggered)
            if needs_escalation and self.investigator:
                self.logger.info(f"🕵️ Deep verification triggered for: '{claim[:40]}...'")
                try:
                    deep_result = self._run_investigator_sync(claim)
                    
                    if deep_result.get("verdict") and deep_result.get("verdict") != "ERROR":
                        # Map verdict to classification
                        verdict_map = {
                            "VERIFIED": "verified",
                            "FALSE": "refuted",
                            "CONFLICTING": "questionable",
                            "UNVERIFIED": "questionable"
                        }
                        
                        result.update({
                            "classification": verdict_map.get(deep_result["verdict"], "questionable"),
                            "method": "investigator_deep",
                            "confidence": 0.9,  # Higher confidence from research
                            "rationale": deep_result.get("reasoning", ""),
                            "evidence": deep_result.get("traceability", [])
                        })
                        
                        # Adjust score based on verdict
                        if result["classification"] == "verified":
                            result["score"] = 0.95
                        elif result["classification"] == "refuted":
                            result["score"] = 0.05
                        else:
                            result["score"] = 0.5
                            
                except Exception as e:
                    self.logger.warning(f"Deep verification failed, keeping fast result: {e}")
            
            return result

        except Exception as e:
            self.logger.error(f"Error in single claim verification: {e}")
            return {"score": 0.5, "classification": "error", "confidence": 0.0, "error": str(e)}

    def _run_investigator_sync(self, claim: str) -> dict[str, Any]:
        """Run the async investigator in a thread with its own loop to avoid blocking main loop."""
        import asyncio
        import concurrent.futures
        
        def _run_in_new_loop():
            # Create a new loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Run the coroutine to completion
                return loop.run_until_complete(self.verify_claim_deep(claim))
            finally:
                loop.close()

        # Execute in a thread pool to bridge sync -> async safely
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_in_new_loop)
            return future.result()

    def _fast_verify_claim(self, claim: str, context: str | None) -> dict[str, Any]:
        """
        Internal fast verification (LLM/BERT only).
        Ensures audit data (reasoning/traceability) is present even if Deep Research is skipped.
        """
        # Prepare evidence list if context is provided
        base_traceability = []
        if context:
            base_traceability.append({
                "source": "provided_context",
                "type": "context_text",
                "confidence": 1.0, 
                "snippet": context[:200]
            })
            
        # 1. Try Mistral Adapter
        try:
            adapter_assessment = self._evaluate_with_mistral(claim, context)
            if adapter_assessment:
                classification_map = {
                    "verified": "verified",
                    "refuted": "refuted",
                    "unclear": "questionable",
                }
                
                # Use model assessment as traceable evidence
                traceability = base_traceability + [{
                    "source": "mistral_adapter",
                    "type": "model_inference",
                    "confidence": adapter_assessment.confidence
                }]
                
                return {
                    "score": adapter_assessment.score,
                    "classification": classification_map.get(adapter_assessment.verdict, "questionable"),
                    "method": "mistral_adapter",
                    "confidence": adapter_assessment.confidence,
                    "rationale": adapter_assessment.rationale,
                    "evidence_needed": adapter_assessment.evidence_needed,
                    "evidence": traceability # Audit trail
                }
        except Exception as e:
            self.logger.warning(f"Mistral check failed: {e}")

        # 2. Try DistilBERT
        if self.distilbert_model:
            try:
                result = self.distilbert_model(claim[:512])
                scores = {item["label"]: item["score"] for item in result}
                positive = scores.get("POSITIVE", 0.5)
                
                # Generate synthetic rationale for audit
                rationale = (
                    f"DistilBERT sentiment analysis indicates positive probability of {positive:.2f}. "
                    f"Classified as {'verified' if positive > 0.6 else 'questionable'} based on threshold 0.6."
                )
                
                traceability = base_traceability + [{
                    "source": "distilbert_base_uncased",
                    "type": "sentiment_proxy",
                    "confidence": 0.6
                }]
                
                return {
                    "score": float(positive),
                    "classification": "verified" if positive > 0.6 else "questionable",
                    "method": "distilbert_sentiment_proxy",
                    "confidence": 0.6,
                    "rationale": rationale,
                    "evidence_needed": True,
                    "evidence": traceability
                }
            except Exception as e:
                self.logger.warning(f"DistilBERT check failed: {e}")
                
        # 3. Fallback
        return {
            "score": 0.5,
            "classification": "unverified",
            "method": "none",
            "confidence": 0.0,
            "rationale": "Fast verification failed to produce a result from available models.",
            "evidence": base_traceability,
            "evidence_needed": True
        }

    def _heuristic_verification(self, claim: str) -> float:
        """Simple heuristic-based verification when models are unavailable."""
        claim_lower = claim.lower()

        # Positive indicators
        positive_indicators = [
            "according to",
            "reported by",
            "study shows",
            "research indicates",
            "data from",
            "official statement",
            "confirmed",
            "verified",
        ]

        # Negative indicators
        negative_indicators = [
            "allegedly",
            "claimed",
            "supposedly",
            "rumored",
            "unconfirmed",
            "speculation",
            "possibly",
            "might be",
        ]

        positive_score = sum(
            1 for indicator in positive_indicators if indicator in claim_lower
        )
        negative_score = sum(
            1 for indicator in negative_indicators if indicator in claim_lower
        )

        # Base score of 0.5, adjusted by indicators
        score = 0.5 + (positive_score * 0.1) - (negative_score * 0.1)
        return max(0.0, min(1.0, score))

    def validate_sources(
        self, content: str, source_url: str | None = None, domain: str | None = None
    ) -> dict[str, Any]:
        """Validate source credibility (alias for assess_credibility)."""
        return self.assess_credibility(content, domain, source_url)

    def assess_credibility(
        self,
        content: str | None = None,
        domain: str | None = None,
        source_url: str | None = None,
    ) -> dict[str, Any]:
        """
        Assess source credibility using domain analysis and content evaluation.

        Args:
            content: Source content
            domain: Domain name
            source_url: Full source URL

        Returns:
            Credibility assessment results
        """
        try:
            # Extract domain if not provided
            if not domain and source_url:
                try:
                    from urllib.parse import urlparse

                    domain = urlparse(source_url).netloc.lower()
                except Exception:
                    domain = None

            # Domain-based credibility assessment
            domain_score = self._assess_domain_credibility(domain) if domain else 0.5

            # Content-based credibility if available
            content_score = 0.5
            if content and self.roberta_model:
                try:
                    # Use RoBERTa for content credibility assessment
                    result = self.roberta_model(content[:512])
                    scores = {item["label"]: item["score"] for item in result}
                    # Assume LABEL_1 is more credible (this is model-dependent)
                    content_score = scores.get("LABEL_1", 0.5)
                except Exception as e:
                    self.logger.warning(f"RoBERTa credibility assessment failed: {e}")

            # Combine scores
            credibility_score = (domain_score * 0.7) + (content_score * 0.3)

            # Determine reliability level
            if credibility_score >= 0.8:
                reliability = "high"
            elif credibility_score >= 0.6:
                reliability = "medium"
            elif credibility_score >= 0.4:
                reliability = "low"
            else:
                reliability = "unreliable"

            return {
                "credibility_score": float(credibility_score),
                "reliability": reliability,
                "domain_score": float(domain_score),
                "content_score": float(content_score),
                "domain": domain,
                "source_url": source_url,
            }

        except Exception as e:
            self.logger.error(f"Credibility assessment failed: {e}")
            return {"error": str(e)}

    def _assess_domain_credibility(self, domain: str) -> float:
        """Assess domain credibility based on known patterns."""
        if not domain:
            return 0.3

        domain_lower = domain.lower()

        # High credibility domains
        high_credibility = [
            ".edu",
            ".gov",
            ".org",
            ".ac.",
            ".mil",
            "bbc.com",
            "reuters.com",
            "apnews.com",
            "npr.org",
            "nytimes.com",
            "washingtonpost.com",
            "wsj.com",
        ]

        # Low credibility indicators
        low_credibility = [
            "fake",
            "hoax",
            "satire",
            "joke",
            "parody",
            "buzzfeed",
            "huffpost",
            "breitbart",
        ]

        # Check for high credibility indicators
    async def comprehensive_fact_check(
        self,
        content: str,
        source_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Perform comprehensive fact-checking on full articles.

        Args:
            content: Full article content
            source_url: Article source URL
            metadata: Article metadata

        Returns:
            Comprehensive fact-checking results
        """
        try:
            # Extract claims
            claims_analysis = self.extract_claims(content)

            # Verify facts (Now Async)
            fact_verification = await self.verify_facts(content, source_url)

            # Assess credibility
            credibility = self.assess_credibility(content, None, source_url)



            # Check for contradictions (if multiple sources in metadata)
            contradictions = {"contradictions_found": 0, "analysis": []}
            if metadata and "related_sources" in metadata:
                related_texts = metadata["related_sources"]
                if len(related_texts) > 1:
                    contradictions = self.detect_contradictions(
                        [content] + related_texts
                    )

            # Calculate overall score
            weights = {
                "fact_verification": 0.5,
                "credibility": 0.3,
                "claims_quality": 0.2,
            }

            fact_score = fact_verification.get("verification_score", 0.5)
            credibility_score = credibility.get("credibility_score", 0.5)
            claims_score = min(
                1.0, len(claims_analysis.get("claims", [])) / 10.0
            )  # Normalize by expected claims

            overall_score = (
                fact_score * weights["fact_verification"]
                + credibility_score * weights["credibility"]
                + claims_score * weights["claims_quality"]
            )

            return {
                "overall_score": float(overall_score),
                "fact_verification": fact_verification,
                "credibility_assessment": credibility,
                "claims_analysis": claims_analysis,
                "contradictions_analysis": contradictions,
                "metadata_analysis": metadata or {},
                "processing_timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Comprehensive fact-check failed: {e}")
            return {"error": str(e)}

    def extract_claims(self, content: str) -> dict[str, Any]:
        """
        Extract verifiable claims from text content.

        Args:
            content: Text content to analyze

        Returns:
            Extracted claims and analysis
        """
        try:
            claims = []

            if self.spacy_nlp:
                # Use spaCy for claim extraction
                doc = self.spacy_nlp(content)

                # Extract sentences that contain factual claims
                for sent in doc.sents:
                    sent_text = sent.text.strip()

                    # Heuristics for claim identification
                    if self._is_potential_claim(sent_text):
                        claims.append(sent_text)

            else:
                # Fallback: split by sentences and filter
                sentences = re.split(r"[.!?]+", content)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if len(sentence) > 20 and self._is_potential_claim(sentence):
                        claims.append(sentence)

            # Limit to reasonable number
            claims = claims[:50] if len(claims) > 50 else claims

            return {
                "claims": claims,
                "claim_count": len(claims),
                "extraction_method": "spacy" if self.spacy_nlp else "heuristic",
            }

        except Exception as e:
            self.logger.error(f"Claim extraction failed: {e}")
            return {"error": str(e), "claims": [], "claim_count": 0}

    def _is_potential_claim(self, text: str) -> bool:
        """Determine if text contains a potential verifiable claim."""
        text_lower = text.lower()

        # Claim indicators
        claim_indicators = [
            "is",
            "was",
            "were",
            "are",
            "has",
            "have",
            "had",
            "according to",
            "reported",
            "stated",
            "announced",
            "study",
            "research",
            "data",
            "evidence",
            "found",
            "confirmed",
            "verified",
            "proved",
            "showed",
        ]

        # Question indicators (not claims)
        question_indicators = ["?", "what", "how", "why", "when", "where", "who"]

        has_claim_indicator = any(
            indicator in text_lower for indicator in claim_indicators
        )
        has_question = any(indicator in text_lower for indicator in question_indicators)

        return has_claim_indicator and not has_question and len(text.split()) > 3

    def detect_contradictions(self, text_passages: list[str]) -> dict[str, Any]:
        """
        Detect logical contradictions between text passages.

        Args:
            text_passages: List of text passages to analyze

        Returns:
            Contradiction analysis results
        """
        try:
            if len(text_passages) < 2:
                return {"contradictions_found": 0, "analysis": []}

            contradictions = []

            if self.sentence_transformer:
                # Use semantic similarity to detect contradictions
                embeddings = self.sentence_transformer.encode(text_passages)

                # Compare each pair
                for i in range(len(text_passages)):
                    for j in range(i + 1, len(text_passages)):
                        similarity = np.dot(embeddings[i], embeddings[j]) / (
                            np.linalg.norm(embeddings[i])
                            * np.linalg.norm(embeddings[j])
                        )

                        # Low similarity might indicate contradiction
                        if similarity < 0.3:  # Threshold for potential contradiction
                            contradictions.append(
                                {
                                    "passage_1": text_passages[i][:200] + "..."
                                    if len(text_passages[i]) > 200
                                    else text_passages[i],
                                    "passage_2": text_passages[j][:200] + "..."
                                    if len(text_passages[j]) > 200
                                    else text_passages[j],
                                    "similarity_score": float(similarity),
                                    "potential_contradiction": True,
                                }
                            )

            else:
                # Fallback: keyword-based contradiction detection
                contradictions = self._keyword_contradiction_detection(text_passages)

            return {
                "contradictions_found": len(contradictions),
                "analysis": contradictions,
                "method": "semantic" if self.sentence_transformer else "keyword",
            }

        except Exception as e:
            self.logger.error(f"Contradiction detection failed: {e}")
            return {"error": str(e), "contradictions_found": 0, "analysis": []}

    def _keyword_contradiction_detection(
        self, text_passages: list[str]
    ) -> list[dict[str, Any]]:
        """Keyword-based contradiction detection fallback."""
        contradictions = []

        # Simple contradiction patterns
        contradiction_pairs = [
            ("increased", "decreased"),
            ("rose", "fell"),
            ("gained", "lost"),
            ("won", "lost"),
            ("yes", "no"),
            ("true", "false"),
            ("confirmed", "denied"),
        ]

        for i in range(len(text_passages)):
            text1_lower = text_passages[i].lower()
            for j in range(i + 1, len(text_passages)):
                text2_lower = text_passages[j].lower()

                # Check for contradictory keyword pairs
                for pos, neg in contradiction_pairs:
                    if pos in text1_lower and neg in text2_lower:
                        contradictions.append(
                            {
                                "passage_1": text_passages[i][:200] + "..."
                                if len(text_passages[i]) > 200
                                else text_passages[i],
                                "passage_2": text_passages[j][:200] + "..."
                                if len(text_passages[j]) > 200
                                else text_passages[j],
                                "contradiction_type": f"{pos}_vs_{neg}",
                                "potential_contradiction": True,
                            }
                        )
                        break

        return contradictions

    async def validate_is_news_gpu(self, content: str) -> dict[str, Any]:
        """GPU-accelerated news content validation."""
        try:
            if self.tensorrt_engine:
                return await self.tensorrt_engine.validate_news_content(content)
            else:
                # Fallback to CPU
                return await self._validate_is_news_cpu(content)
        except Exception as e:
            self.logger.warning(f"GPU news validation failed: {e}")
            return await self._validate_is_news_cpu(content)

    async def _validate_is_news_cpu(self, content: str) -> dict[str, Any]:
        """CPU-based news validation."""
        try:
            content_lower = content.lower()

            # News content indicators
            news_keywords = [
                "breaking",
                "news",
                "report",
                "headline",
                "announced",
                "according to",
                "sources",
                "said",
                "stated",
                "reported",
            ]

            # Structure indicators
            structure_indicators = [" - ", " | ", "\n\n", "by ", "published", "updated"]

            keyword_score = sum(
                1 for keyword in news_keywords if keyword in content_lower
            ) / len(news_keywords)
            structure_score = sum(
                1 for indicator in structure_indicators if indicator in content
            ) / len(structure_indicators)
            length_score = min(
                1.0, len(content) / 500.0
            )  # News articles are typically substantial

            is_news_score = (
                keyword_score * 0.4 + structure_score * 0.3 + length_score * 0.3
            )

            return {
                "is_news": is_news_score > 0.5,
                "confidence": float(is_news_score),
                "news_score": float(keyword_score),
                "structure_score": float(structure_score),
                "length_score": float(length_score),
                "method": "cpu_analysis",
                "analysis_timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error(f"CPU news validation failed: {e}")
            return {"error": str(e), "is_news": False, "method": "cpu_fallback"}

    async def verify_claims_gpu(
        self, claims: list[str], sources: list[str]
    ) -> dict[str, Any]:
        """GPU-accelerated batch claim verification."""
        try:
            if self.tensorrt_engine:
                return await self.tensorrt_engine.verify_claims_batch(claims, sources)
            else:
                return await self._verify_claims_cpu(claims, sources)
        except Exception as e:
            self.logger.warning(f"GPU claims verification failed: {e}")
            return await self._verify_claims_cpu(claims, sources)

    async def _verify_claims_cpu(
        self, claims: list[str], sources: list[str]
    ) -> dict[str, Any]:
        """CPU-based batch claim verification."""
        try:
            source_text = "\n".join(sources) if sources else ""
            results = {}

            for claim in claims:
                # Simple verification based on source matching
                verification_score = 0.5

                if source_text:
                    claim_words = set(claim.lower().split())
                    source_words = set(source_text.lower().split())
                    overlap = len(claim_words.intersection(source_words))
                    verification_score = min(1.0, overlap / len(claim_words) * 2)

                results[claim] = {
                    "verification_score": verification_score,
                    "classification": "verified"
                    if verification_score > 0.6
                    else "questionable",
                    "confidence": verification_score,
                    "method": "cpu_batch",
                }

            return {
                "results": results,
                "total_claims": len(claims),
                "verified_claims": sum(
                    1 for r in results.values() if r["classification"] == "verified"
                ),
                "method": "cpu_batch",
                "analysis_timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error(f"CPU claims verification failed: {e}")
            return {"error": str(e), "method": "cpu_batch"}

    def log_feedback(self, feedback_type: str, feedback_data: dict[str, Any]):
        """Log user feedback for model improvement."""
        try:
            if not self.config.training_config["feedback_collection"]:
                return {"status": "feedback_collection_disabled"}

            feedback_entry = {
                "type": feedback_type,
                "data": feedback_data,
                "timestamp": datetime.now().isoformat(),
                "session_id": os.getenv("SESSION_ID", "unknown"),
            }

            self.feedback_buffer.append(feedback_entry)

            # Trigger training update if buffer is full
            if len(self.feedback_buffer) >= 10:  # Configurable threshold
                self._process_feedback_buffer()

            return {
                "status": "feedback_logged",
                "buffer_size": len(self.feedback_buffer),
            }

        except Exception as e:
            self.logger.error(f"Feedback logging failed: {e}")
            return {"error": str(e)}

    def _process_feedback_buffer(self):
        """Process accumulated feedback for model training."""
        try:
            if not self.feedback_buffer:
                return

            # Add to training data
            self.training_data.extend(self.feedback_buffer)

            # Limit training data size
            max_samples = self.config.training_config["max_training_samples"]
            if len(self.training_data) > max_samples:
                self.training_data = self.training_data[-max_samples:]

            # Clear buffer
            self.feedback_buffer.clear()

            self.logger.info(
                f"✅ Processed {len(self.feedback_buffer)} feedback entries for training"
            )

        except Exception as e:
            self.logger.error(f"Feedback processing failed: {e}")

    def correct_verification(
        self,
        claim: str,
        context: str | None = None,
        incorrect_classification: str = "",
        correct_classification: str = "",
        priority: int = 2,
    ) -> dict[str, Any]:
        """Submit user correction for fact verification."""
        try:
            correction_data = {
                "claim": claim,
                "context": context,
                "incorrect_classification": incorrect_classification,
                "correct_classification": correct_classification,
                "priority": priority,
                "timestamp": datetime.now().isoformat(),
            }

            self.log_feedback("verification_correction", correction_data)

            return {
                "status": "correction_submitted",
                "correction_id": len(self.training_data),
            }

        except Exception as e:
            self.logger.error(f"Verification correction failed: {e}")
            return {"error": str(e)}

    def correct_credibility(
        self,
        source_text: str | None = None,
        domain: str = "",
        incorrect_reliability: str = "",
        correct_reliability: str = "",
        priority: int = 2,
    ) -> dict[str, Any]:
        """Submit user correction for credibility assessment."""
        try:
            correction_data = {
                "source_text": source_text,
                "domain": domain,
                "incorrect_reliability": incorrect_reliability,
                "correct_reliability": correct_reliability,
                "priority": priority,
                "timestamp": datetime.now().isoformat(),
            }

            self.log_feedback("credibility_correction", correction_data)

            return {
                "status": "correction_submitted",
                "correction_id": len(self.training_data),
            }

        except Exception as e:
            self.logger.error(f"Credibility correction failed: {e}")
            return {"error": str(e)}

    def get_training_status(self) -> dict[str, Any]:
        """Get online training status."""
        try:
            return {
                "online_training_enabled": self.config.training_config[
                    "online_training"
                ],
                "feedback_collection_enabled": self.config.training_config[
                    "feedback_collection"
                ],
                "training_data_size": len(self.training_data),
                "feedback_buffer_size": len(self.feedback_buffer),
                "last_model_update": datetime.fromtimestamp(
                    self.last_model_update
                ).isoformat(),
                "next_update_due": datetime.fromtimestamp(
                    self.last_model_update
                    + self.config.training_config["model_update_interval"]
                ).isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Training status retrieval failed: {e}")
            return {"error": str(e)}

    def force_model_update(self) -> dict[str, Any]:
        """Force immediate model update (admin function)."""
        try:
            if not self.config.training_config["online_training"]:
                return {"status": "online_training_disabled"}

            # Process any pending feedback
            self._process_feedback_buffer()

            # Trigger model update (simplified - in real implementation would retrain models)
            self.last_model_update = time.time()

            self.logger.info("🔄 Forced model update completed")

            return {
                "status": "model_updated",
                "training_data_processed": len(self.training_data),
                "update_timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Model update failed: {e}")
            return {"error": str(e)}

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached result is still valid."""
        if not self.config.performance_config["cache_enabled"]:
            return False

        if cache_key not in self.cache_timestamps:
            return False

        cache_age = time.time() - self.cache_timestamps[cache_key]
        return cache_age < self.config.performance_config["cache_ttl"]

    def _cache_result(self, cache_key: str, result: dict[str, Any]):
        """Cache a result with timestamp."""
        if self.config.performance_config["cache_enabled"]:
            self.cache[cache_key] = result
            self.cache_timestamps[cache_key] = time.time()

            # Limit cache size
            if len(self.cache) > 1000:  # Configurable limit
                # Remove oldest entries
                oldest_keys = sorted(
                    self.cache_timestamps.keys(), key=lambda k: self.cache_timestamps[k]
                )[:100]
                for key in oldest_keys:
                    del self.cache[key]
                    del self.cache_timestamps[key]


