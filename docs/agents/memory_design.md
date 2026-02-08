# Memory Agent — Design and Interfaces

Responsibilities

- Normalize and persist ingested articles into structured DBs (MariaDB) and vector stores (Chroma or alternative).

- Provide APIs for article retrieval, embedding lookup, and recall for downstream agents.

- Emit ingestion metrics and provide idempotent ingestion semantics.

Files of interest

- `agents/memory/memory_engine.py` — core ingestion logic

- `database/` — migrations and models

Ingest API (example)

- MCP call `memory.ingest_article` payload fields:

- `site_id`(str),`url`(str),`title`(str),`cleaned_text` (str),

- `extraction_metadata`(dict),`source_html_path` (str, optional),

- `ingest_meta` (dict: source, run_id, provenance)

- MCP call `memory.embed_article` payload fields:

- `article_id` (int)

Processing steps

1. Validate and normalise payload (ensure `site_id` is string, truncate extreme fields).

1. **Ingestion**: Compute or fetch embeddings for `cleaned_text` and persist to vector DB (optional synchronous embedding).

1. **Embedding (Deferred)**: Trigger `memory.embed_article` to generating embeddings for an existing article ID (Backfill/Async support).

1. Persist structured metadata and pointers to archive storage in MariaDB.

1. Return ingest result including `article_id` and status.

Idempotency

- Use content hash or `site_id+url` deterministic keys to ensure duplicate ingestion is avoided.

Observability

- Emit `ingest_total`,`ingest_errors`,`ingest_latency` metrics.

Testing

- Unit tests for payload validation and DB writes.

- Integration tests with local Chroma instance (or a mocked vector store) for embedding persistence.
