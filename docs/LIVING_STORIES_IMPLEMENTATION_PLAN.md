# JustNews "Living Stories" Implementation Plan

**Date:** February 1, 2026
**Status:** Draft (v3) - Includes Config & Chroma Strategy
**Target Architecture:** Assign-or-Buffer (Fast/Slow Path) with Autonomous Drift

---

## 1. Executive Summary

### The Problem
Single-source crawling results in sparse article batches that fail density-based clustering (HDBSCAN). Meanwhile, standard Snapshot Clustering forgets narrative history.
- **Scenario:** We crawl CNN, get 1 article on "Event X". HDBSCAN sees it as noise (no density). Later, we crawl BBC, get 1 article. Still noise. Discovery fails.

### The Solution: Assign-or-Buffer
We bifurcate the pipeline:
1.  **Fast Path (Update)**: Check every new article against existing stories immediately using Vector Search.
2.  **Slow Path (Discovery)**: Buffer unmatched articles in a **Pending Pool** until enough sources (defined in `global.env`) corroborate the event.

---

## 2. Architecture Proposal

### 2.1. Path 1: The Fast Path (Ingestion)
*Objective: Latency-free updates for known stories.*

1.  **Ingest & Vectorize**: Crawler fetches a single article (embedding generated via `sentence-transformers`).
2.  **Lookup**: Query **ChromaDB** (`active_living_stories` collection) for the nearest centroid.
3.  **Decision**:
    *   **Match**: If Distance < `LS_SIMILARITY_THRESHOLD` AND Entity Overlap > `LS_ENTITY_OVERLAP_THRESHOLD`:
        *   Action: Create `StoryUpdate` (MariaDB).
        *   Action: Update `LivingStory` centroid in ChromaDB (Drift).
    *   **No Match**:
        *   Action: Insert into `pending_articles_pool` (MariaDB) + Cache Vector.

### 2.2. Path 2: The Slow Path (Discovery)
*Objective: Noise-resistant creation of new stories.*

1.  **Accumulate**: The `PendingPool` collects unmatched articles from various sources (CNN, BBC, Local).
2.  **Cluster (Cron Job)**: Periodically, `DiscoveryAgent` runs **HDBSCAN** on the Pending Pool vectors.
3.  **Resolution**:
    *   **Dense Cluster Found**:
        *   Condition: Cluster Size >= `LS_MIN_SOURCES_FOR_CREATION` (e.g., 3).
        *   Safety: Double-check Centroid vs Active Stories (prevent split-brain).
        *   Action: Create **NEW** `LivingStory` in MariaDB + ChromaDB.
        *   Action: Move articles to `StoryUpdate`.
    *   **Noise**: Leave in pool (waiting for more sources).
    *   **Expired**: If `added_at` > `LS_PENDING_TTL_HOURS`, move to `ArchivedSingleton`.

### 2.3. Autonomous Evolution
*   **Rolling Centroids**: We use a weighted moving average to allow stories to evolve.
    *   $C_{new} = (C_{old} \times (1 - \text{Decay})) + (V_{update} \times \text{Decay})$
    *   Controlled by `LS_DRIFT_DECAY_RATE`.

### 2.4. Phased Workflow Orchestration
To prevent resource contention, the system will execute in 4 sequential phases:
1.  **Ingestion & Encryption (Phase 1)**: Crawl -> Parse -> Vectorize.
    *   *Exit Condition*: Crawler finished AND No un-enriched articles remaining.
2.  **Clustering & Linkage (Phase 2)**: Fast/Slow Path clustering.
    *   *Exit Condition*: All pending articles processed/pooled.
3.  **Synthesis (Phase 3)**: LLM Generation.
    *   *Trigger*: New `StoryUpdate` exists AND Phase 2 Complete.
4.  **Publication (Phase 4)**: CMS Push.

---

## 3. Data Model & Infrastructure Changes

### A. Database (MariaDB/Django)
We **DO** need schema changes.
1.  **`living_stories` Table**:
    *   `id` (UUID), `title`, `status` (`ACTIVE`/`DORMANT`), `created_at`, `last_updated_at`.
2.  **`story_updates` Table**:
    *   `id` (UUID), `story_id` (FK), `article_count`, `batch_centroid` (JSON/Blob is sufficient here).
3.  **`pending_articles_pool` Table**:
    *   `article_id` (OneToOne with `Article`), `source_domain`, `vector_blob` (optimization to avoid re-querying Chroma), `added_at`.

### B. Vector Store (ChromaDB)
We **DO** need a NEW collection.
1.  **`active_living_stories` Collection**:
    *   **Purpose**: Stores the current rolling centroid of every `ACTIVE` story.
    *   **Metadata**: `{"story_id": "...", "last_updated": "...", "title": "..."}`.
    *   **Why**: Enables $O(1)$ semantic search during the Fast Path (Ingestion) without loading all story vectors into memory. Active stories are removed from this collection when they go `DORMANT` (status update).

---

## 4. Configuration Strategy (global.env)
All critical logic thresholds must be externalized to `global.env` for tuning.

| Variable Name | Default | Description |
| :--- | :--- | :--- |
| **`LS_MIN_SOURCES_FOR_CREATION`** | `3` | Minimum unique sources required in a cluster to spawn a new Living Story. |
| **`LS_ACTIVE_WINDOW_DAYS`** | `7` | Days a story remains `ACTIVE` without updates before going `DORMANT`. |
| **`LS_PENDING_TTL_HOURS`** | `48` | How long an unmatched article waits in the pool before being archived as noise. |
| **`LS_SIMILARITY_THRESHOLD`** | `0.85` | Cosine similarity score required to auto-merge an article into a story. |
| **`LS_ENTITY_OVERLAP_THRESHOLD`**| `0.4` | Percentage of Named Entities that must match for safety. |
| **`LS_DRIFT_DECAY_RATE`** | `0.2` | How much a new update shifts the story's centroid (0.0=Static, 1.0=Instant). |

---

## 5. Implementation Steps

### Phase 1: Environment & Config
*   Update `environment.yml` (`hdbscan`, `umap-learn`).
*   Update `global.env` with the new constants.
*   Update `dashboard_config.json` to expose these constants for viewing.

### Phase 2: Infrastructure
*   **Django**: Create models for `LivingStory`, `StoryUpdate`, `PendingArticle`.
*   **Chroma**: Create utility script to initialize/reset `active_living_stories` collection.

### Phase 3: Logic Implementation
*   **IngestionWorker**: Hook into the save pipeline -> Check `active_living_stories` -> Assign or Pool.
*   **DiscoveryAgent**: Create the "Slow Path" cron job (Fetch Pool -> HDBSCAN -> Create Story).

### Phase 4: Dashboard
*   Add Visualizations: "Pending Pool Size", "Active Stories Count".
*   Add Controls: "Force Merge" (HITL).

## 6. Success Metrics
*   **Reduction in fragments**: Same story from 3 sources becomes 1 Living Story.
*   **Drift Handling**: An "Election" story seamlessly transitions to "Results" without needing a new ID.
*   **Zero-Touch**: System runs indefinitely without manual training, only occasional cleanup.

