"""
Memory Agent Tools - Utility Functions
=====================================

Core utilities for the memory agent:
- Embedding model management
- Article storage operations
- Vector search functionality
- Feedback logging
- Training data collection

Architecture:
- Shared embedding model with caching
- Database connection pooling
- GPU acceleration support
- Comprehensive error handling
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import requests

from common.json_utils import make_json_safe
from common.observability import get_logger
from common.stage_b_metrics import get_stage_b_metrics

try:
    import torch
except Exception:
    torch = None

# Import database utilities - REMOVED: now using migrated database service directly in functions
from common.url_normalization import hash_article_url, normalize_article_url

# Configure centralized logging
logger = get_logger(__name__)

# Environment variables
FEEDBACK_LOG = os.environ.get("MEMORY_FEEDBACK_LOG", "./feedback_memory.log")
EMBEDDING_MODEL_NAME = os.environ.get("SENTENCE_TRANSFORMER_MODEL", "all-MiniLM-L6-v2")
MEMORY_AGENT_PORT = int(os.environ.get("MEMORY_AGENT_PORT", 8007))
# NOTE: PostgreSQL environment variables were removed after migration to
# MariaDB + Chroma; the storage layer is accessed via the migrated database
# service from `database.utils.migrated_database_utils`.

# Canonical cache folder for shared embedding model
DEFAULT_MODEL_CACHE = os.environ.get("MEMORY_MODEL_CACHE") or str(
    Path("./agents/memory/models").resolve()
)


def log_feedback(event: str, details: dict):
    """Logs feedback to a file."""
    try:
        with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()}\t{event}\t{details}\n")
    except Exception as e:
        logger.error(f"Error logging feedback: {e}")


def get_embedding_model():
    """Return a SentenceTransformer instance, using the shared helper when available."""
    try:
        from agents.common.embedding import get_shared_embedding_model

        # Use a canonical cache folder and device so cached instances are reused
        # Force CPU to avoid VRAM contention with VLLM/Synthesizer
        return get_shared_embedding_model(
            EMBEDDING_MODEL_NAME, cache_folder=DEFAULT_MODEL_CACHE, device="cpu"
        )
    except Exception:
        # Fallback: use agent-local models directory
        try:
            from agents.common.embedding import get_shared_embedding_model

            agent_cache = os.environ.get("MEMORY_MODEL_CACHE") or str(
                Path("./agents/memory/models").resolve()
            )
            # Force CPU
            return get_shared_embedding_model(
                EMBEDDING_MODEL_NAME, cache_folder=agent_cache, device="cpu"
            )
        except Exception as e:
            logger.warning(f"Could not load shared embedding model: {e}")
            # Return None - caller should handle this gracefully
            return None


def _parse_publication_date(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            if candidate.endswith("Z"):
                candidate = candidate[:-1] + "+00:00"
            return datetime.fromisoformat(candidate)
        except ValueError:
            return None
    return None


def _make_chroma_metadata_safe(metadata: dict) -> dict:
    """Convert metadata values to Chroma-compatible scalar representations."""
    safe_metadata: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        # Drop unset values entirely to avoid sending nulls that Chroma rejects
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            safe_metadata[key] = value
        elif isinstance(value, datetime):
            safe_metadata[key] = value.isoformat()
        else:
            try:
                serialized = json.dumps(value, default=str)
                if serialized == "null":
                    continue
                safe_metadata[key] = serialized
            except Exception:
                safe_metadata[key] = str(value)
    return safe_metadata


def _ensure_embedding_metadata(metadata: dict) -> dict:
    """Attach embedding model metadata to Chroma metadatas for traceability."""
    try:
        model = (
            os.environ.get("EMBEDDING_MODEL")
            or os.environ.get("SENTENCE_TRANSFORMER_MODEL")
            or "all-MiniLM-L6-v2"
        )
        dims = os.environ.get("EMBEDDING_DIMENSIONS")
        metadata = metadata or {}
        if isinstance(metadata, dict):
            metadata.setdefault("embedding_model", model)
            if dims:
                try:
                    metadata.setdefault("embedding_dimensions", int(dims))
                except Exception:
                    pass
    except Exception:
        pass
    return metadata


def save_article(
    content: str, metadata: dict, embedding_model=None, db_service=None
) -> dict:
    """Saves an article to the migrated MariaDB + ChromaDB system.

    Args:
        content: Article text to embed and store.
        metadata: Arbitrary metadata dict to store alongside the article.
        embedding_model: Optional pre-initialized SentenceTransformer instance.
            If not provided, a new model will be created via get_embedding_model().
    """
    metrics = get_stage_b_metrics()
    start_time = perf_counter()
    try:
        metadata = metadata or {}
        if not isinstance(metadata, dict):
            metadata = {"value": metadata}
        metadata = make_json_safe(metadata)

        disable_dedupe = bool(metadata.get("disable_dedupe"))

        raw_url = metadata.get("url")
        canonical_url = metadata.get("canonical") or raw_url
        normalized_url = metadata.get("normalized_url") or normalize_article_url(
            raw_url or "", canonical_url
        )
        normalized_url = normalized_url or None
        hash_algorithm = (
            metadata.get("url_hash_algorithm")
            or os.environ.get("ARTICLE_URL_HASH_ALGO", "sha256")
        ).lower()

        hash_value = None
        duplicate_lookup_id = None

        # Use migrated database service
        from database.utils.migrated_database_utils import create_database_service

        created_local_db_service = False
        if db_service is None:
            db_service = create_database_service()
            # Ensure the db_service exposes a minimal compatible API for test fakes
            try:
                from database.utils.migrated_database_utils import ensure_service_compat

                db_service = ensure_service_compat(db_service)
            except Exception:
                pass
            created_local_db_service = True

        # Ensure DB connection is available before doing any cursor operations
        try:
            db_service.ensure_conn()
        except Exception as e:
            logger.error(f"DB connection unavailable during save_article: {e}")
            metrics.record_ingestion("db_connection_unavailable")
            if created_local_db_service:
                db_service.close()
            return {
                "error": "MySQL Connection not available",
                "processing_time": perf_counter() - start_time,
            }

        # If canonical Chroma is required and unavailable, fail fast
        chroma_require_canonical = (
            os.environ.get("CHROMADB_REQUIRE_CANONICAL", "1") == "1"
        )
        if chroma_require_canonical and getattr(db_service, "collection", None) is None:
            logger.error(
                "CHROMADB_REQUIRE_CANONICAL enabled but Chroma collection not available"
            )
            if created_local_db_service:
                db_service.close()
            metrics.record_ingestion("chroma_unavailable")
            return {
                "error": "chroma_unavailable",
                "processing_time": perf_counter() - start_time,
            }

        if not disable_dedupe:
            hash_candidate = metadata.get("url_hash") or hash_article_url(
                normalized_url or canonical_url or raw_url or "",
                algorithm=hash_algorithm,
            )

            if not hash_candidate and normalized_url:
                hash_candidate = hash_article_url(
                    normalized_url, algorithm=hash_algorithm
                )
            hash_value = hash_candidate or None

            if hash_value:
                # Use a short-lived connection for the duplicate checks + insert to
                # avoid sharing a single connection across concurrent callers
                using_temp_conn = False
                conn = getattr(db_service, "mb_conn", None)
                try:
                    if getattr(db_service, "get_connection", None):
                        conn = db_service.get_connection()
                        using_temp_conn = True

                    # Check for duplicates in MariaDB (buffered cursor to avoid "Unread result found")
                    cursor = conn.cursor(buffered=True)
                    cursor.execute(
                        "SELECT id FROM articles WHERE url_hash = %s", (hash_value,)
                    )
                    duplicate = cursor.fetchone()
                    cursor.close()
                finally:
                    # Close any per-call connection we opened
                    if using_temp_conn:
                        try:
                            conn.close()
                        except Exception:
                            pass

                if duplicate:
                    duplicate_lookup_id = duplicate[0]
            if normalized_url and duplicate_lookup_id is None:
                using_temp_conn = False
                conn = getattr(db_service, "mb_conn", None)
                try:
                    if getattr(db_service, "get_connection", None):
                        conn = db_service.get_connection()
                        using_temp_conn = True

                    # Check for duplicates by normalized URL (buffered)
                    cursor = conn.cursor(buffered=True)
                    cursor.execute(
                        "SELECT id FROM articles WHERE normalized_url = %s",
                        (normalized_url,),
                    )
                    duplicate = cursor.fetchone()
                    cursor.close()
                finally:
                    if using_temp_conn:
                        try:
                            conn.close()
                        except Exception:
                            pass

                if duplicate:
                    duplicate_lookup_id = duplicate[0]

            if duplicate_lookup_id is not None:
                logger.info(
                    "Article with hash %s already exists (ID: %s), skipping duplicate",
                    hash_value,
                    duplicate_lookup_id,
                )
                metrics.record_ingestion("duplicate")
                if created_local_db_service:
                    db_service.close()
                return {
                    "status": "duplicate",
                    "article_id": duplicate_lookup_id,
                    "message": "Article already exists",
                    "processing_time": perf_counter() - start_time,
                }

        # Use provided model if available to avoid re-loading model per-call
        cache_label = "provided" if embedding_model is not None else "shared"
        if embedding_model is None:
            embedding_model = get_embedding_model()
            if embedding_model is None:
                metrics.record_embedding("model_unavailable")
                logger.error("No embedding model available for article storage")
                metrics.record_ingestion("embedding_model_unavailable")
                if created_local_db_service:
                    db_service.close()
                return {
                    "error": "embedding_model_unavailable",
                    "processing_time": perf_counter() - start_time,
                }
            cache_label = "shared"

        # encode may return numpy array; convert later to list of floats
        encode_start = perf_counter()
        try:
            embedding = embedding_model.encode(content)
            encode_duration = perf_counter() - encode_start
            metrics.observe_embedding_latency(cache_label, encode_duration)
            metrics.record_embedding("success")
        except Exception as encoding_error:
            encode_duration = perf_counter() - encode_start
            metrics.observe_embedding_latency(cache_label, encode_duration)
            metrics.record_embedding("error")
            logger.error("Embedding generation failed: %s", encoding_error)
            metrics.record_ingestion("error")
            if created_local_db_service:
                db_service.close()
            return {
                "error": "embedding_generation_failed",
                "processing_time": perf_counter() - start_time,
            }

        try:
            metadata_payload = json.dumps(metadata)
        except Exception:
            metadata_payload = json.dumps({"raw": str(metadata)})

        authors: list[str] = metadata.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]
        tags: list[str] = metadata.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        publication_dt = _parse_publication_date(metadata.get("publication_date"))
        collection_dt = _parse_publication_date(metadata.get("collection_timestamp"))
        if collection_dt is None:
            collection_dt = datetime.now(timezone.utc)

        review_reasons_json = json.dumps(metadata.get("review_reasons") or [])

        # Insert into MariaDB (without embedding column)
        # Use a per-request connection to perform the insert and subsequent
        # read of LAST_INSERT_ID() — this avoids interfering with other
        # concurrent operations using a shared connection.
        using_temp_conn = False
        conn = getattr(db_service, "mb_conn", None)
        try:
            if getattr(db_service, "get_connection", None):
                conn = db_service.get_connection()
                using_temp_conn = True

            cursor = conn.cursor(buffered=True)

            insertion_params = (
                raw_url,
                metadata.get("title"),
                content,
                metadata.get("summary"),
                bool(metadata.get("analyzed", False)),
                metadata.get("source_id"),
                normalized_url,
                hash_value,
                hash_algorithm,
                metadata.get("language"),
                metadata.get("section"),
                json.dumps(tags) if tags else None,
                json.dumps(authors) if authors else None,
                metadata.get("raw_html_ref"),
                float(metadata.get("confidence", 0.0))
                if metadata.get("confidence") is not None
                else None,
                bool(metadata.get("needs_review", False)),
                review_reasons_json,
                json.dumps(metadata.get("extraction_metadata") or {}),
                json.dumps(metadata.get("structured_metadata") or {}),
                publication_dt,
                metadata_payload,
                collection_dt,
            )

            insert_query = """
            INSERT INTO articles (
                source_url,
                title,
                content,
                summary,
                analyzed,
                source_id,
                normalized_url,
                url_hash,
                url_hash_algo,
                language,
                section,
                tags,
                authors,
                raw_html_ref,
                extraction_confidence,
                needs_review,
                review_reasons,
                extraction_metadata,
                structured_metadata,
                publication_date,
                metadata,
                collection_timestamp,
                created_at,
                updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
            )
            """

            cursor.execute(insert_query, insertion_params)

            # commit on the same connection we used for insert
            try:
                conn.commit()
            except Exception:
                # If conn is the shared service connection, let higher-level
                # logic handle commit/rollback as before
                try:
                    if not using_temp_conn and getattr(db_service, "mb_conn", None):
                        db_service.mb_conn.commit()
                except Exception:
                    pass

            # Get the inserted article ID
            cursor.execute("SELECT LAST_INSERT_ID()")
            last = cursor.fetchone()
            next_id = last[0] if last and len(last) > 0 else None
            cursor.close()
        finally:
            # Close any per-call connection
            if using_temp_conn:
                try:
                    conn.close()
                except Exception:
                    pass

        if next_id is None:
            logger.error(
                "Could not determine inserted article id; aborting save operation"
            )
            if created_local_db_service:
                db_service.close()
            return {
                "error": "could_not_determine_inserted_id",
                "processing_time": perf_counter() - start_time,
            }

        # Add embedding to ChromaDB
        try:
            if getattr(db_service, "collection", None):
                embedding_list = list(map(float, embedding))
                chroma_metadata = _make_chroma_metadata_safe(
                    _ensure_embedding_metadata(metadata)
                )
                db_service.collection.add(
                    ids=[str(next_id)],
                    embeddings=[embedding_list],
                    metadatas=[chroma_metadata],
                    documents=[content],
                )
                logger.debug(f"Added embedding to ChromaDB for article {next_id}")
            else:
                logger.warning(
                    "Skipping embedding add to ChromaDB as no collection is configured"
                )
        except Exception as chroma_error:
            logger.warning(f"Failed to add embedding to ChromaDB: {chroma_error}")
            # Don't fail the whole operation if ChromaDB fails

        # --- Living Stories: Assign-or-Buffer Logic ---
        try:
            # Only proceed if we have an embedding and DB service
            if locals().get("embedding") is not None and getattr(db_service, "mb_conn", None) and getattr(db_service, "chroma_client", None):
                import numpy as np
                import uuid
                
                # Configuration
                ls_threshold = float(os.environ.get("LS_SIMILARITY_THRESHOLD", "0.85"))
                ls_decay = float(os.environ.get("LS_DRIFT_DECAY_RATE", "0.2"))
                
                ls_collection = None
                try:
                    ls_collection = db_service.chroma_client.get_collection("active_living_stories")
                except Exception:
                    # Collection might not exist if setup script wasn't run or failed
                    pass
                
                match_found = False
                
                if ls_collection:
                    # Search for nearest story
                    # embedding is a list of floats, ensure it's compatible
                    embedding_query = list(map(float, embedding))
                    
                    results = ls_collection.query(
                        query_embeddings=[embedding_query],
                        n_results=1,
                        include=["embeddings", "distances", "metadatas"]
                    )
                    
                    if results["ids"] and len(results["ids"][0]) > 0:
                        # Distance check (Cosine distance)
                        distance = results["distances"][0][0]
                        if distance < (1.0 - ls_threshold):
                            match_found = True
                            story_id = results["ids"][0][0]
                            old_centroid = results["embeddings"][0][0]
                            
                            # Calculate new centroid
                            req_vec = np.array(embedding_query)
                            cur_vec = np.array(old_centroid)
                            new_vec = (cur_vec * (1 - ls_decay)) + (req_vec * ls_decay)
                            # Normalize
                            norm = np.linalg.norm(new_vec)
                            if norm > 0:
                                new_vec = new_vec / norm
                            new_centroid = new_vec.tolist()
                            
                            # 1. Update Chroma Collection
                            ls_collection.update(
                                ids=[story_id],
                                embeddings=[new_centroid],
                                metadatas=results["metadatas"][0] if results["metadatas"] else None
                            )
                            
                            # 2. Update DB
                            cursor = db_service.mb_conn.cursor()
                            try:
                                # Update timestamp and centroid
                                cursor.execute(
                                    "UPDATE living_stories SET last_updated_at = NOW(), semantic_centroid = %s WHERE id = %s",
                                    (json.dumps(new_centroid), story_id)
                                )
                                
                                # Insert StoryUpdate
                                update_id = str(uuid.uuid4())
                                article_ids_json = json.dumps([next_id])
                                
                                cursor.execute(
                                    """
                                    INSERT INTO story_updates (id, story_id, article_ids, article_count, batch_centroid, timestamp)
                                    VALUES (%s, %s, %s, 1, %s, NOW())
                                    """,
                                    (update_id, story_id, article_ids_json, json.dumps(new_centroid))
                                )
                                db_service.mb_conn.commit()
                                logger.debug(f"Living Stories: Article {next_id} assigned to story {story_id}")
                            except Exception as db_err:
                                logger.error(f"Living Stories DB Update failed: {db_err}")
                            finally:
                                cursor.close()

                if not match_found:
                    # Buffer to Pending Pool
                    domain = metadata.get("domain") or "unknown"
                    vector_blob = json.dumps(list(map(float, embedding)))
                    
                    cursor = db_service.mb_conn.cursor()
                    try:
                        cursor.execute(
                            """
                            INSERT INTO pending_articles_pool (article_id, source_domain, vector_blob, added_at)
                            VALUES (%s, %s, %s, NOW())
                            """,
                            (next_id, domain, vector_blob)
                        )
                        db_service.mb_conn.commit()
                        logger.debug(f"Living Stories: Article {next_id} buffered to pending pool")
                    except Exception as e:
                         logger.warning(f"Failed to buffer article {next_id}: {e}")
                    finally:
                        cursor.close()

        except Exception as e:
            logger.error(f"Living Stories: Fast path logic failed: {e}")

        log_feedback("save_article", {"status": "success", "article_id": next_id})

        result = {"status": "success", "article_id": next_id, "id": next_id}

        # Collect prediction for training
        try:
            from training_system import collect_prediction

            collect_prediction(
                agent_name="memory",
                task_type="article_storage",
                input_text=content,
                prediction=result,
                confidence=0.95,  # High confidence for successful storage
                source_url="",
            )
            logger.debug("📊 Training data collected for article storage")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")

        # Return both 'article_id' and legacy 'id' key for backward compatibility
        metrics.record_ingestion("success")
        if created_local_db_service:
            db_service.close()
        result["processing_time"] = perf_counter() - start_time
        return result
    except Exception as e:
        logger.error(f"Error saving article: {e}")
        metrics.record_ingestion("error")
        try:
            if created_local_db_service:
                db_service.close()
        except Exception:
            pass
        return {"error": str(e), "processing_time": perf_counter() - start_time}


def vector_search_articles(query: str, top_k: int = 5) -> list:
    """Performs a vector search for articles using the memory agent."""
    url = f"http://localhost:{MEMORY_AGENT_PORT}/vector_search_articles"
    try:
        response = requests.post(url, json={"query": query, "top_k": top_k}, timeout=5)
        response.raise_for_status()
        res = response.json()
        # Coerce a few common shapes from test fakes: allow list or dict with 'results'
        if isinstance(res, list):
            return res
        if isinstance(res, dict):
            # prefer explicit results key
            if "results" in res and isinstance(res["results"], list):
                return res["results"]
            # sometimes test fakes return empty dict
            return []
        return []
    except requests.exceptions.RequestException as e:
        logger.warning(f"vector_search_articles: memory agent request failed: {e}")
        return []


def vector_search_articles_local(
    query: str, top_k: int = 5, embedding_model=None
) -> list:
    """Local in-process vector search implementation using the new ChromaDB + MariaDB system.

    This uses the semantic search service instead of direct PostgreSQL queries.
    """
    try:
        from common.semantic_search_service import get_search_service

        # Get the search service instance
        search_service = get_search_service()

        # Perform semantic search
        response = search_service.search(
            query=query, n_results=top_k, search_type="semantic", min_score=0.0
        )

        # Convert SearchResult objects to the expected format
        results = []
        for result in response.results:
            results.append(
                {
                    "id": result.article_id,
                    "score": result.similarity_score,
                    "content": result.content,
                    "metadata": result.metadata,
                }
            )

        # Collect prediction for training
        try:
            from training_system import collect_prediction

            confidence = min(
                0.9,
                max(
                    0.1,
                    float(
                        sum(r.similarity_score for r in response.results)
                        / len(response.results)
                    )
                    if response.results
                    else 0.5,
                ),
            )
            collect_prediction(
                agent_name="memory",
                task_type="vector_search",
                input_text=query,
                prediction={"results": results, "top_k": top_k},
                confidence=confidence,
                source_url="",
            )
            logger.debug(
                f"📊 Training data collected for vector search (confidence: {confidence:.3f})"
            )
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")

        return results
    except Exception:
        logger.exception("vector_search_articles_local: error in semantic search")
        return []
