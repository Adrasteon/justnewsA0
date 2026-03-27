"""
Analyst Engine - Core Quantitative Analysis Engine

This engine provides comprehensive quantitative analysis capabilities for news content,
including entity extraction, statistical analysis, sentiment/bias detection, and trend analysis.

Features:
- Entity extraction using spaCy with transformer fallbacks
- Text statistics and readability analysis
- GPU-accelerated sentiment and bias analysis
- Key metrics extraction (financial, temporal, statistical)
- Content trend analysis across multiple articles
- Production-ready with robust error handling and fallbacks

Architecture: Streamlined for production use with GPU acceleration and CPU fallbacks.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import re
import statistics
import time
import warnings
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from common.observability import get_logger
from common.tracing import traced

try:
    from .model_adapter import AdapterResult
    from .model_adapter import AnalystModelAdapter as MistralAdapter
except Exception:  # pragma: no cover - optional dependency wiring
    MistralAdapter = None  # type: ignore
    AdapterResult = Any  # type: ignore

if TYPE_CHECKING:
    from .schemas import SourceFactCheck

# Configure centralized logging
logger = get_logger(__name__)

# Suppress specific warnings for production deployment, but not during test runs
if os.environ.get("PYTEST_RUNNING") != "1":
    warnings.filterwarnings("ignore", category=UserWarning, module="torch")
    warnings.filterwarnings("ignore", category=FutureWarning, module="transformers")

# Dependency detection
try:
    _spacy_spec = importlib.util.find_spec("spacy")
except ValueError:
    _spacy_spec = None
HAS_SPACY = _spacy_spec is not None

try:
    _transformers_spec = importlib.util.find_spec("transformers")
except ValueError:
    _transformers_spec = None
HAS_TRANSFORMERS = _transformers_spec is not None

try:
    _torch_spec = importlib.util.find_spec("torch")
except ValueError:
    _torch_spec = None
TORCH_AVAILABLE = _torch_spec is not None

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None


# Lazy imports for heavy dependencies
def _import_spacy():
    """Lazy import spaCy."""
    if HAS_SPACY:
        import spacy

        return spacy
    return None


def _import_transformers_pipeline():
    """Lazy import transformers pipeline."""
    if HAS_TRANSFORMERS and TORCH_AVAILABLE:
        import torch
        from transformers import pipeline

        return pipeline, torch
    return None, None


class AnalystConfig:
    """Configuration for Analyst Engine."""

    def __init__(self):
        self.spacy_model = "en_core_web_sm"
        self.ner_fallback_model = "dbmdz/bert-large-cased-finetuned-conll03-english"
        self.sentiment_model = "cardiffnlp/twitter-roberta-base-sentiment-latest"
        self.bias_model = "unitary/toxic-bert"
        self.feedback_log = os.environ.get(
            "ANALYST_FEEDBACK_LOG", "feedback_analyst.log"
        )
        self.max_text_length = 1000000  # 1MB limit
        self.batch_size = 16
        self.use_gpu = True
        self.memory_threshold_gb = 1.0


class AnalystEngine:
    """
    Analyst Engine - Core quantitative analysis for news content.

    This engine specializes in extracting quantitative insights from news content,
    including entities, statistics, sentiment, bias, and trends.

    Key Features:
    - Entity extraction with spaCy and transformer fallbacks
    - Statistical text analysis and readability metrics
    - GPU-accelerated sentiment and bias detection
    - Key metrics extraction (financial, temporal, statistical)
    - Trend analysis across content collections
    - Production-ready with comprehensive error handling
    """

    def __init__(self, config: AnalystConfig | None = None):
        """Initialize the Analyst engine with configuration."""
        self.config = config or AnalystConfig()

        # Model instances
        self.spacy_nlp = None
        self.ner_pipeline = None
        self.gpu_analyst = None
        self.mistral_adapter: MistralAdapter | None = None
        self._mistral_cache_key: str | None = None
        self._mistral_cache_result: AdapterResult | None = None
        self._traceability_db_service: Any | None = None

        # Processing stats
        self.processing_stats = {
            "total_processed": 0,
            "entities_extracted": 0,
            "sentiment_analyses": 0,
            "bias_detections": 0,
            "average_processing_time": 0.0,
        }

        # Initialize components
        self._initialize_models()
        logger.info(
            "✅ Analyst Engine initialized with quantitative analysis capabilities"
        )

    def __enter__(self) -> AnalystEngine:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self._cleanup_resources()
        if exc_type is not None:
            logger.error(
                f"Analyst Engine exited with error: {exc_type.__name__}: {exc_val}"
            )
        return False

    async def __aenter__(self) -> AnalystEngine:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        self._cleanup_resources()
        if exc_type is not None:
            logger.error(
                f"Analyst Engine async exited with error: {exc_type.__name__}: {exc_val}"
            )
        return False

    @traced(name="analyst.init_models")
    def _initialize_models(self):
        """Initialize analysis models and components."""
        try:
            self._initialize_spacy()
            self._initialize_ner_fallback()
            self._initialize_gpu_analyst()
            self._initialize_mistral_adapter()
            logger.info("✅ Analyst models initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing models: {e}")
            self._initialize_fallback_systems()

    def _initialize_spacy(self):
        """Initialize spaCy model for entity extraction."""
        if not HAS_SPACY:
            logger.warning("spaCy not available - using fallback NER")
            return

        try:
            spacy = _import_spacy()
            if spacy:
                self.spacy_nlp = spacy.load(self.config.spacy_model)
                logger.info(f"✅ Loaded spaCy model: {self.config.spacy_model}")
        except Exception as e:
            logger.warning(f"Could not load spaCy model {self.config.spacy_model}: {e}")

    def _initialize_ner_fallback(self):
        """Initialize transformer-based NER pipeline as fallback."""
        if not HAS_TRANSFORMERS:
            logger.warning("Transformers not available for NER fallback")
            return

        try:
            pipeline_fn, torch_mod = _import_transformers_pipeline()
            if pipeline_fn and torch_mod:
                device = 0 if torch_mod.cuda.is_available() else -1
                self.ner_pipeline = pipeline_fn(
                    "ner",
                    model=self.config.ner_fallback_model,
                    aggregation_strategy="simple",
                    device=device,
                )
                logger.info(f"✅ Loaded NER pipeline: {self.config.ner_fallback_model}")
        except Exception as e:
            logger.warning(f"Could not load NER pipeline: {e}")

    def _initialize_gpu_analyst(self):
        """Initialize GPU-accelerated analyst for sentiment/bias analysis."""
        if not self.config.use_gpu:
            logger.info("GPU analysis disabled by configuration")
            return

        try:
            from .gpu_analyst import get_gpu_analyst

            self.gpu_analyst = get_gpu_analyst()
            logger.info("✅ GPU analyst initialized for sentiment/bias analysis")
        except Exception as e:
            logger.warning(f"Could not initialize GPU analyst: {e}")

    def _initialize_mistral_adapter(self):
        """Try to prepare the high-accuracy Mistral adapter helper."""
        if MistralAdapter is None:
            logger.info(
                "Mistral adapter dependencies unavailable; continuing with legacy models"
            )
            return

        try:
            # Use the shared ModelAdapter (Qwen backed) wrapper
            self.mistral_adapter = MistralAdapter()
            if getattr(self.mistral_adapter, "enabled", True):
                logger.info(
                    "Qwen adapter enabled for Analyst; loading lazily"
                )
            else:
                logger.info("Qwen adapter explicitly disabled via env variable")
        except Exception as exc:
            logger.warning(f"Failed to set up Analyst Mistral adapter: {exc}")
            self.mistral_adapter = None

    def _get_mistral_result(self, text: str) -> AdapterResult | None:
        """Fetch (and cache) the adapter result for the given text."""
        if not self.mistral_adapter or not text.strip():
            return None

        cache_key = hashlib.sha1(text.encode("utf-8")).hexdigest()
        if self._mistral_cache_key == cache_key and self._mistral_cache_result:
            return self._mistral_cache_result

        try:
            result = self.mistral_adapter.classify(text)
        except Exception as exc:
            logger.warning(f"Mistral adapter inference failed: {exc}")
            self._mistral_cache_key = None
            self._mistral_cache_result = None
            return None

        if result:
            self._mistral_cache_key = cache_key
            self._mistral_cache_result = result
            return result

        self._mistral_cache_key = None
        self._mistral_cache_result = None
        return None

    def _initialize_fallback_systems(self):
        """Initialize fallback analysis systems."""
        logger.info("Initializing fallback analysis systems...")
        self.fallback_mode = True

    def _cleanup_resources(self):
        """Clean up resources and GPU memory."""
        try:
            if self.gpu_analyst:
                from .gpu_analyst import cleanup_gpu_analyst

                cleanup_gpu_analyst()
            logger.info("🧹 Analyst Engine resources cleaned up")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")

    def _validate_text_input(self, text: str) -> bool:
        """Validate text input for processing."""
        if not isinstance(text, str) or not text.strip():
            return False
        if len(text) > self.config.max_text_length:
            return False
        return True

    def _log_feedback(self, event: str, details: dict[str, Any]) -> None:
        """Log analysis feedback for monitoring and improvement."""
        try:
            timestamp = datetime.now(UTC).isoformat()
            log_entry = {
                "timestamp": timestamp,
                "event": event,
                "details": details,
                "agent": "analyst",
            }

            with open(self.config.feedback_log, "a", encoding="utf-8") as f:
                f.write(f"{json.dumps(log_entry)}\n")
        except Exception as e:
            logger.warning(f"Failed to log feedback: {e}")

    @traced(name="analyst.extract_entities", record_args=True)
    def extract_entities(self, text: str) -> dict[str, Any]:
        """
        Extract named entities from text using spaCy with transformer fallback.

        Args:
            text: Input text for entity extraction

        Returns:
            Dictionary containing entity extraction results
        """
        if not self._validate_text_input(text):
            return {"entities": [], "total_entities": 0, "error": "Invalid text input"}

        start_time = time.time()
        logger.info(f"🔍 Extracting entities from {len(text)} characters")

        entities = []
        processing_method = "none"

        try:
            # Primary: spaCy NER
            if self.spacy_nlp:
                doc = self.spacy_nlp(text)
                for ent in doc.ents:
                    entities.append(
                        {
                            "text": ent.text,
                            "label": ent.label_,
                            "start": int(ent.start_char),
                            "end": int(ent.end_char),
                            "confidence": 0.9,
                            "description": ent.label_,
                        }
                    )
                processing_method = "spacy"

            # Fallback: Transformer NER
            elif self.ner_pipeline:
                text_limited = text[:2000] if len(text) > 2000 else text
                ner_results = self.ner_pipeline(text_limited)

                for result in ner_results:
                    entities.append(
                        {
                            "text": result["word"],
                            "label": result["entity_group"],
                            "start": int(result["start"]),
                            "end": int(result["end"]),
                            "confidence": float(result["score"]),
                            "description": result["entity_group"],
                        }
                    )
                processing_method = "transformer"

            # Last resort: Pattern-based extraction
            else:
                entities = self._extract_entities_patterns(text)
                processing_method = "patterns"

            # Clean and deduplicate entities
            entities = self._clean_entities(entities)

            processing_time = time.time() - start_time
            self.processing_stats["entities_extracted"] += len(entities)
            self.processing_stats["total_processed"] += 1

            result = {
                "entities": entities,
                "total_entities": len(entities),
                "method": processing_method,
                "text_length": len(text),
                "processing_time": processing_time,
            }

            self._log_feedback(
                "extract_entities",
                {
                    "text_length": len(text),
                    "entities_found": len(entities),
                    "method": processing_method,
                    "processing_time": processing_time,
                },
            )

            logger.info(
                f"✅ Extracted {len(entities)} entities using {processing_method}"
            )
            return result

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Entity extraction failed: {e}")

            self._log_feedback(
                "extract_entities_error",
                {
                    "text_length": len(text),
                    "error": str(e),
                    "processing_time": processing_time,
                },
            )

            return {
                "entities": [],
                "total_entities": 0,
                "method": "error",
                "error": str(e),
            }

    def extract_claims(self, text: str) -> list[dict[str, Any]]:
        """
        Extract candidate claims from text using the helper module.
        Wraps agents.analyst.claims.extract_claims for engine usage.
        """
        try:
            from .claims import extract_claims as _extract_claims

            claims = _extract_claims(text)
            # Try to fill in start/end positions if they are None
            for c in claims:
                if c.get("start") is None and c.get("claim_text"):
                    idx = text.find(c["claim_text"])
                    if idx >= 0:
                        c["start"] = int(idx)
                        c["end"] = int(idx + len(c["claim_text"]))
            return claims
        except Exception as e:
            logger.warning(f"Claim extraction failed: {e}")
            return []

    def extract_quotes(self, text: str) -> list[dict[str, Any]]:
        """Extract direct quotes with lightweight attribution hints."""
        if not text:
            return []

        quote_pattern = re.compile(r'"([^"\n]{8,500})"')
        attribution_pattern = re.compile(
            r"([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\s+(said|stated|argued|claimed|told|according to)",
            re.IGNORECASE,
        )

        results: list[dict[str, Any]] = []
        for match in quote_pattern.finditer(text):
            quote_text = match.group(1).strip()
            if not quote_text:
                continue

            window_start = max(0, match.start() - 180)
            window_end = min(len(text), match.end() + 180)
            window = text[window_start:window_end]
            speaker_name = None
            attribution_text = None
            attribution_match = attribution_pattern.search(window)
            if attribution_match:
                speaker_name = attribution_match.group(1).strip()
                attribution_text = attribution_match.group(0).strip()

            results.append(
                {
                    "quote_text": quote_text,
                    "start": int(match.start()),
                    "end": int(match.end()),
                    "speaker_name": speaker_name,
                    "attribution_text": attribution_text,
                    "confidence": 0.72 if attribution_text else 0.55,
                }
            )

        return results

    def extract_attributed_speech(self, text: str) -> dict[str, Any]:
        """Extract statements and quotes with minimal structured attribution."""
        claim_items = self.extract_claims(text)
        quote_items = self.extract_quotes(text)

        statements: list[dict[str, Any]] = []
        for claim in claim_items:
            claim_text = str(claim.get("claim_text") or "").strip()
            if not claim_text:
                continue
            statements.append(
                {
                    "statement_text": claim_text,
                    "start": claim.get("start"),
                    "end": claim.get("end"),
                    "confidence": float(claim.get("confidence", 0.5) or 0.5),
                    "claim_type": claim.get("claim_type"),
                    "is_opinion": bool(claim.get("claim_type") == "opinion"),
                }
            )

        attributed_count = sum(
            1 for quote in quote_items if quote.get("attribution_text")
        ) + sum(1 for statement in statements if statement.get("claim_type") == "attributed")

        total_items = len(quote_items) + len(statements)
        return {
            "statements": statements,
            "quotes": quote_items,
            "attribution_coverage": {
                "total_items": total_items,
                "attributed_items": attributed_count,
                "coverage_ratio": (attributed_count / total_items) if total_items else 0.0,
            },
        }

    def _traceability_persistence_enabled(self) -> bool:
        return (
            str(os.environ.get("ANALYST_TRACEABILITY_PERSIST_ENABLED", "false"))
            .strip()
            .lower()
            in {"1", "true", "yes", "on"}
        )

    def _get_traceability_db_service(self) -> Any | None:
        if self._traceability_db_service is not None:
            return self._traceability_db_service
        try:
            from database.utils.migrated_database_utils import create_database_service

            self._traceability_db_service = create_database_service()
            return self._traceability_db_service
        except Exception as exc:
            logger.warning("Traceability DB service unavailable: %s", exc)
            self._traceability_db_service = None
            return None

    def _persist_traceability_for_article(
        self,
        *,
        article_id: str | None,
        entities: list[dict[str, Any]] | None,
        statements: list[Any],
        quotes: list[Any],
    ) -> None:
        if not self._traceability_persistence_enabled():
            return
        if not article_id:
            return

        try:
            numeric_article_id = int(article_id)
        except Exception:
            logger.debug("Skipping traceability persistence for non-numeric article id: %s", article_id)
            return

        service = self._get_traceability_db_service()
        if service is None:
            return

        try:
            from database.utils.migrated_database_utils import (
                add_quote,
                add_statement,
                link_quote_to_entity,
                link_statement_to_entity,
            )

            linked_entity_ids = [
                int(entity.get("id"))
                for entity in (entities or [])
                if isinstance(entity, dict) and entity.get("id") is not None
            ]

            for statement in statements:
                statement_id = add_statement(
                    service,
                    article_id=numeric_article_id,
                    statement_text=statement.statement_text,
                    source_url=statement.source_url,
                    source_domain=statement.source_domain,
                    speaker_entity_id=statement.speaker_entity_id,
                    attribution_text=statement.attribution_text,
                    span_start=statement.span.start if statement.span else None,
                    span_end=statement.span.end if statement.span else None,
                    extraction_method="analyst_engine",
                    confidence=statement.confidence,
                    perspective_label=statement.perspective_label,
                    is_opinion=statement.is_opinion,
                    counts_as_factual_corroboration=statement.counts_as_factual_corroboration,
                    metadata=statement.metadata,
                )
                if statement_id:
                    for entity_id in linked_entity_ids:
                        link_statement_to_entity(
                            service,
                            statement_id=int(statement_id),
                            entity_id=entity_id,
                            relation_type="mentioned",
                        )

            for quote in quotes:
                quote_id = add_quote(
                    service,
                    article_id=numeric_article_id,
                    quote_text=quote.quote_text,
                    source_url=quote.source_url,
                    source_domain=quote.source_domain,
                    speaker_entity_id=quote.speaker_entity_id,
                    attribution_text=quote.attribution_text,
                    span_start=quote.span.start if quote.span else None,
                    span_end=quote.span.end if quote.span else None,
                    extraction_method="analyst_engine",
                    confidence=quote.confidence,
                    perspective_label=quote.perspective_label,
                    is_opinion=quote.is_opinion,
                    counts_as_factual_corroboration=quote.counts_as_factual_corroboration,
                    metadata=quote.metadata,
                )
                if quote_id:
                    for entity_id in linked_entity_ids:
                        link_quote_to_entity(
                            service,
                            quote_id=int(quote_id),
                            entity_id=entity_id,
                            relation_type="mentioned",
                        )
        except Exception as exc:
            logger.warning("Traceability persistence failed for article %s: %s", article_id, exc)

    def generate_analysis_report(
        self,
        texts: list[str],
        article_ids: list[str] | None = None,
        cluster_id: str | None = None,
        enable_fact_check: bool = True,
    ) -> dict[str, Any]:
        """
        Generate an AnalysisReport for a cluster of texts.

        Returns a dictionary matching the AnalysisReport schema with
        per-article analysis and aggregate metrics.

        Args:
            texts: List of article texts to analyze
            article_ids: Optional list of article IDs
            cluster_id: Optional cluster identifier
            enable_fact_check: Whether to run per-article fact-checking (default: True)
        """
        try:
            from .schemas import (
                AnalysisReport,
                AttributedQuote,
                AttributedStatement,
                AttributionSpan,
                BalanceAssessment,
                Claim,
                PerArticleAnalysis,
            )

            per_article_results = []
            sentiments = []
            biases = []
            all_entities = []
            source_fact_checks = []
            all_statements: list[AttributedStatement] = []
            all_quotes: list[AttributedQuote] = []

            for i, text in enumerate(texts or []):
                article_id = (
                    (article_ids or [None] * len(texts))[i] if article_ids else None
                )
                start_time = time.time()

                sentiment = self.analyze_sentiment(text)
                bias = self.detect_bias(text)
                entities = self.extract_entities(text).get("entities", [])
                claim_dicts = self.extract_claims(text)
                speech = self.extract_attributed_speech(text)
                claims = [
                    Claim(
                        **{
                            k: v
                            for k, v in c.items()
                            if k
                            in {
                                "claim_text",
                                "start",
                                "end",
                                "confidence",
                                "claim_type",
                            }
                        }
                    )
                    for c in claim_dicts
                ]

                statements = [
                    AttributedStatement(
                        statement_text=item.get("statement_text", ""),
                        attribution_text=item.get("claim_type"),
                        source_url=article_id,
                        confidence=float(item.get("confidence", 0.5) or 0.5),
                        is_opinion=bool(item.get("is_opinion", False)),
                        counts_as_factual_corroboration=not bool(
                            item.get("is_opinion", False)
                        ),
                        span=AttributionSpan(
                            start=item.get("start"),
                            end=item.get("end"),
                        ),
                        metadata={"claim_type": item.get("claim_type")},
                    )
                    for item in speech.get("statements", [])
                    if item.get("statement_text")
                ]

                quotes = [
                    AttributedQuote(
                        quote_text=item.get("quote_text", ""),
                        speaker_name=item.get("speaker_name"),
                        attribution_text=item.get("attribution_text"),
                        source_url=article_id,
                        confidence=float(item.get("confidence", 0.5) or 0.5),
                        counts_as_factual_corroboration=bool(
                            item.get("attribution_text")
                        ),
                        span=AttributionSpan(
                            start=item.get("start"),
                            end=item.get("end"),
                        ),
                    )
                    for item in speech.get("quotes", [])
                    if item.get("quote_text")
                ]

                all_statements.extend(statements)
                all_quotes.extend(quotes)

                self._persist_traceability_for_article(
                    article_id=article_id,
                    entities=entities,
                    statements=statements,
                    quotes=quotes,
                )

                # Per-article fact-checking (mandatory per feature doc)
                source_fact_check = None
                if enable_fact_check:
                    source_fact_check = self._run_per_article_fact_check(
                        text, article_id
                    )
                    if source_fact_check:
                        source_fact_checks.append(source_fact_check)

                processing_time = time.time() - start_time

                per_article_results.append(
                    PerArticleAnalysis(
                        article_id=article_id,
                        language="en",
                        sentiment=sentiment,
                        bias=bias,
                        entities=entities,
                        claims=claims,
                        statements=statements,
                        quotes=quotes,
                        attribution_coverage=speech.get("attribution_coverage"),
                        source_fact_check=source_fact_check,
                        processing_time_seconds=processing_time,
                    )
                )

                if (
                    sentiment
                    and isinstance(sentiment, dict)
                    and sentiment.get("confidence") is not None
                ):
                    sentiments.append(sentiment.get("confidence", 0.0))
                if (
                    bias
                    and isinstance(bias, dict)
                    and bias.get("bias_score") is not None
                ):
                    biases.append(bias.get("bias_score", 0.0))
                if entities:
                    all_entities.extend(entities)

            avg_sentiment = None
            if sentiments:
                avg_sentiment = {
                    "average_confidence": sum(sentiments) / len(sentiments)
                }

            avg_bias = None
            if biases:
                avg_bias = {"average_bias_score": sum(biases) / len(biases)}

            unique_entities = []
            seen = set()
            for ent in all_entities:
                t = ent.get("text", "").lower().strip()
                if t and t not in seen:
                    seen.add(t)
                    unique_entities.append(ent)

            primary_claims = []
            # Simple heuristic: take highest confidence claims from each article up to 6
            for p in per_article_results:
                top = sorted((p.claims or []), key=lambda c: c.confidence, reverse=True)
                primary_claims.extend(top[:1])
            primary_claims = primary_claims[:6]

            # Aggregate cluster-level fact-check summary
            cluster_fact_check_summary = None
            if source_fact_checks:
                cluster_fact_check_summary = self._aggregate_fact_check_summary(
                    source_fact_checks
                )

            total_speech_items = len(all_statements) + len(all_quotes)
            opinion_items_count = sum(1 for statement in all_statements if statement.is_opinion)
            corroborating_items_count = sum(
                1 for statement in all_statements if statement.counts_as_factual_corroboration
            ) + sum(
                1 for quote in all_quotes if quote.counts_as_factual_corroboration
            )

            balance_assessment = BalanceAssessment(
                disputed_topic=False,
                min_distinct_sides=2,
                distinct_sides_found=min(2, len({(s.perspective_label or "unknown") for s in all_statements}) if all_statements else 0),
                policy_result="warning" if total_speech_items == 0 else "pass",
                opinion_items_count=opinion_items_count,
                corroborating_items_count=corroborating_items_count,
                details={
                    "generated_by": "analyst_engine",
                    "total_speech_items": total_speech_items,
                },
            )

            report = AnalysisReport(
                cluster_id=cluster_id,
                language="en",
                articles_count=len(texts or []),
                aggregate_sentiment=avg_sentiment,
                aggregate_bias=avg_bias,
                entities=unique_entities,
                primary_claims=primary_claims,
                attributed_statements=all_statements,
                attributed_quotes=all_quotes,
                balance_assessment=balance_assessment,
                attribution_summary={
                    "total_statements": len(all_statements),
                    "total_quotes": len(all_quotes),
                    "total_speech_items": total_speech_items,
                },
                per_article=per_article_results,
                source_fact_checks=source_fact_checks,
                cluster_fact_check_summary=cluster_fact_check_summary,
            )

            return report.to_dict()
        except Exception as e:
            logger.error(f"Failed to generate analysis report: {e}")
            return {"error": str(e)}

    def _run_per_article_fact_check(
        self, text: str, article_id: str | None = None
    ) -> SourceFactCheck | None:
        """
        Run comprehensive fact-check on a single article.

        Calls the modern analyst audit module against the fact-check service.
        Returns SourceFactCheck object with results.
        """
        try:
            from .audit import audit_text
            from .schemas import ClaimVerdict, SourceFactCheck

            try:
                result = asyncio.run(audit_text(text, max_claims=5))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(audit_text(text, max_claims=5))
                finally:
                    loop.close()

            if not result or "error" in result:
                logger.error(
                    f"Fact-check failed for article {article_id}: {result.get('error')}"
                )
                return None

            overall_score = float(result.get("score", 0.0) or 0.0)
            details = result.get("details", {}) if isinstance(result.get("details"), dict) else {}
            verdicts = result.get("verdicts", []) if isinstance(result.get("verdicts"), list) else []

            claim_items = []
            for verdict_entry in verdicts[:10]:
                if not isinstance(verdict_entry, dict):
                    continue
                fact_check = verdict_entry.get("fact_check", {})
                if not isinstance(fact_check, dict):
                    fact_check = {}
                claim_items.append(
                    {
                        "text": verdict_entry.get("claim", ""),
                        "verdict": fact_check.get("verdict", "Uncertain"),
                        "confidence": float(fact_check.get("confidence", verdict_entry.get("confidence", 0.0)) or 0.0),
                        "evidence": fact_check.get("evidence"),
                    }
                )

            fact_verification = {
                "verification_score": overall_score,
                "claims_analyzed": int(details.get("checked_count", len(claim_items)) or 0),
                "verdict_breakdown": details.get("verdict_breakdown", {}),
            }
            credibility_assessment = {
                "credibility_score": overall_score,
            }
            claims_analysis = {
                "claims": claim_items,
                "claim_count": int(details.get("checked_count", len(claim_items)) or len(claim_items)),
            }

            # Determine fact_check_status based on overall_score
            if overall_score >= 0.8:
                status = "passed"
            elif overall_score >= 0.6:
                status = "needs_review"
            else:
                status = "failed"

            # Extract claim verdicts
            claim_verdicts = []
            for claim in claims_analysis.get("claims", [])[:10]:  # Limit to 10 claims
                claim_verdicts.append(
                    ClaimVerdict(
                        claim_text=claim.get("text", ""),
                        verdict=claim.get("verdict", "unverifiable"),
                        confidence=claim.get("confidence", 0.0),
                        evidence=claim.get("evidence"),
                        timestamp=result.get("processing_timestamp"),
                    )
                )

            return SourceFactCheck(
                article_id=article_id or "unknown",
                fact_check_status=status,
                overall_score=overall_score,
                claim_verdicts=claim_verdicts,
                credibility_score=credibility_assessment.get("credibility_score"),
                source_url=article_id,
                fact_check_trace={
                    "fact_verification": fact_verification,
                    "credibility_assessment": credibility_assessment,
                    "claims_analyzed": claims_analysis.get("claim_count", 0),
                    "contradictions": result.get("contradictions_analysis", {}),
                },
            )

        except Exception as e:
            logger.error(f"Per-article fact-check failed for {article_id}: {e}")
            return None

    def _aggregate_fact_check_summary(
        self, source_fact_checks: list[SourceFactCheck]
    ) -> dict[str, Any]:
        """
        Aggregate cluster-level fact-check summary from per-article results.

        Returns summary dict with:
        - total_articles_checked
        - passed_count, failed_count, needs_review_count
        - average_overall_score
        - articles_flagged (list of article_ids with status=failed)
        """
        if not source_fact_checks:
            return {}

        total = len(source_fact_checks)
        passed = sum(
            1 for sfc in source_fact_checks if sfc.fact_check_status == "passed"
        )
        failed = sum(
            1 for sfc in source_fact_checks if sfc.fact_check_status == "failed"
        )
        needs_review = sum(
            1 for sfc in source_fact_checks if sfc.fact_check_status == "needs_review"
        )

        avg_score = (
            sum(sfc.overall_score for sfc in source_fact_checks) / total
            if total > 0
            else 0.0
        )

        flagged = [
            sfc.article_id
            for sfc in source_fact_checks
            if sfc.fact_check_status == "failed"
        ]

        return {
            "total_articles_checked": total,
            "passed_count": passed,
            "failed_count": failed,
            "needs_review_count": needs_review,
            "average_overall_score": float(avg_score),
            "articles_flagged": flagged,
            "percent_verified": (passed / total * 100) if total > 0 else 0.0,
        }

    def _extract_entities_patterns(self, text: str) -> list[dict[str, Any]]:
        """Pattern-based entity extraction as last resort fallback."""
        entities = []

        name_pattern = r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)*\b"
        matches = re.finditer(name_pattern, text)

        for match in matches:
            entity_text = match.group()
            if entity_text.lower() not in {
                "The",
                "This",
                "That",
                "Then",
                "There",
                "When",
                "Where",
            }:
                entities.append(
                    {
                        "text": entity_text,
                        "label": "UNKNOWN",
                        "start": int(match.start()),
                        "end": int(match.end()),
                        "confidence": 0.5,
                        "description": "Pattern-based extraction",
                    }
                )

        return entities[:20]

    def _clean_entities(self, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Clean and deduplicate entity list."""
        if not entities:
            return []

        seen = set()
        cleaned = []

        for entity in entities:
            entity_text = entity["text"].lower().strip()
            if entity_text and entity_text not in seen and len(entity_text) > 1:
                seen.add(entity_text)
                cleaned.append(entity)

        cleaned.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        return cleaned[:15]

    @traced(name="analyst.analyze_stats", record_args=True)
    def analyze_text_statistics(self, text: str) -> dict[str, Any]:
        """
        Comprehensive text statistical analysis.

        Args:
            text: Input text for analysis

        Returns:
            Dictionary containing statistical metrics
        """
        if not self._validate_text_input(text):
            return {"error": "Invalid text input"}

        start_time = time.time()
        logger.info(f"📊 Analyzing text statistics for {len(text)} characters")

        try:
            words = text.split()
            sentences = [s for s in text.split(".") if s.strip()]

            # Basic metrics
            word_count = len(words)
            sentence_count = len(sentences)
            paragraph_count = len([p for p in text.split("\n\n") if p.strip()])

            # Word length analysis
            word_lengths = [
                len(word.strip('.,!?;:"()[]')) for word in words if word.strip()
            ]

            # Readability metrics
            avg_word_length = statistics.mean(word_lengths) if word_lengths else 0
            avg_sentence_length = (
                word_count / sentence_count if sentence_count > 0 else 0
            )

            # Complexity indicators
            complex_words = [w for w in words if len(w.strip('.,!?;:"()[]')) > 6]
            complex_word_ratio = (
                len(complex_words) / word_count if word_count > 0 else 0
            )

            # Number extraction
            numbers = self._extract_numbers(text)

            # Readability score
            readability = self._calculate_readability(
                text, word_count, sentence_count, word_lengths
            )

            result = {
                "word_count": word_count,
                "character_count": len(text),
                "sentence_count": sentence_count,
                "paragraph_count": paragraph_count,
                "avg_words_per_sentence": round(avg_sentence_length, 2),
                "avg_word_length": round(avg_word_length, 2),
                "complex_words": len(complex_words),
                "complex_word_ratio": round(complex_word_ratio, 3),
                "vocabulary_diversity": self._calculate_vocabulary_diversity(words),
                "readability_score": readability,
                "numbers_found": len(numbers),
                "numeric_density": round(len(numbers) / word_count * 100, 2)
                if word_count > 0
                else 0,
                "processing_time": time.time() - start_time,
            }

            self.processing_stats["total_processed"] += 1

            logger.info(
                f"✅ Statistical analysis complete: {word_count} words, readability {readability}"
            )
            return result

        except Exception as e:
            logger.error(f"❌ Text statistics analysis failed: {e}")
            return {"error": str(e)}

    def _extract_numbers(self, text: str) -> list[dict[str, Any]]:
        """Extract numerical data from text."""
        numbers = []
        patterns = [
            (r"\b\d{1,3}(?:,\d{3})*\.?\d*\%", "percentage"),
            (r"\$\d{1,3}(?:,\d{3})*\.?\d*(?:[kmb]illion)?", "currency"),
            (r"\b\d{1,3}(?:,\d{3})*\.?\d*\b", "number"),
        ]

        for pattern, num_type in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                numbers.append(
                    {
                        "value": match.group(),
                        "type": num_type,
                        "position": match.start(),
                    }
                )

        return numbers

    def _calculate_readability(
        self, text: str, word_count: int, sentence_count: int, word_lengths: list[int]
    ) -> float:
        """Calculate simplified readability score."""
        if sentence_count == 0 or not word_lengths:
            return 0.0

        avg_sentence_length = word_count / sentence_count
        avg_word_length = statistics.mean(word_lengths)

        readability = (
            100 - (1.015 * avg_sentence_length) - (84.6 * avg_word_length / 100)
        )
        return max(0, min(100, round(readability, 1)))

    def _calculate_vocabulary_diversity(self, words: list[str]) -> float:
        """Calculate type-token ratio for vocabulary diversity."""
        if not words:
            return 0.0

        unique_words = {word.lower().strip('.,!?;:"()[]') for word in words}
        return round(len(unique_words) / len(words), 3)

    def extract_key_metrics(self, text: str, url: str | None = None) -> dict[str, Any]:
        """
        Extract key numerical and statistical metrics from news text.

        Args:
            text: Article text to analyze
            url: Article URL for context

        Returns:
            Dictionary containing extracted metrics
        """
        if not self._validate_text_input(text):
            return {"metrics": [], "total_metrics": 0, "error": "Invalid text input"}

        start_time = time.time()
        logger.info(f"🔍 Extracting key metrics from text (length: {len(text)} chars)")

        try:
            all_metrics = []

            # Extract different types of metrics
            all_metrics.extend(self._extract_financial_metrics(text))
            all_metrics.extend(self._extract_temporal_references(text))
            all_metrics.extend(self._extract_statistical_references(text))
            all_metrics.extend(self._extract_geographic_metrics(text))
            all_metrics.extend(self._extract_numbers(text))

            result = {
                "metrics": all_metrics,
                "total_metrics": len(all_metrics),
                "text_length": len(text),
                "url": url,
                "processing_time": time.time() - start_time,
            }

            self.processing_stats["total_processed"] += 1

            logger.info(f"✅ Extracted {len(all_metrics)} total metrics")
            return result

        except Exception as e:
            logger.error(f"❌ Error extracting key metrics: {e}")
            return {"metrics": [], "total_metrics": 0, "error": str(e)}

    def _extract_financial_metrics(self, text: str) -> list[dict[str, Any]]:
        """Extract financial metrics from text."""
        financial_patterns = [
            (
                r"\$\d+(?:,\d+)*(?:\.\d+)?(?:\s*(?:million|billion|trillion))?",
                "currency",
            ),
            (r"\d+(?:\.\d+)?%", "percentage"),
            (
                r"(?:up|down|increased|decreased)\s+(?:by\s+)?\d+(?:\.\d+)?%",
                "change_percentage",
            ),
        ]

        metrics = []
        for pattern, metric_type in financial_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                metrics.append(
                    {
                        "value": match.group(),
                        "type": metric_type,
                        "context": text[
                            max(0, match.start() - 20) : match.end() + 20
                        ].strip(),
                    }
                )

        return metrics

    def _extract_temporal_references(self, text: str) -> list[dict[str, Any]]:
        """Extract temporal references from text."""
        temporal_patterns = [
            (
                r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}",
                "full_date",
            ),
            (r"\b\d{1,2}/\d{1,2}/\d{4}", "date_slash"),
            (
                r"\b(?:yesterday|today|tomorrow|last week|next week|this month)",
                "relative_time",
            ),
        ]

        references = []
        for pattern, ref_type in temporal_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                references.append(
                    {
                        "value": match.group(),
                        "type": ref_type,
                        "position": match.start(),
                    }
                )

        return references

    def _extract_statistical_references(self, text: str) -> list[dict[str, Any]]:
        """Extract statistical references from text."""
        stat_patterns = [
            (
                r"(?:poll|survey|study|research)\s+(?:shows?|indicates?|finds?|suggests?)",
                "study_reference",
            ),
            (
                r"\d+(?:\.\d+)?%\s+of\s+(?:respondents|people|participants)",
                "poll_result",
            ),
            (r"according\s+to\s+(?:a\s+)?(?:poll|survey|study)", "source_reference"),
        ]

        statistics_refs = []
        for pattern, stat_type in stat_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                statistics_refs.append(
                    {
                        "value": match.group(),
                        "type": stat_type,
                        "context": text[
                            max(0, match.start() - 30) : match.end() + 30
                        ].strip(),
                    }
                )

        return statistics_refs

    def _extract_geographic_metrics(self, text: str) -> list[dict[str, Any]]:
        """Extract geographic and demographic metrics."""
        geo_patterns = [
            (
                r"\b(?:in|from|across)\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                "location_reference",
            ),
            (
                r"\d+(?:,\d+)*\s+(?:people|residents|citizens|voters)",
                "demographic_count",
            ),
        ]

        geo_metrics = []
        for pattern, geo_type in geo_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                geo_metrics.append(
                    {
                        "value": match.group(),
                        "type": geo_type,
                        "position": match.start(),
                    }
                )

        return geo_metrics[:10]

    def analyze_content_trends(
        self, texts: list[str], urls: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Analyze trends across multiple content pieces.

        Args:
            texts: List of article texts to analyze
            urls: Corresponding URLs for context

        Returns:
            Dictionary containing trend analysis
        """
        if not texts or not any(text.strip() for text in texts):
            return {
                "trends": [],
                "topics": [],
                "error": "No valid texts provided for trend analysis",
            }

        start_time = time.time()
        logger.info(f"📈 Analyzing content trends across {len(texts)} texts")

        try:
            valid_texts = [text for text in texts if text and text.strip()]

            entity_trends = self._analyze_entity_trends(valid_texts)
            topic_trends = self._analyze_topic_trends(valid_texts)

            trends = []
            topics = []

            # Add entity trends
            if "most_common_entities" in entity_trends:
                for entity, count in entity_trends["most_common_entities"].items():
                    trends.append(
                        {
                            "type": "entity",
                            "value": entity,
                            "frequency": count,
                            "category": "named_entity",
                        }
                    )

            # Add topic trends
            if "trending_topics" in topic_trends:
                for topic, count in topic_trends["trending_topics"].items():
                    topics.append(
                        {
                            "topic": topic,
                            "frequency": count,
                            "relevance_score": count / len(valid_texts),
                        }
                    )
                    trends.append(
                        {
                            "type": "topic",
                            "value": topic,
                            "frequency": count,
                            "category": "keyword",
                        }
                    )

            result = {
                "trends": trends,
                "topics": topics,
                "total_texts": len(valid_texts),
                "total_trends": len(trends),
                "total_topics": len(topics),
                "processing_time": time.time() - start_time,
            }

            self.processing_stats["total_processed"] += 1

            logger.info(
                f"✅ Content trends analysis completed for {len(valid_texts)} texts"
            )
            return result

        except Exception as e:
            logger.error(f"❌ Error analyzing content trends: {e}")
            return {"trends": [], "topics": [], "error": str(e)}

    def _analyze_entity_trends(self, texts: list[str]) -> dict[str, Any]:
        """Analyze entity trends across multiple texts."""
        if not self.spacy_nlp:
            return {"error": "spaCy not available for entity trend analysis"}

        entity_counts = Counter()
        entity_types = defaultdict(list)

        for text in texts:
            if not text:
                continue

            doc = self.spacy_nlp(text)
            for ent in doc.ents:
                entity_counts[ent.text] += 1
                entity_types[ent.label_].append(ent.text)

        return {
            "most_common_entities": dict(entity_counts.most_common(10)),
            "entity_types": {k: len(set(v)) for k, v in entity_types.items()},
            "total_unique_entities": len(entity_counts),
        }

    def _analyze_topic_trends(self, texts: list[str]) -> dict[str, Any]:
        """Analyze topic trends using keyword frequency."""
        all_text = " ".join(texts).lower()
        words = re.findall(r"\b[a-z]{4,}\b", all_text)

        stop_words = {
            "this",
            "that",
            "with",
            "have",
            "will",
            "from",
            "they",
            "been",
            "said",
            "would",
            "there",
            "could",
            "more",
            "what",
            "when",
            "where",
            "were",
            "their",
            "than",
            "about",
            "after",
            "before",
            "during",
            "through",
        }
        filtered_words = [w for w in words if w not in stop_words]

        word_counts = Counter(filtered_words)

        return {
            "trending_topics": dict(word_counts.most_common(15)),
            "total_keywords": len(word_counts),
            "vocabulary_size": len(set(filtered_words)),
        }

    @traced(name="analyst.sentiment", record_args=True)
    def analyze_sentiment(self, text: str) -> dict[str, Any]:
        """
        Analyze sentiment of text content using GPU acceleration.

        Args:
            text: Text content to analyze for sentiment

        Returns:
            Dictionary containing sentiment analysis results
        """
        if not self._validate_text_input(text):
            return {"error": "Invalid text input"}

        start_time = time.time()
        logger.info(f"😊 Analyzing sentiment for {len(text)} characters")

        try:
            adapter_payload = self._get_mistral_result(text)
            if adapter_payload:
                result = adapter_payload.sentiment
            elif self.gpu_analyst:
                sentiment_score = self.gpu_analyst.score_sentiment_gpu(text)

                if sentiment_score is not None:
                    if sentiment_score > 0.6:
                        dominant_sentiment = "positive"
                        confidence = min(sentiment_score, 0.9)
                    elif sentiment_score < 0.4:
                        dominant_sentiment = "negative"
                        confidence = min(1.0 - sentiment_score, 0.9)
                    else:
                        dominant_sentiment = "neutral"
                        confidence = 0.7

                    intensity = (
                        "strong"
                        if confidence > 0.8
                        else "moderate"
                        if confidence > 0.6
                        else "mild"
                    )

                    result = {
                        "dominant_sentiment": dominant_sentiment,
                        "confidence": float(confidence),
                        "intensity": intensity,
                        "sentiment_scores": {
                            "positive": float(sentiment_score),
                            "negative": float(1.0 - sentiment_score),
                            "neutral": 0.5,
                        },
                        "method": "gpu_accelerated",
                        "model_name": self.config.sentiment_model,
                        "analysis_timestamp": datetime.now().isoformat(),
                        "reasoning": f"GPU-accelerated sentiment analysis (score: {sentiment_score:.3f})",
                        "processing_time": time.time() - start_time,
                    }
                else:
                    result = self._heuristic_sentiment_analysis(text)
            else:
                result = self._heuristic_sentiment_analysis(text)

            self.processing_stats["sentiment_analyses"] += 1
            self.processing_stats["total_processed"] += 1

            self._log_feedback(
                "analyze_sentiment",
                {
                    "method": result.get("method", "unknown"),
                    "dominant_sentiment": result.get("dominant_sentiment"),
                    "confidence": result.get("confidence"),
                },
            )

            return result

        except Exception as e:
            logger.error(f"❌ Sentiment analysis failed: {e}")
            self._log_feedback("analyze_sentiment_error", {"error": str(e)})
            return {"error": str(e)}

    def _heuristic_sentiment_analysis(self, text: str) -> dict[str, Any]:
        """Heuristic sentiment analysis fallback."""
        positive_words = [
            "good",
            "great",
            "excellent",
            "amazing",
            "wonderful",
            "positive",
            "success",
            "win",
            "happy",
            "pleased",
            "best",
            "love",
            "like",
            "improve",
            "increase",
            "grow",
            "benefit",
            "advantage",
            "progress",
        ]
        negative_words = [
            "bad",
            "terrible",
            "awful",
            "horrible",
            "negative",
            "fail",
            "loss",
            "sad",
            "angry",
            "disappointed",
            "worst",
            "hate",
            "worse",
            "decline",
            "decrease",
            "problem",
            "issue",
            "crisis",
        ]

        text_lower = text.lower()
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)

        total_words = len(text.split())
        positive_ratio = positive_count / max(total_words, 1)
        negative_ratio = negative_count / max(total_words, 1)

        if positive_count > negative_count:
            dominant_sentiment = "positive"
            confidence = min(0.5 + (positive_count - negative_count) * 0.05, 0.9)
        elif negative_count > positive_count:
            dominant_sentiment = "negative"
            confidence = min(0.5 + (negative_count - positive_count) * 0.05, 0.9)
        else:
            dominant_sentiment = "neutral"
            confidence = 0.6

        intensity = (
            "strong" if confidence > 0.8 else "moderate" if confidence > 0.6 else "mild"
        )

        return {
            "dominant_sentiment": dominant_sentiment,
            "confidence": float(confidence),
            "intensity": intensity,
            "sentiment_scores": {
                "positive": float(positive_ratio),
                "negative": float(negative_ratio),
                "neutral": float(1.0 - positive_ratio - negative_ratio),
            },
            "method": "heuristic_keywords",
            "model_name": "keyword_analysis",
            "analysis_timestamp": datetime.now().isoformat(),
            "reasoning": f"Heuristic analysis (positive: {positive_count}, negative: {negative_count})",
        }

    def detect_bias(self, text: str) -> dict[str, Any]:
        """
        Detect bias in text content using GPU acceleration.

        Args:
            text: Text content to analyze for bias

        Returns:
            Dictionary containing bias detection results
        """
        if not self._validate_text_input(text):
            return {"error": "Invalid text input"}

        start_time = time.time()
        logger.info(f"⚖️ Detecting bias in {len(text)} characters")

        try:
            adapter_payload = self._get_mistral_result(text)
            if adapter_payload:
                result = adapter_payload.bias
            elif self.gpu_analyst:
                bias_score = self.gpu_analyst.score_bias_gpu(text)

                if bias_score is not None:
                    if bias_score > 0.7:
                        bias_level = "high"
                        has_bias = True
                    elif bias_score > 0.4:
                        bias_level = "medium"
                        has_bias = True
                    elif bias_score > 0.2:
                        bias_level = "low"
                        has_bias = True
                    else:
                        bias_level = "minimal"
                        has_bias = False

                    confidence = min(bias_score + 0.3, 0.9)

                    result = {
                        "has_bias": has_bias,
                        "bias_score": float(bias_score),
                        "bias_level": bias_level,
                        "confidence": float(confidence),
                        "political_bias": float(bias_score * 0.6),
                        "emotional_bias": float(bias_score * 0.8),
                        "factual_bias": float(bias_score * 0.7),
                        "reasoning": f"GPU-accelerated bias detection (score: {bias_score:.3f})",
                        "method": "gpu_accelerated",
                        "model_used": self.config.bias_model,
                        "timestamp": datetime.now().isoformat(),
                        "processing_time": time.time() - start_time,
                    }
                else:
                    result = self._heuristic_bias_detection(text)
            else:
                result = self._heuristic_bias_detection(text)

            self.processing_stats["bias_detections"] += 1
            self.processing_stats["total_processed"] += 1

            self._log_feedback(
                "detect_bias",
                {
                    "method": result.get("method", "unknown"),
                    "has_bias": result.get("has_bias"),
                    "bias_level": result.get("bias_level"),
                },
            )

            return result

        except Exception as e:
            logger.error(f"❌ Bias detection failed: {e}")
            self._log_feedback("detect_bias_error", {"error": str(e)})
            return {"error": str(e)}

    def _heuristic_bias_detection(self, text: str) -> dict[str, Any]:
        """Heuristic bias detection fallback."""
        bias_indicators = [
            "always",
            "never",
            "all",
            "everyone",
            "nobody",
            "everybody",
            "terrible",
            "amazing",
            "best",
            "worst",
            "perfect",
            "disaster",
            "obviously",
            "clearly",
            "undoubtedly",
            "absolutely",
            "definitely",
        ]
        political_bias_words = [
            "liberal",
            "conservative",
            "left",
            "right",
            "progressive",
            "traditional",
            "democrat",
            "republican",
            "socialist",
            "capitalist",
            "woke",
            "patriotic",
        ]

        text_lower = text.lower()
        bias_count = sum(1 for word in bias_indicators if word in text_lower)
        political_bias_count = sum(
            1 for word in political_bias_words if word in text_lower
        )

        total_words = len(text.split())
        bias_score = min(
            (bias_count + political_bias_count * 2) / max(total_words, 1) * 10, 1.0
        )

        if bias_score > 0.7:
            bias_level = "high"
        elif bias_score > 0.4:
            bias_level = "medium"
        elif bias_score > 0.2:
            bias_level = "low"
        else:
            bias_level = "minimal"

        return {
            "has_bias": bias_score > 0.3,
            "bias_score": float(bias_score),
            "bias_level": bias_level,
            "confidence": min(bias_score + 0.3, 0.9),
            "political_bias": float(political_bias_count / max(total_words, 1) * 5),
            "emotional_bias": float(bias_count / max(total_words, 1) * 5),
            "factual_bias": float(bias_score * 0.8),
            "reasoning": f"Heuristic bias detection (bias indicators: {bias_count}, political: {political_bias_count})",
            "method": "heuristic_keywords",
            "model_used": "bias_indicators",
            "timestamp": datetime.now().isoformat(),
        }

    def analyze_sentiment_and_bias(self, text: str) -> dict[str, Any]:
        """
        Comprehensive analysis combining sentiment and bias detection.

        Args:
            text: Text content to analyze

        Returns:
            Dictionary containing combined sentiment and bias analysis results
        """
        if not self._validate_text_input(text):
            return {"error": "Invalid text input"}

        start_time = time.time()
        logger.info(
            f"🔍 Running combined sentiment and bias analysis for {len(text)} characters"
        )

        try:
            sentiment_result = self.analyze_sentiment(text)
            bias_result = self.detect_bias(text)

            combined_result = {
                "sentiment_analysis": sentiment_result,
                "bias_analysis": bias_result,
                "combined_assessment": {
                    "overall_reliability": self._calculate_combined_reliability(
                        sentiment_result, bias_result
                    ),
                    "content_quality_score": self._calculate_content_quality(
                        sentiment_result, bias_result
                    ),
                    "recommendations": self._generate_analysis_recommendations(
                        sentiment_result, bias_result
                    ),
                },
                "analysis_timestamp": datetime.now().isoformat(),
                "text_length": len(text),
                "method": "analyst_combined_analysis",
                "processing_time": time.time() - start_time,
            }

            self.processing_stats["total_processed"] += 1

            self._log_feedback(
                "analyze_sentiment_and_bias",
                {
                    "sentiment": sentiment_result.get("dominant_sentiment", "unknown"),
                    "bias_level": bias_result.get("bias_level", "unknown"),
                    "combined_reliability": combined_result["combined_assessment"][
                        "overall_reliability"
                    ],
                },
            )

            return combined_result

        except Exception as e:
            logger.error(f"❌ Combined sentiment and bias analysis failed: {e}")
            self._log_feedback("analyze_sentiment_and_bias_error", {"error": str(e)})
            return {"error": str(e)}

    def _calculate_combined_reliability(
        self, sentiment_result: dict[str, Any], bias_result: dict[str, Any]
    ) -> float:
        """Calculate combined reliability score."""
        try:
            sentiment_reliability = 1.0
            if sentiment_result.get("dominant_sentiment") != "neutral":
                sentiment_confidence = sentiment_result.get("confidence", 0.5)
                sentiment_reliability = 1.0 - (sentiment_confidence - 0.5) * 0.4

            bias_penalty = 1.0 - bias_result.get("bias_score", 0.0)
            combined_reliability = sentiment_reliability * 0.6 + bias_penalty * 0.4

            return min(max(combined_reliability, 0.0), 1.0)
        except Exception:
            return 0.5

    def _calculate_content_quality(
        self, sentiment_result: dict[str, Any], bias_result: dict[str, Any]
    ) -> float:
        """Calculate content quality score."""
        try:
            sentiment_quality = (
                0.8 if sentiment_result.get("dominant_sentiment") == "neutral" else 0.6
            )
            bias_quality = 1.0 - bias_result.get("bias_score", 0.0)
            sentiment_confidence = sentiment_result.get("confidence", 0.5)

            quality_score = (
                sentiment_quality * 0.4
                + bias_quality * 0.4
                + sentiment_confidence * 0.2
            )
            return min(max(quality_score, 0.0), 1.0)
        except Exception:
            return 0.5

    def _generate_analysis_recommendations(
        self, sentiment_result: dict[str, Any], bias_result: dict[str, Any]
    ) -> list[str]:
        """Generate recommendations based on analysis."""
        recommendations = []

        try:
            sentiment = sentiment_result.get("dominant_sentiment", "neutral")
            sentiment_intensity = sentiment_result.get("intensity", "mild")

            if sentiment != "neutral" and sentiment_intensity in ["strong", "moderate"]:
                recommendations.append(
                    f"Content shows {sentiment_intensity} {sentiment} sentiment - consider fact-checking"
                )

            bias_level = bias_result.get("bias_level", "minimal")
            if bias_level in ["high", "medium"]:
                recommendations.append(
                    f"Detected {bias_level} bias - verify with multiple sources"
                )

            if not recommendations:
                recommendations.append("Content appears balanced and neutral")

            return recommendations
        except Exception:
            return ["Analysis completed - manual review recommended"]


# Export main components
__all__ = ["AnalystEngine", "AnalystConfig"]
