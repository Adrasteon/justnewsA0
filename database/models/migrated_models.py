"""
Migrated Database Models - MariaDB + ChromaDB Integration
Models for the migrated JustNews database schema

Features:
- MariaDB models for relational data (articles, sources, mappings)
- ChromaDB integration for vector embeddings
- Semantic search capabilities
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import json
import mysql.connector
# Module-level placeholder so tests can patch `database.models.migrated_models.SentenceTransformer`
SentenceTransformer = None
# NOTE: Do not import sentence_transformers at module import time — it's a
# heavy optional dependency. Import dynamically in the initialization path so
# tests that patch/magic-mock sentence_transformers.SentenceTransformer work
# reliably and missing packages don't break test collection.

from common.observability import get_logger
import os
from pathlib import Path

logger = get_logger(__name__)


def _resolve_snapshot_candidate(model_root: Path, model_id: str) -> Path | None:
    """Resolve a HF-style snapshot path under a model root if present."""
    normalized = model_id.replace("/", "--")
    candidate = model_root / f"models--{normalized}"
    if not candidate.exists():
        return None
    snapshots = candidate / "snapshots"
    if snapshots.exists():
        dirs = sorted([p for p in snapshots.iterdir() if p.is_dir()])
        if dirs:
            return dirs[0]
    return candidate


def _resolve_embedding_model_source(model_id: str) -> str:
    """Resolve embedding model source, preferring central ModelStore paths."""
    # Highest-priority explicit override.
    explicit_path = os.environ.get("EMBEDDING_MODEL_PATH")
    if explicit_path:
        p = Path(explicit_path).expanduser()
        if p.exists():
            return str(p)
        logger.warning("EMBEDDING_MODEL_PATH set but missing on disk: %s", p)

    root_env = os.environ.get("MODEL_STORE_ROOT")
    if not root_env:
        return model_id

    root = Path(root_env).expanduser()
    if not root.exists():
        logger.warning("MODEL_STORE_ROOT does not exist: %s", root)
        return model_id

    # Prefer explicit embedding agent; default to fact_checker.
    # Operators can set MODEL_STORE_EMBEDDING_AGENT to route to another namespace
    # such as "base_models" if that's how the store is populated.
    agent_name = os.environ.get("MODEL_STORE_EMBEDDING_AGENT", "fact_checker")

    # Prefer current symlink style layout: <root>/<agent>/current
    current_dir = root / agent_name / "current"
    if current_dir.exists():
        try:
            resolved_current = current_dir.resolve()
            snap = _resolve_snapshot_candidate(resolved_current, model_id)
            if snap and snap.exists():
                return str(snap)
            if (resolved_current / "modules.json").exists() or (resolved_current / "config.json").exists():
                return str(resolved_current)
        except Exception as e:
            logger.debug("Failed to resolve current model-store directory %s: %s", current_dir, e)

    # Fallback explicit path hint under model store.
    relative_hint = os.environ.get("MODEL_STORE_EMBEDDING_PATH")
    if relative_hint:
        hinted = (root / relative_hint).resolve()
        if hinted.exists():
            return str(hinted)
        logger.warning("MODEL_STORE_EMBEDDING_PATH set but missing on disk: %s", hinted)

    return model_id


class Source:
    """Source model for MariaDB"""

    __tablename__ = "sources"

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.url = kwargs.get('url')
        self.domain = kwargs.get('domain')
        self.name = kwargs.get('name')
        self.description = kwargs.get('description')
        self.country = kwargs.get('country')
        self.language = kwargs.get('language')
        self.paywall = kwargs.get('paywall', False)
        self.paywall_type = kwargs.get('paywall_type')
        self.last_verified = kwargs.get('last_verified')
        self.metadata = kwargs.get('metadata', {})
        self.created_at = kwargs.get('created_at')
        self.updated_at = kwargs.get('updated_at')

    @classmethod
    def from_row(cls, row) -> 'Source':
        """Create Source from database row"""
        return cls(
            id=row[0],
            url=row[1],
            domain=row[2],
            name=row[3],
            description=row[4],
            country=row[5],
            language=row[6],
            paywall=row[7],
            paywall_type=row[8],
            last_verified=row[9],
            metadata=json.loads(row[10]) if row[10] else {},
            created_at=row[11],
            updated_at=row[12]
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'url': self.url,
            'domain': self.domain,
            'name': self.name,
            'description': self.description,
            'country': self.country,
            'language': self.language,
            'paywall': self.paywall,
            'paywall_type': self.paywall_type,
            'last_verified': self.last_verified,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class Article:
    """Article model for MariaDB"""

    __tablename__ = "articles"

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.url = kwargs.get('url')
        self.title = kwargs.get('title')
        self.content = kwargs.get('content')
        self.summary = kwargs.get('summary')
        self.analyzed = kwargs.get('analyzed', False)
        self.source_id = kwargs.get('source_id')
        self.created_at = kwargs.get('created_at')
        self.updated_at = kwargs.get('updated_at')
        self.normalized_url = kwargs.get('normalized_url')
        self.url_hash = kwargs.get('url_hash')
        self.url_hash_algo = kwargs.get('url_hash_algo', 'sha256')
        self.language = kwargs.get('language')
        self.section = kwargs.get('section')
        self.tags = kwargs.get('tags', [])
        self.authors = kwargs.get('authors', [])
        self.raw_html_ref = kwargs.get('raw_html_ref')
        self.extraction_confidence = kwargs.get('extraction_confidence')
        self.needs_review = kwargs.get('needs_review', False)
        self.review_reasons = kwargs.get('review_reasons', [])
        self.extraction_metadata = kwargs.get('extraction_metadata', {})
        self.structured_metadata = kwargs.get('structured_metadata', {})
        self.publication_date = kwargs.get('publication_date')
        self.metadata = kwargs.get('metadata', {})
        self.collection_timestamp = kwargs.get('collection_timestamp')
        # Synthesis/Publishing metadata (Option A: extend `articles` table)
        self.is_synthesized = kwargs.get('is_synthesized', False)
        # can be a JSON list of cluster ids or a comma-delimited string
        self.input_cluster_ids = kwargs.get('input_cluster_ids', [])
        self.synth_model = kwargs.get('synth_model')
        self.synth_version = kwargs.get('synth_version')
        self.synth_prompt_id = kwargs.get('synth_prompt_id')
        # store as JSON/str for auditability
        self.synth_trace = kwargs.get('synth_trace')
        self.critic_result = kwargs.get('critic_result', {})
        self.fact_check_status = kwargs.get('fact_check_status')
        self.fact_check_trace = kwargs.get('fact_check_trace')
        self.factual_accuracy_score = kwargs.get('factual_accuracy_score')
        self.fact_check_details = kwargs.get('fact_check_details', {})
        self.is_published = kwargs.get('is_published', False)
        self.published_at = kwargs.get('published_at')
        self.created_by = kwargs.get('created_by')

    @classmethod
    def from_row(cls, row) -> 'Article':
        """Create Article from database row"""
        return cls(
            id=row[0],
            url=row[1],
            title=row[2],
            content=row[3],
            summary=row[4],
            analyzed=row[5],
            source_id=row[6],
            created_at=row[7],
            updated_at=row[8],
            normalized_url=row[9],
            url_hash=row[10],
            url_hash_algo=row[11],
            language=row[12],
            section=row[13],
            tags=json.loads(row[14]) if row[14] else [],
            authors=json.loads(row[15]) if row[15] else [],
            raw_html_ref=row[16],
            extraction_confidence=row[17],
            needs_review=row[18],
            review_reasons=json.loads(row[19]) if row[19] else [],
            extraction_metadata=json.loads(row[20]) if row[20] else {},
            structured_metadata=json.loads(row[21]) if row[21] else {},
            publication_date=row[22],
            metadata=json.loads(row[23]) if row[23] else {},
            collection_timestamp=row[24]
            # Optional synthesis/publishing columns (added in migration)
            , is_synthesized=row[25] if len(row) > 25 else False
            , input_cluster_ids=json.loads(row[26]) if len(row) > 26 and row[26] else []
            , synth_model=row[27] if len(row) > 27 else None
            , synth_version=row[28] if len(row) > 28 else None
            , synth_prompt_id=row[29] if len(row) > 29 else None
            , synth_trace=json.loads(row[30]) if len(row) > 30 and row[30] else None
            , critic_result=json.loads(row[31]) if len(row) > 31 and row[31] else {}
            , fact_check_status=row[32] if len(row) > 32 else None
            , fact_check_trace=json.loads(row[33]) if len(row) > 33 and row[33] else None
            , is_published=row[34] if len(row) > 34 else False
            , published_at=row[35] if len(row) > 35 else None
            , created_by=row[36] if len(row) > 36 else None
            , factual_accuracy_score=row[37] if len(row) > 37 else None
            , fact_check_details=json.loads(row[38]) if len(row) > 38 and row[38] else {}
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'url': self.url,
            'title': self.title,
            'content': self.content,
            'summary': self.summary,
            'analyzed': self.analyzed,
            'source_id': self.source_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'normalized_url': self.normalized_url,
            'url_hash': self.url_hash,
            'url_hash_algo': self.url_hash_algo,
            'language': self.language,
            'section': self.section,
            'tags': self.tags,
            'authors': self.authors,
            'raw_html_ref': self.raw_html_ref,
            'extraction_confidence': self.extraction_confidence,
            'needs_review': self.needs_review,
            'review_reasons': self.review_reasons,
            'extraction_metadata': self.extraction_metadata,
            'structured_metadata': self.structured_metadata,
            'publication_date': self.publication_date,
            'metadata': self.metadata,
            'collection_timestamp': self.collection_timestamp
            , 'is_synthesized': self.is_synthesized
            , 'input_cluster_ids': self.input_cluster_ids
            , 'synth_model': self.synth_model
            , 'synth_version': self.synth_version
            , 'synth_prompt_id': self.synth_prompt_id
            , 'synth_trace': self.synth_trace
            , 'critic_result': self.critic_result
            , 'fact_check_status': self.fact_check_status
            , 'fact_check_trace': self.fact_check_trace
            , 'factual_accuracy_score': self.factual_accuracy_score
            , 'fact_check_details': self.fact_check_details
            , 'is_published': self.is_published
            , 'published_at': self.published_at
            , 'created_by': self.created_by
        }


class ArticleSourceMap:
    """Article-Source mapping model for MariaDB"""

    __tablename__ = "article_source_map"

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.article_id = kwargs.get('article_id')
        self.source_id = kwargs.get('source_id')
        self.confidence = kwargs.get('confidence', 1.0)
        self.detected_at = kwargs.get('detected_at')
        self.metadata = kwargs.get('metadata', {})

    @classmethod
    def from_row(cls, row) -> 'ArticleSourceMap':
        """Create ArticleSourceMap from database row"""
        return cls(
            id=row[0],
            article_id=row[1],
            source_id=row[2],
            confidence=row[3],
            detected_at=row[4],
            metadata=json.loads(row[5]) if row[5] else {}
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'article_id': self.article_id,
            'source_id': self.source_id,
            'confidence': self.confidence,
            'detected_at': self.detected_at,
            'metadata': self.metadata
        }


class SynthesizedArticle:
    """Dedicated table for synthesized articles (Option B)."""

    __tablename__ = "synthesized_articles"

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.story_id = kwargs.get('story_id')
        self.cluster_id = kwargs.get('cluster_id')
        self.input_articles = kwargs.get('input_articles', [])
        self.title = kwargs.get('title')
        self.body = kwargs.get('body')
        self.summary = kwargs.get('summary')
        self.reasoning_plan = kwargs.get('reasoning_plan', {})
        self.analysis_summary = kwargs.get('analysis_summary', {})
        self.synth_metadata = kwargs.get('synth_metadata', {})
        self.created_at = kwargs.get('created_at')
        self.updated_at = kwargs.get('updated_at')
        self.is_published = kwargs.get('is_published', False)
        self.published_at = kwargs.get('published_at')
        self.published_by = kwargs.get('published_by')

    @classmethod
    def from_row(cls, row) -> 'SynthesizedArticle':
        return cls(
            id=row[0],
            story_id=row[1],
            cluster_id=row[2],
            input_articles=json.loads(row[3]) if row[3] else [],
            title=row[4],
            body=row[5],
            summary=row[6],
            reasoning_plan=json.loads(row[7]) if row[7] else {},
            analysis_summary=json.loads(row[8]) if row[8] else {},
            synth_metadata=json.loads(row[9]) if row[9] else {},
            created_at=row[10],
            updated_at=row[11],
            is_published=row[12],
            published_at=row[13],
            published_by=row[14]
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'story_id': self.story_id,
            'cluster_id': self.cluster_id,
            'input_articles': self.input_articles,
            'title': self.title,
            'body': self.body,
            'summary': self.summary,
            'reasoning_plan': self.reasoning_plan,
            'analysis_summary': self.analysis_summary,
            'synth_metadata': self.synth_metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'is_published': self.is_published,
            'published_at': self.published_at,
            'published_by': self.published_by,
        }


class MigratedDatabaseService:
    """Service for interacting with the migrated database (MariaDB + ChromaDB)"""

    def __init__(self, config: Dict[str, Any]):
        # Accept either a full config with top-level 'database' or a flat database config
        if isinstance(config, dict) and 'database' in config:
            self.config = config
        else:
            # Wrap a raw database config in the expected structure
            self.config = {'database': config or {}}
        self.mb_conn = None
        self.chroma_client = None
        self.embedding_model = None
        self.collection = None

        self._connect_databases()

    def _connect_databases(self):
        """Connect to MariaDB and ChromaDB"""
        # MariaDB connection
        mb_config = self.config['database']['mariadb']
        # Build connection parameters, conditionally including password only if it's not empty
        conn_params = {
            'host': mb_config['host'],
            'port': mb_config['port'],
            'user': mb_config['user'],
            'database': mb_config['database'],
            'autocommit': False,
            'use_pure': True
        }
        # Only include password if it's not empty (for passwordless authentication)
        if mb_config.get('password'):
            conn_params['password'] = mb_config['password']
        
        self.mb_conn = mysql.connector.connect(**conn_params)
        logger.info("Connected to MariaDB")
        # Persist mariadb config for reconnect attempts
        self._mariadb_config = mb_config

        # ChromaDB connection
        chroma_config = self.config['database'].get('chromadb', {})
        # Use HttpClient with basic settings
        import os
        os.environ["CHROMA_TELEMETRY_ENABLED"] = "false"
        
        # Try to connect without authentication first (works with ChromaDB 1.3.2)
        self.chroma_client = None
        self.collection = None
        try:
            # Import chromadb lazily. Importing it at module import time pulls in
            # large optional dependencies (opentelemetry, google.rpc) which can
            # cause warnings/errors during test collection. Attempt to import the
            # package here and fall back to a local None to keep the service
            # functional when chroma is not installed/available.
            try:
                import chromadb  # type: ignore
            except Exception:
                chromadb = None

            host = chroma_config.get('host')
            port = chroma_config.get('port')
            tenant = chroma_config.get('tenant')
            # Validate canonical chroma instance if required
            try:
                require_canonical = os.environ.get('CHROMADB_REQUIRE_CANONICAL', '1') == '1'
                canonical_host = os.environ.get('CHROMADB_CANONICAL_HOST')
                canonical_port = os.environ.get('CHROMADB_CANONICAL_PORT')
                if require_canonical and host and port and canonical_host and canonical_port:
                    from database.utils.chromadb_utils import validate_chroma_is_canonical
                    # Will raise ChromaCanonicalValidationError on mismatch
                    validate_chroma_is_canonical(host, port, canonical_host, int(canonical_port), raise_on_fail=True)
            except Exception:
                # Any validation issues should cause failure only when requirement is enabled; otherwise continue
                raise
            if host and port:
                import time
                max_retries = int(os.environ.get('CHROMADB_CONNECT_RETRIES', 3))
                retry_delay = float(os.environ.get('CHROMADB_CONNECT_RETRY_DELAY', 1.0))
                last_exc = None
                for attempt in range(max_retries):
                    try:
                        if tenant:
                            try:
                                self.chroma_client = chromadb.HttpClient(host=host, port=port, tenant=tenant)
                                logger.info(f"ChromaDB client initialized with tenant={tenant}")
                            except TypeError:
                                # Older chromadb client might not accept tenant in constructor - fallback
                                self.chroma_client = chromadb.HttpClient(host=host, port=port)
                                logger.info("ChromaDB client initialized without tenant parameter (older SDK)")
                        else:
                            self.chroma_client = chromadb.HttpClient(host=host, port=port)
                            logger.info("ChromaDB client initialized without tenant")
                        # try heartbeat
                        try:
                            self.chroma_client.heartbeat()
                        except Exception as hb_err:
                            # heartbeat may be unavailable on some deployments; try listing collections
                            logger.debug(f"Heartbeat failed with error: {hb_err}; attempting alternate connectivity checks")
                            try:
                                # Try list or get collection as an alternate connectivity probe
                                _ = self.chroma_client.list_collections()
                            except Exception as e2:
                                logger.debug(f"Alternate connectivity probe failed: {e2}")
                                raise hb_err
                        last_exc = None
                        break
                    except Exception as e:
                        last_exc = e
                        logger.warning(f"Attempt {attempt+1}/{max_retries} to connect to ChromaDB failed: {e}")
                        time.sleep(retry_delay)
                if last_exc:
                    # Special-case: root endpoint not chroma (e.g., MCP Bus), help operator to diagnose
                    try:
                        from database.utils.chromadb_utils import get_root_info
                        root_info = get_root_info(host, port)
                        if isinstance(root_info, dict) and 'text' in root_info and 'MCP Bus Agent' in str(root_info.get('text', '')):
                            logger.warning("ChromaDB endpoint seems to point at MCP Bus (root indicates MCP Bus Agent). Ensure your CHROMADB_HOST/PORT are correct (env or system_config.json).")
                    except Exception:
                        pass
                    raise last_exc
                # Test the connection
                self.chroma_client.heartbeat()
        except Exception as e:
            # Do not swallow canonical validation errors - they must abort service initialization
            from database.utils.chromadb_utils import ChromaCanonicalValidationError
            if isinstance(e, ChromaCanonicalValidationError):
                logger.error(f"Chroma canonical validation failed: {e}")
                raise
            logger.warning(f"Direct ChromaDB connection failed: {e}")
            # Try best-effort auth bypass patch (keeps existing behavior but won't raise)
            try:
                from chromadb.api import UserIdentity
                original_get_user_identity = chromadb.api.client.Client.get_user_identity

                def patched_get_user_identity(self):
                    return UserIdentity(user_id="anonymous", tenant="default", databases=["default"])

                chromadb.api.client.Client.get_user_identity = patched_get_user_identity
                try:
                    host = chroma_config.get('host')
                    port = chroma_config.get('port')
                    if host and port:
                        self.chroma_client = chromadb.HttpClient(host=host, port=port)
                        self.chroma_client.heartbeat()
                finally:
                    chromadb.api.client.Client.get_user_identity = original_get_user_identity
            except Exception as e2:
                logger.warning(f"ChromaDB auth bypass attempt failed: {e2}")
                # Additional diagnostic: try to discover endpoints and suggest actions
                try:
                    from database.utils.chromadb_utils import discover_chroma_endpoints, get_root_info
                    endpoints = discover_chroma_endpoints(host, port)
                    logger.debug(f"ChromaDB endpoint discovery: {endpoints}")
                    root_info = get_root_info(host, port)
                    logger.debug(f"ChromaDB root info: {root_info}")
                except Exception:
                    logger.debug("ChromaDB extra diagnostics not available")
        
        # Create collection if it doesn't exist - but fail gracefully if ChromaDB isn't available
        base_collection_name = chroma_config.get('collection')
        collection_name = self.get_scoped_collection_name(base_collection_name)
        
        if self.chroma_client and collection_name:
            # If possible, try scoped collection name first (better traceability), fall back to base name
            tried_names = []
            def try_get_or_create(name: str):
                try:
                    c = self.chroma_client.get_collection(name)
                    logger.info(f"Connected to existing ChromaDB collection: {name}")
                    return c
                except Exception as e:
                    logger.info(f"Collection {name} doesn't exist or could not be fetched: {e}")
                    try:
                        c = self.chroma_client.create_collection(
                            name=name,
                            metadata={"description": "Article embeddings for semantic search"}
                        )
                        logger.info(f"Created new ChromaDB collection: {name}")
                        return c
                    except Exception as create_err:
                        logger.warning(f"Failed to create ChromaDB collection '{name}': {create_err}")
                        return None

            # Attempt scoped collection name first (when enabled and embedding config present), then fall back to base
            collection_candidates = [collection_name]
            if collection_name != base_collection_name:
                collection_candidates = [collection_name, base_collection_name]
            else:
                collection_candidates = [base_collection_name]

            logger.debug(f"CHROMADB candidates=%s", collection_candidates)
            for candidate in collection_candidates:
                tried_names.append(candidate)
                c = try_get_or_create(candidate)
                if c is not None:
                    self.collection = c
                    break

            if self.collection is None:
                # If all attempts failed, try HTTP helper auto-provisioning as a last resort
                try:
                    from database.utils.chromadb_utils import ensure_collection_exists_using_http, create_tenant
                    tenant_create_enabled = os.environ.get('CHROMADB_AUTO_CREATE_TENANT', '0') == '1'
                    if tenant_create_enabled:
                        if create_tenant(host, port, tenant='default_tenant'):
                            logger.info("Created default tenant 'default_tenant' for ChromaDB server")
                        else:
                            logger.warning("Could not auto-create default tenant for ChromaDB server")
                    for candidate in tried_names:
                        if ensure_collection_exists_using_http(host, port, candidate):
                            logger.info(f"Ensured collection {candidate} exists via HTTP API")
                            try:
                                self.collection = self.chroma_client.get_collection(candidate)
                                break
                            except Exception:
                                continue
                        else:
                            logger.warning(f"Failed to ensure collection {candidate} exists via HTTP API")
                except Exception:
                    logger.debug("ChromaDB extra diagnostics/auto-provision not available (skipping)")
                # Ensure service continues to operate without ChromaDB if all methods failed
                if self.collection is None:
                    self.collection = None
        else:
            logger.warning("ChromaDB client not initialized; operating without embeddings support.")
        
        if self.collection:
            logger.info("Connected to ChromaDB")
        else:
            logger.warning("ChromaDB not available - embeddings support disabled")

        # Embedding model: import sentence-transformers at runtime (best-effort)
        embeddings_enabled = str(os.environ.get("JUSTNEWS_DB_EMBEDDING_ENABLED", "1")).lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        if not embeddings_enabled:
            logger.info("DB embedding model loading disabled (JUSTNEWS_DB_EMBEDDING_ENABLED=0)")
            self.embedding_model = None
            return

        embedding_config = self.config['database']['embedding']
        try:
            from sentence_transformers import SentenceTransformer as _SentenceTransformer  # type: ignore
        except Exception:
            logger.warning("SentenceTransformer unavailable - embeddings disabled in MigratedDatabaseService")
            self.embedding_model = None
        else:
            try:
                embedding_model_id = embedding_config.get('model')
                resolved_model_source = _resolve_embedding_model_source(embedding_model_id)
                strict_store = str(os.environ.get("STRICT_MODEL_STORE", "0")).lower() in (
                    "1",
                    "true",
                    "yes",
                )
                if strict_store and resolved_model_source == embedding_model_id and os.environ.get("MODEL_STORE_ROOT"):
                    raise RuntimeError(
                        "STRICT_MODEL_STORE is enabled but no embedding model path could be resolved from MODEL_STORE_ROOT"
                    )

                self.embedding_model = _SentenceTransformer(resolved_model_source)
                if resolved_model_source != embedding_model_id:
                    logger.info(
                        "Loaded embedding model from model store path: %s",
                        resolved_model_source,
                    )
                else:
                    logger.info(f"Loaded embedding model: {embedding_model_id}")
            except Exception as e:
                logger.warning(f"Failed to load embedding model '{embedding_config.get('model')}': {e}")

    def get_scoped_collection_name(self, base_name: str) -> str:
        """
        Generate a scoped collection name based on the current embedding model and dimensions.
        
        Args:
            base_name: The base collection name (e.g., 'articles')
            
        Returns:
            The scoped collection name (e.g., 'articles__BAAI_bge-large-en-v1_5__1024')
        """
        if not base_name:
            return base_name
            
        try:
            # Scoped collection enabled unless explicitly disabled via environment variable.
            _scoped_env = os.environ.get('CHROMADB_MODEL_SCOPED_COLLECTION')
            if _scoped_env is not None and str(_scoped_env).lower() in ('0', 'false', 'no', 'off'):
                return base_name
                
            embedding_config = self.config.get('database', {}).get('embedding', {})
            emb_model = embedding_config.get('model', '')
            emb_dims = str(embedding_config.get('dimensions', ''))
            
            if not emb_model or not emb_dims:
                return base_name
                
            # Sanitize model name for collection (alphanumeric, -, _)
            safe_model = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in emb_model)
            return f"{base_name}__{safe_model}__{emb_dims}"
        except Exception:
            return base_name

    def close(self):
        """Close database connections"""
        try:
            if getattr(self, 'mb_conn', None):
                try:
                    self.mb_conn.close()
                    logger.info("Closed MariaDB connection")
                except Exception as e:
                    logger.warning(f"Error closing MariaDB connection: {e}")
                finally:
                    # Keep the mb_conn reference for tests to assert close() called on the underlying
                    # fake connection. Production code can still rely on a closed connection being
                    # unusable; `ensure_conn()` will reconnect when needed.
                    pass
        except Exception as e:
            logger.warning(f"Unexpected error during close: {e}")

    def ensure_conn(self):
            """Ensure the MariaDB connection is active; reconnect when needed."""
            try:
                # If no mb_conn set, or it's disconnected, re-create connection
                if not getattr(self, 'mb_conn', None) or not getattr(self.mb_conn, 'is_connected', lambda: False)():
                    logger.debug("MariaDB connection not active; attempting reconnect")
                    mb_cfg = getattr(self, '_mariadb_config', None) or self.config['database'].get('mariadb', {})
                    # Build params for mysql.connector.connect
                    params = {
                        'host': mb_cfg.get('host'),
                        'port': int(mb_cfg.get('port')) if mb_cfg.get('port') else None,
                        'user': mb_cfg.get('user'),
                        'database': mb_cfg.get('database'),
                        'autocommit': False,
                        'use_pure': True
                    }
                    # Only include password if it's not empty (for passwordless authentication)
                    if mb_cfg.get('password'):
                        params['password'] = mb_cfg.get('password')
                    # Remove None values
                    params = {k: v for k, v in params.items() if v is not None}
                    self.mb_conn = mysql.connector.connect(**params)
                    logger.info("Reconnected to MariaDB")
            except Exception as e:
                logger.warning(f"Failed to ensure MariaDB connection: {e}")
                raise

    def get_connection(self):
        """Create a fresh MariaDB connection using the service's configuration.

        This is intended for short-lived / per-request DB usage where a single
        shared connection object would otherwise be shared across concurrent
        callers and can surface 'Unread result found' errors. Callers that use
        get_connection() must close the returned connection when done.
        """
        mb_cfg = getattr(self, '_mariadb_config', None) or self.config['database'].get('mariadb', {})
        params = {
            'host': mb_cfg.get('host'),
            'port': int(mb_cfg.get('port')) if mb_cfg.get('port') else None,
            'user': mb_cfg.get('user'),
            'database': mb_cfg.get('database'),
            'autocommit': False,
            'use_pure': True,
        }
        if mb_cfg.get('password'):
            params['password'] = mb_cfg.get('password')
        params = {k: v for k, v in params.items() if v is not None}
        logger.debug("MigratedDatabaseService.get_connection: creating new per-call MariaDB connection")
        return mysql.connector.connect(**params)

    def get_safe_cursor(self, *, per_call: bool = False, dictionary: bool = False, buffered: bool = True):
        """
        Helper to obtain a 'safe' cursor for use by callers.

        - If per_call is True this will create a fresh connection (via get_connection()),
          and return (cursor, connection) where the caller is responsible for closing
          both cursor and connection.
        - If per_call is False we fall back to the shared `self.mb_conn` connection and
          return (cursor, None). The returned cursor will respect the `buffered` and
          `dictionary` flags.

        This should reduce risk of 'Unread result found' by encouraging per-call
        connections for high-concurrency call sites while still supporting
        backward-compatible usage.
        """
        try:
            if per_call:
                conn = self.get_connection()
                cursor = conn.cursor(buffered=buffered, dictionary=dictionary)
                logger.debug("get_safe_cursor: using per-call connection %s (id=%s)", conn, id(conn))
                return cursor, conn
            # fallback to shared connection
            self.ensure_conn()
            cursor = self.mb_conn.cursor(buffered=buffered, dictionary=dictionary)
            logger.debug("get_safe_cursor: using shared connection %s (id=%s)", self.mb_conn, id(self.mb_conn))
            return cursor, None
        except Exception as e:
            logger.warning(f"Failed to obtain safe cursor: {e}")
            raise

    def get_article_by_id(self, article_id: Union[int, str]) -> Optional[Article]:
        """Get article by ID from MariaDB"""
        try:
            # Ensure connection is alive and reconnected if needed
            self.ensure_conn()
            cursor = self.mb_conn.cursor()
            query = """
            SELECT id, url, title, content, summary, analyzed, source_id,
                   created_at, updated_at, normalized_url, url_hash, url_hash_algo,
                   language, section, tags, authors, raw_html_ref, extraction_confidence,
                   needs_review, review_reasons, extraction_metadata, structured_metadata,
                   publication_date, metadata, collection_timestamp
            FROM articles WHERE id = %s
            """
            cursor.execute(query, (article_id,))
            row = cursor.fetchone()
            cursor.close()

            if row:
                return Article.from_row(row)
            return None

        except Exception as e:
            logger.error(f"Failed to get article {article_id}: {e}")
            return None

    def get_source_by_id(self, source_id: Union[int, str]) -> Optional[Source]:
        """Get source by ID from MariaDB"""
        try:
            # Ensure connection is alive and reconnected if needed
            self.ensure_conn()
            cursor = self.mb_conn.cursor()
            query = """
            SELECT id, url, domain, name, description, country, language,
                   paywall, paywall_type, last_verified, metadata, created_at, updated_at
            FROM sources WHERE id = %s
            """
            cursor.execute(query, (source_id,))
            row = cursor.fetchone()
            cursor.close()

            if row:
                return Source.from_row(row)
            return None

        except Exception as e:
            logger.error(f"Failed to get source {source_id}: {e}")
            return None

    def semantic_search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Perform semantic search using ChromaDB + MariaDB"""
        try:
            if not self.collection:
                logger.warning("ChromaDB collection not initialized - semantic search unavailable")
                return []
            # Embed the query. Some embedding providers return numpy-like arrays
            # with a `.tolist()` method; others (mocks/tests) may return a plain
            # Python list. Handle both possibilities.
            emb = self.embedding_model.encode(query)
            if hasattr(emb, 'tolist'):
                query_embedding = emb.tolist()
            else:
                # Ensure it's a plain list copy so downstream code can index it
                query_embedding = list(emb)

            # Search ChromaDB for similar articles
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=['metadatas', 'documents', 'distances']
            )

            # Enrich results with full article data from MariaDB
            enriched_results = []
            for article_id, metadata, distance in zip(
                results['ids'][0],
                results['metadatas'][0],
                results['distances'][0]
            ):
                # Get full article from MariaDB
                article = self.get_article_by_id(article_id)
                if article:
                    # Get source information
                    source = None
                    if article.source_id:
                        source = self.get_source_by_id(article.source_id)

                    enriched_results.append({
                        'article': article.to_dict(),
                        'source': source.to_dict() if source else None,
                        'similarity_score': 1.0 - distance,  # Convert distance to similarity
                        'metadata': metadata
                    })

            return enriched_results

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    def search_articles_by_text(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search articles by text content in MariaDB"""
        try:
            self.ensure_conn()
            cursor = self.mb_conn.cursor(dictionary=True)
            search_query = """
            SELECT a.*,
                   s.name as source_name,
                   s.domain as source_domain
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            WHERE a.title LIKE %s OR a.content LIKE %s OR a.summary LIKE %s
            ORDER BY a.created_at DESC
            LIMIT %s
            """
            search_term = f"%{query}%"
            cursor.execute(search_query, (search_term, search_term, search_term, limit))
            results = cursor.fetchall()
            cursor.close()

            return results

        except Exception as e:
            logger.error(f"Text search failed: {e}")
            return []

    def get_recent_articles(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent articles from MariaDB"""
        try:
            self.ensure_conn()
            cursor = self.mb_conn.cursor(dictionary=True)
            query = """
            SELECT a.*,
                   s.name as source_name,
                   s.domain as source_domain
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            ORDER BY a.created_at DESC
            LIMIT %s
            """
            cursor.execute(query, (limit,))
            results = cursor.fetchall()
            cursor.close()

            return results

        except Exception as e:
            logger.error(f"Failed to get recent articles: {e}")
            return []

    def get_articles_by_source(self, source_id: Union[int, str], limit: int = 10) -> List[Dict[str, Any]]:
        """Get articles by source from MariaDB"""
        try:
            self.ensure_conn()
            cursor = self.mb_conn.cursor(dictionary=True)
            query = """
            SELECT a.*,
                   s.name as source_name,
                   s.domain as source_domain
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            WHERE a.source_id = %s
            ORDER BY a.created_at DESC
            LIMIT %s
            """
            cursor.execute(query, (source_id, limit))
            results = cursor.fetchall()
            cursor.close()

            return results

        except Exception as e:
            logger.error(f"Failed to get articles by source {source_id}: {e}")
            return []