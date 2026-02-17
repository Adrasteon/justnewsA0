# Agent API Signatures and Payload Contracts

This file summarizes key API endpoints, MCP call signatures, and payload shapes used across agents. Use this as a
reference when implementing tests, forwarders, or new integrations.

1) HITL Service (HTTP API)

- `POST /candidates`

- Body (JSON):

  - `id`: string (candidate id)

  - `url`: string

  - `site_id`: string

  - `title`: string

  - `extracted_text`: string

  - `extraction_metadata`: object

  - `publish_time`: iso8601 string (optional)

- Response: `{ "candidate_id": "..." }`

- `POST /labels`

- Body: `{ "candidate_id": "...", "label": "accept|reject|review", "user": "...", "comment": "..." }`

- Response: `{ "label_id": "...", "ingestion_status": "pending" }`

2) MCP Bus calls (agent-to-agent RPC)

- `memory.ingest_article`

- Payload (JSON):

  - `site_id`(str),`url`(str),`title`(str),`cleaned_text` (str),

  - `extraction_metadata`(dict),`source_html_path` (str, optional),

  - `ingest_meta`(dict:`run_id`,`source`,`submitted_by`)

- Return: `{ "article_id": <int|string>, "status": "ok" }`

- `memory.embed_article`

- Payload (JSON):

  - `article_id`: int

- Fetches the article content for the given ID, generates embeddings, and persists them to the vector store (ChromaDB). Updates the database `embedded` flag to 1.

- Return: `{ "status": "success", "article_id": <int> }`

- `archive.queue_article`

- Payload (JSON): `ingest_payload`produced by HITL service (`candidate`,`cleaned_text`,`label_*` fields)

- Normalizes URLs, hashes, authors, tags, and forwards to Stage B storage

- Return: `{ "status": "success|duplicate", "article_id": <int>, "job_id": "..." }`

3) Crawl4AI adapter expectations

- `crawl_site_with_crawl4ai(site_config, profile, max_articles)`returns`list[dict]` where each dict contains:

- `url`,`cleaned_html`/`markdown`or`html`,`metadata`,`links`(internal/external),`score`

3.1) Crawler Control advanced crawl contract (`localhost:8016`)

- `POST /api/crawl/start`

- Supports standard crawl controls plus optional `crawl4ai` object that is translated into per-domain `profile_overrides`.

- Key advanced fields in `crawl4ai`:

  - `crawl_depth` (max link-hop depth), `max_pages`, `follow_internal_links`, `follow_external`

  - `run_config`, `browser_config`, `link_preview`, `adaptive`, `extra`, `start_urls`

- Programmatic route: `POST /start_crawl` accepts equivalent options via `kwargs.crawl4ai` / `kwargs.profile_overrides`.

- Discovery route: `GET /api/crawl/options` returns supported option keys and example payload.

- See detailed guidance: `docs/agents/crawler_control_options.md`

4) Archive / Storage agent

- `archive.queue_article`

- Payload: `{ "candidate": {...}, "cleaned_text": "...", "label_id": "..." }`

- Persists canonical metadata via `memory.save_article`, emits Stage B ingest metrics, returns duplicates when detected

Notes on versioning and backward compatibility

- Keep payloads additive. New fields should be optional; consumers should fallback gracefully when fields missing.

- Use `site_id` as string across all payloads to avoid schema mismatch.
