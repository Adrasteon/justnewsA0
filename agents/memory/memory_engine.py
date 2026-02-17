"""
Memory Engine - Core Storage and Retrieval Logic
===============================================

Responsibilities:
- Article storage and retrieval operations
- Database connection management
- Training example logging
- Article ingestion with transactional operations
- Source management
- Statistics and monitoring

Architecture:
- Database connection pooling
- Transactional operations for data integrity
- Comprehensive error handling
- Performance monitoring and metrics
"""

import json
import os

# Import tools
from agents.memory.tools import get_embedding_model, log_feedback, save_article
from common.json_utils import make_json_safe
from common.observability import get_logger

# Import database utilities
from database.utils.migrated_database_utils import create_database_service

# Configure centralized logging
logger = get_logger(__name__)


class MemoryEngine:
    """Core memory engine for article storage and retrieval operations"""

    def __init__(self):
        self.db_initialized = False
        self.db_service = None
        self.embedding_model = None

    def _acquire_cursor(
        self, *, per_call: bool = True, dictionary: bool = False, buffered: bool = True
    ):
        """Helper to obtain a cursor + optional per-call connection.

        Returns (cursor, conn) where conn is None when using the shared
        mb_conn cursor. This allows tests which mock mb_conn.cursor to continue
        working without needing to provide get_safe_cursor.
        """
        if not self.db_service:
            return None, None
        # Prefer the safe helper if available
        getter = getattr(self.db_service, "get_safe_cursor", None)
        if callable(getter):
            try:
                result = getter(
                    per_call=per_call, dictionary=dictionary, buffered=buffered
                )
                # Accept only explicit (cursor, conn) sequences — fall back otherwise
                if isinstance(result, (list, tuple)) and len(result) == 2:
                    return result[0], result[1]
                # Try iterating into a tuple and validate length
                try:
                    rtuple = tuple(result)
                    if len(rtuple) == 2:
                        return rtuple[0], rtuple[1]
                except Exception:
                    pass
            except Exception:
                # Fall back to shared connection
                pass

        # Fallback: use the shared connection's cursor for tests/compat
        conn = getattr(self.db_service, "mb_conn", None)
        if conn is None:
            return None, None
        # mysql.connector supports dictionary & buffered arguments
        try:
            cur = conn.cursor(dictionary=dictionary, buffered=buffered)
        except TypeError:
            # Some fake cursors in tests may not accept args
            cur = conn.cursor()
        return cur, None

    def embed_article(self, article_id: int) -> dict:
        """Generates embedding for an existing article and saves to ChromaDB"""
        try:
             # Fetch article
             cursor, conn = self._acquire_cursor(dictionary=True)
             if not cursor:
                 return {"error": "DB connection failed"}
             
             cursor.execute("SELECT id, content, metadata FROM articles WHERE id = %s", (article_id,))
             article = cursor.fetchone()
             if conn: 
                 cursor.close()
                 conn.close()
             
             if not article:
                 return {"error": "Article not found"}
            
             if not article['content']:
                 return {"error": "Article has no content"}

             # Generate Embedding
             if not self.embedding_model:
                  # Try to load - uses tools.get_embedding_model
                  from agents.memory.tools import get_embedding_model
                  self.embedding_model = get_embedding_model()
             
             if not self.embedding_model:
                  return {"error": "Embedding model not available"}

             # Move model to device if needed/possible is handled by get_embedding_model logic generally
             # But here we assume it returns a usable model
             
             embedding = self.embedding_model.encode(article['content']).tolist()
             
             # Upsert to Chroma
             collection = getattr(self.db_service, "collection", None)
             if not collection:
                  return {"error": "Chroma collection not available"}
             
             meta = {}
             # Use safe get
             if article.get('metadata'):
                 if isinstance(article['metadata'], str):
                     try:
                        meta = json.loads(article['metadata'])
                     except:
                        pass
                 elif isinstance(article['metadata'], dict):
                     meta = article['metadata']
             
             if not meta:
                 meta = {"source": "unknown"}

             # Ensure metadata is flat/safe for Chroma
             safe_meta = {}
             for k, v in meta.items():
                 if isinstance(v, (str, int, float, bool)):
                     safe_meta[k] = v
                 else:
                     safe_meta[k] = str(v)
             
             if not safe_meta:
                 safe_meta = {"source": "unknown"}
             
             # Perform vector store operation first - failure here must abort the DB update
             try:
                 if collection is None:
                     raise RuntimeError("ChromaDB collection is not available")
                     
                 collection.upsert(
                     ids=[str(article_id)],
                     embeddings=[embedding],
                     metadatas=[safe_meta],
                     documents=[article['content']]
                 )
                 logger.info(f"Successfully upserted embedding to ChromaDB for article {article_id}")
             except Exception as chroma_error:
                 logger.error(f"ChromaDB write failed for article {article_id}: {chroma_error}")
                 return {"status": "error", "message": f"ChromaDB write failure: {str(chroma_error)}"}

             # ONLY after successful ChromaDB write do we update the MariaDB flag
             cursor, conn = self._acquire_cursor()
             
             try:
                 # Update embedded flag
                 cursor.execute("UPDATE articles SET embedded=1 WHERE id=%s", (article_id,))
                 
                 # Record embedding in embeddings_document table
                 try:
                     import json as json_module
                     meta_json = json_module.dumps(safe_meta) if safe_meta else '{}'
                     cursor.execute(
                         "INSERT INTO embeddings_document (embeddings_collection_id, document_id, content, content_hash, embedding_status, metadata) VALUES (1, %s, %s, %s, 'active', %s)",
                         (str(article_id), article['title'][:255] if article.get('title') else '', 
                         article.get('url_hash', ''), meta_json)
                     )
                 except Exception as emb_error:
                     logger.debug(f"Note: Could not record embedding metadata: {emb_error}")
                 
                 if conn: 
                    conn.commit()
                    logger.debug(f"Committed MariaDB transaction for article {article_id} (embedded=1)")
                 elif self.db_service and hasattr(self.db_service, 'mb_conn'):
                    self.db_service.mb_conn.commit()
                    logger.debug(f"Committed MariaDB shared transaction for article {article_id} (embedded=1)")
             finally:
                 if conn:
                     conn.close()
             
             return {"status": "success", "article_id": article_id}

        except Exception as e:
            logger.error(f"Error embedding article {article_id}: {e}")
            return {"error": str(e)}

    async def initialize(self):
        """Initialize the memory engine"""
        try:
            # Initialize migrated database service
            self.db_service = create_database_service()
            self.db_initialized = True
            logger.info("Migrated database service initialized for memory engine")

            # If Chroma is required to be canonical for this deployment, ensure we actually have a collection
            try:
                require_canonical = (
                    os.environ.get("CHROMADB_REQUIRE_CANONICAL", "1") == "1"
                )
                if require_canonical:
                    # If require_canonical is true, we must have a chroma collection connected
                    if getattr(self.db_service, "collection", None) is None:
                        logger.error(
                            "CHROMADB_REQUIRE_CANONICAL enabled but no Chroma collection connected; aborting startup"
                        )
                        raise RuntimeError(
                            "ChromaDB required (CANONICAL) but not available"
                        )
            except Exception:
                # Propagate any fatal condition
                raise

            # Pre-warm embedding model
            self.embedding_model = get_embedding_model()
            logger.info("Embedding model pre-warmed in memory engine")

        except Exception as e:
            logger.error(f"Failed to initialize memory engine: {e}")
            raise

    async def shutdown(self):
        """Shutdown the memory engine"""
        try:
            if self.db_initialized and self.db_service:
                try:
                    from database.utils.migrated_database_utils import (
                        close_cached_service,
                    )

                    close_cached_service()
                except Exception:
                    # Fall back: close the service instance directly
                    try:
                        self.db_service.close()
                    except Exception:
                        pass
                logger.info("Migrated database service closed in memory engine")

            # Clear references
            self.db_service = None
            self.embedding_model = None

        except Exception as e:
            logger.error(f"Error during memory engine shutdown: {e}")

    def save_article(self, content: str, metadata: dict) -> dict:
        """Saves an article to the database and generates an embedding"""
        try:
            # Use the shared save_article function from tools
            result = save_article(
                content,
                metadata,
                embedding_model=self.embedding_model,
                db_service=self.db_service,
            )
            return result
        except Exception as e:
            logger.error(f"Error saving article in memory engine: {e}")
            return {"error": str(e)}

    def get_article(self, article_id: int) -> dict | None:
        """Retrieves an article from the database by its ID"""
        try:
            if not self.db_service:
                return None
            try:
                self.db_service.ensure_conn()
            except Exception as e:
                logger.error(f"DB connection unavailable when retrieving article: {e}")
                return None
            cursor, conn = self._acquire_cursor(
                per_call=True, dictionary=True, buffered=True
            )
            try:
                cursor.execute(
                    "SELECT id, content, metadata FROM articles WHERE id = %s",
                    (article_id,),
                )
                article = cursor.fetchone()
            finally:
                try:
                    cursor.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

            if article:
                # Parse metadata JSON if it's a string
                if isinstance(article.get("metadata"), str):
                    try:
                        article["metadata"] = json.loads(article["metadata"])
                    except Exception:
                        pass
                return article
            else:
                return None
        except Exception as e:
            logger.error(f"Error retrieving article {article_id}: {e}")
            return None

    def get_all_article_ids(self) -> dict:
        """Retrieves all article IDs from the database"""
        try:
            if not self.db_service:
                return {"article_ids": []}
            try:
                self.db_service.ensure_conn()
            except Exception as e:
                logger.error(
                    f"DB connection unavailable when retrieving all article ids: {e}"
                )
                return {"article_ids": []}
            cursor, conn = self._acquire_cursor(
                per_call=True, dictionary=True, buffered=True
            )
            try:
                cursor.execute("SELECT id FROM articles")
                rows = cursor.fetchall()
            finally:
                try:
                    cursor.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

            if rows:
                article_ids = [row["id"] for row in rows]
                logger.info(f"Found {len(article_ids)} article IDs")
                return {"article_ids": article_ids}
            else:
                logger.info("No article IDs found")
                return {"article_ids": []}
        except Exception as e:
            logger.error(f"Error retrieving all article IDs: {e}")
            return {"error": "database_error"}

    def get_recent_articles(self, limit: int = 10) -> list:
        """Returns the most recent articles"""
        try:
            if not self.db_service:
                return []
            try:
                self.db_service.ensure_conn()
            except Exception as e:
                logger.error(
                    f"DB connection unavailable when retrieving recent articles: {e}"
                )
                return []
            cursor, conn = self._acquire_cursor(
                per_call=True, dictionary=True, buffered=True
            )
            try:
                cursor.execute(
                    "SELECT id, content, metadata FROM articles ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
                rows = cursor.fetchall()
            finally:
                try:
                    cursor.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

            # Ensure JSON-serializable metadata
            for r in rows:
                if isinstance(r.get("metadata"), str):
                    try:
                        r["metadata"] = json.loads(r["metadata"])
                    except Exception:
                        pass

            return rows

        except Exception as e:
            logger.error(f"Error retrieving recent articles: {e}")
            return []

    def log_training_example(
        self, task: str, input_data: dict, output_data: dict, critique: str
    ) -> dict:
        """Logs a training example to the database"""
        try:
            if not self.db_service:
                return {"error": "database_not_initialized"}
            try:
                self.db_service.ensure_conn()
            except Exception as e:
                logger.error(
                    f"DB connection unavailable when logging training example: {e}"
                )
                return {"error": "database_not_available"}
            # Insert training example
            cursor, conn = self._acquire_cursor(per_call=True, buffered=True)
            try:
                cursor.execute(
                    "INSERT INTO training_examples (task, input, output, critique) VALUES (%s, %s, %s, %s)",
                    (task, json.dumps(input_data), json.dumps(output_data), critique),
                )
                # If a per-call connection was returned, commit on it; otherwise
                # fall back to the shared mb_conn provided by the service.
                if conn is not None:
                    conn.commit()
                else:
                    try:
                        getattr(self.db_service, "mb_conn", None).commit()
                    except Exception:
                        pass
            finally:
                try:
                    cursor.close()
                except Exception:
                    pass
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass

            log_feedback(
                "log_training_example",
                {
                    "task": task,
                    "input_keys": list(input_data.keys()) if input_data else [],
                    "output_keys": list(output_data.keys()) if output_data else [],
                    "critique_length": len(critique) if critique else 0,
                },
            )

            result = {"status": "logged"}

            # Collect prediction for training
            try:
                from training_system import collect_prediction

                collect_prediction(
                    agent_name="memory",
                    task_type="training_example_logging",
                    input_text=f"Task: {task}, Input: {str(input_data)}, Output: {str(output_data)}, Critique: {critique}",
                    prediction=result,
                    confidence=0.9,  # High confidence for successful logging
                    source_url="",
                )
                logger.debug("📊 Training data collected for training example logging")
            except ImportError:
                logger.debug("Training system not available - skipping data collection")
            except Exception as e:
                logger.warning(f"Failed to collect training data: {e}")

            return result

        except Exception as e:
            logger.error(f"Error logging training example: {e}")
            return {"error": str(e)}

    def ingest_article(self, article_payload: dict, statements: list) -> dict:
        """Handles article ingestion with transactional operations"""
        try:
            if not article_payload:
                raise ValueError("Missing article_payload")

            article_payload = make_json_safe(article_payload)
            if not isinstance(article_payload, dict):
                article_payload = {"value": article_payload}

            statements = statements or []
            statements = make_json_safe(statements)
            if not isinstance(statements, list):
                statements = [statements]

            logger.info(f"Ingesting article: {article_payload.get('url')}")

            # Execute statements transactionally
            chosen_source_id = None
            # For transactional series of statements we need a dedicated
            # per-call connection (`tx_conn`) so we can run multiple statements
            # and commit/rollback atomically without interfering with other
            # concurrent callers. Fall back if a per-call connection cannot be
            # created.
            tx_conn = None
            try:
                # Obtain a per-call transaction connection when possible. Some
                # tests provide only a fake `mb_conn` so fallback to that.
                conn_getter = getattr(self.db_service, "get_connection", None)
                if callable(conn_getter):
                    try:
                        tx_conn = conn_getter()
                    except Exception:
                        tx_conn = getattr(self.db_service, "mb_conn", None)
                else:
                    tx_conn = getattr(self.db_service, "mb_conn", None)
            except Exception as e:
                logger.error(f"DB connection unavailable during ingest_article: {e}")
                return {"status": "error", "error": "database_not_available"}

            # Log open file descriptor count for diagnostics
            try:
                fd_count = len(os.listdir(f"/proc/{os.getpid()}/fd"))
                logger.debug(f"FD count before ingestion: {fd_count}")
            except Exception:
                pass

            def _clear_pending_results():
                try:
                    tmp_cursor = tx_conn.cursor(buffered=True)
                    # some DB drivers return a strict boolean from nextset(); tests
                    # using MagicMock return a MagicMock which is truthy and would
                    # create an infinite loop. Ensure we only loop while nextset()
                    # returns the boolean True value.
                    while getattr(tmp_cursor, "nextset", lambda: False)() is True:
                        pass
                    tmp_cursor.close()
                except Exception:
                    pass

            try:
                pending_commit = False
                for sql, params in statements:
                    cursor = None
                    try:
                        sql_upper = sql.upper() if isinstance(sql, str) else ""
                        params_tuple = tuple(params) if params is not None else ()

                        if "RETURNING" in sql_upper:
                            cursor = tx_conn.cursor(dictionary=True, buffered=True)
                            cursor.execute(sql, params_tuple)
                            pending_commit = True

                            result = cursor.fetchone()
                            if result and "id" in result:
                                chosen_source_id = result["id"]

                            try:
                                while (
                                    getattr(cursor, "nextset", lambda: False)() is True
                                ):
                                    cursor.fetchall()
                            except Exception:
                                pass
                        else:
                            cursor = tx_conn.cursor(buffered=True)
                            cursor.execute(sql, params_tuple)
                            pending_commit = True

                    except Exception as stmt_e:
                        try:
                            if cursor is not None:
                                while (
                                    getattr(cursor, "nextset", lambda: False)() is True
                                ):
                                    cursor.fetchall()
                        except Exception:
                            pass

                        try:
                            tx_conn.rollback()
                        except Exception:
                            pass

                        pending_commit = False

                        if (
                            "unique constraint" in str(stmt_e).lower()
                            or "duplicate key" in str(stmt_e).lower()
                        ):
                            logger.debug(
                                f"Source already exists, skipping insert: {stmt_e}"
                            )
                            if "sources" in (sql or "") and params_tuple:
                                domain = None
                                if len(params_tuple) > 1:
                                    domain = params_tuple[1]
                                if domain:
                                    lookup_cursor = None
                                    try:
                                        lookup_cursor = tx_conn.cursor(
                                            dictionary=True, buffered=True
                                        )
                                        lookup_cursor.execute(
                                            "SELECT id FROM sources WHERE domain = %s",
                                            (domain,),
                                        )
                                        existing_source = lookup_cursor.fetchone()
                                        if existing_source:
                                            chosen_source_id = existing_source["id"]
                                            logger.debug(
                                                f"Using existing source ID: {chosen_source_id}"
                                            )
                                    except Exception as lookup_error:
                                        logger.debug(
                                            f"Failed to fetch existing source ID: {lookup_error}"
                                        )
                                    finally:
                                        if lookup_cursor:
                                            try:
                                                lookup_cursor.close()
                                            except Exception:
                                                pass
                            continue

                        raise
                    finally:
                        if cursor:
                            try:
                                cursor.close()
                            except Exception:
                                pass

                if pending_commit:
                    try:
                        tx_conn.commit()
                    except Exception as commit_error:
                        logger.error(f"Failed to commit transaction: {commit_error}")
                        _clear_pending_results()
                        return {"status": "error", "error": str(commit_error)}

            except Exception as e:
                logger.error(f"Database transaction failed: {e}")
                _clear_pending_results()
                try:
                    tx_conn.rollback()
                except Exception:
                    pass
                try:
                    tx_conn.close()
                except Exception:
                    pass
                return {"status": "error", "error": str(e)}
            finally:
                try:
                    if tx_conn is not None:
                        tx_conn.close()
                except Exception:
                    pass

            # Now save the article content
            try:
                content = article_payload.get("content", "")
                metadata = {
                    "url": article_payload.get("url"),
                    "normalized_url": article_payload.get("normalized_url"),
                    "title": article_payload.get("title"),
                    "summary": article_payload.get("summary"),
                    "analyzed": article_payload.get("analyzed", False),
                    "domain": article_payload.get("domain"),
                    "publisher_meta": article_payload.get("publisher_meta", {}),
                    "confidence": article_payload.get("confidence", 0.5),
                    "paywall_flag": article_payload.get("paywall_flag", False),
                    "extraction_metadata": article_payload.get(
                        "extraction_metadata", {}
                    ),
                    "structured_metadata": article_payload.get(
                        "structured_metadata", {}
                    ),
                    "timestamp": article_payload.get("timestamp"),
                    "url_hash": article_payload.get("url_hash"),
                    "url_hash_algorithm": article_payload.get("url_hash_algorithm"),
                    "canonical": article_payload.get("canonical"),
                    "language": article_payload.get("language"),
                    "authors": article_payload.get("authors", []),
                    "section": article_payload.get("section"),
                    "tags": article_payload.get("tags", []),
                    "publication_date": article_payload.get("publication_date"),
                    "raw_html_ref": article_payload.get("raw_html_ref"),
                    "needs_review": article_payload.get("needs_review", False),
                    "review_reasons": article_payload.get("review_reasons", []),
                    "source_id": chosen_source_id,
                    "disable_dedupe": article_payload.get("disable_dedupe"),
                }

                if content:  # Only save if there's actual content
                    save_result = save_article(
                        content,
                        metadata,
                        embedding_model=self.embedding_model,
                        db_service=self.db_service,
                    )
                    if save_result.get("status") == "duplicate":
                        logger.info(
                            f"Article already exists, skipping: {article_payload.get('url')}"
                        )
                        resp = {
                            "status": "ok",
                            "url": article_payload.get("url"),
                            "duplicate": True,
                            "existing_id": save_result.get("article_id"),
                        }
                    else:
                        if save_result.get("error"):
                            logger.warning(
                                f"Failed to save article content: {save_result.get('error')}"
                            )
                            resp = {
                                "status": "ok",
                                "url": article_payload.get("url"),
                                "content_save_error": save_result.get("error"),
                            }
                        else:
                            logger.info(
                                f"Article saved with ID: {save_result.get('article_id')}"
                            )
                            resp = {"status": "ok", "url": article_payload.get("url")}
                else:
                    logger.warning(
                        f"No content to save for article: {article_payload.get('url')}"
                    )
                    resp = {
                        "status": "ok",
                        "url": article_payload.get("url"),
                        "no_content": True,
                    }

            except Exception as e:
                logger.warning(f"Failed to save article content: {e}")
                # Don't fail the whole ingestion if content saving fails
                resp = {
                    "status": "ok",
                    "url": article_payload.get("url"),
                    "content_save_error": str(e),
                }

            return resp

        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            return {"status": "error", "error": str(e)}

    def get_article_count(self) -> int:
        """Get total count of articles in database"""
        try:
            if not self.db_service:
                return 0
            try:
                self.db_service.ensure_conn()
            except Exception as e:
                logger.error(
                    f"DB connection unavailable when getting article count: {e}"
                )
                return 0
            cursor, conn = self._acquire_cursor(
                per_call=True, dictionary=True, buffered=True
            )
            try:
                cursor.execute("SELECT COUNT(*) as count FROM articles")
                result = cursor.fetchone()
            finally:
                try:
                    cursor.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

            return result.get("count", 0) if result else 0
        except Exception as e:
            logger.error(f"Error getting article count: {e}")
            # Try to clear any unread results
            try:
                _tmp_cur, _tmp_conn = self._acquire_cursor(per_call=True, buffered=True)
                try:
                    while _tmp_cur.nextset():
                        pass
                finally:
                    try:
                        _tmp_cur.close()
                    except Exception:
                        pass
                    try:
                        _tmp_conn.close()
                    except Exception:
                        pass
            except Exception:
                pass
            return 0

    def get_sources(self, limit: int = 10) -> list:
        """Get list of sources from the database"""
        try:
            if not self.db_service:
                return []
            try:
                self.db_service.ensure_conn()
            except Exception as e:
                logger.error(f"DB connection unavailable when getting sources: {e}")
                return []
            cursor, conn = self._acquire_cursor(
                per_call=True, dictionary=True, buffered=True
            )
            try:
                cursor.execute(
                    "SELECT id, url, domain, name, description, country, language FROM sources ORDER BY id LIMIT %s",
                    (limit,),
                )
                sources = cursor.fetchall()
            finally:
                try:
                    cursor.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

            return sources or []
        except Exception as e:
            logger.error(f"Error getting sources: {e}")
            return []

    def get_stats(self) -> dict:
        """Get memory engine statistics"""
        try:
            stats = {
                "engine": "memory",
                "db_initialized": self.db_initialized,
                "embedding_model_loaded": self.embedding_model is not None,
            }

            # Get article count
            try:
                article_count = self.get_article_count()
                stats["article_count"] = article_count
            except Exception:
                stats["article_count"] = "error"

            # Get source count
            try:
                source_count = len(self.get_sources(1000))  # Get more to count total
                stats["source_count"] = source_count
            except Exception:
                stats["source_count"] = "error"

            return stats

        except Exception as e:
            logger.error(f"Error getting memory engine stats: {e}")
            return {"engine": "memory", "error": str(e)}
