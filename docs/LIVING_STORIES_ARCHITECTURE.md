# Living Stories Architecture (v3)

## Overview
"Living Stories" is a feature that dynamically clusters news articles into evolving event narratives. Unlike static clustering, Living Stories persist over time, allowing new updates to be merged into existing stories ("Fast Path") or new stories to be discovered from unassigned articles ("Slow Path").

## Architecture

The system uses an **Assign-or-Buffer** strategy with a **Phased Workflow**.

### 1. Data Models
*   **`LivingStory`** (`living_stories`): Represents a cluster.
    *   `id` (UUID)
    *   `semantic_centroid` (JSON list of floats): The current center of the story in vector space.
    *   `status`: `active`, `dormant`, or `archived`.
*   **`StoryUpdate`** (`story_updates`): A record of a batch of articles added to a story.
    *   `batch_centroid`: The centroid of the specific update batch.
*   **`PendingArticle`** (`pending_articles_pool`): The "waiting room" for articles that didn't match an existing story.
    *   `vector_blob`: Pre-computed embedding to avoid re-inference.

### 2. Fast Path (Ingestion)
**Component**: `Memory Agent` (`save_article` in `agents/memory/tools.py`)

When an article is saved:
1.  **Vector Search**: The system queries the `active_living_stories` ChromaDB collection with the article's embedding.
2.  **Threshold Check**:
    *   If `Cosine Similarity > LS_SIMILARITY_THRESHOLD` (default 0.85):
        *   **Assign**: The article is linked to the `LivingStory`.
        *   **Update**: The story's centroid is updated (Drift Decay: `LS_DRIFT_DECAY_RATE`, default 0.2).
        *   **Record**: A `StoryUpdate` is created.
    *   If No Match:
        *   **Buffer**: The article is inserted into `pending_articles_pool`.

### 3. Slow Path (Discovery)
**Component**: `Analyst Agent` (`discovery_loop` in `agents/analyst/discovery.py`)

A background task runs every 5 minutes:
1.  **Fetch**: Retrieves all articles from `pending_articles_pool`.
2.  **Filter**: Checks if `count < LS_MIN_SOURCES_FOR_CREATION` (default 3).
3.  **Cluster**: Runs **HDBSCAN** on the pending vectors.
4.  **Promote**: For each dense cluster found:
    *   Checks source diversity (must be >= 3 unique domains).
    *   Creates a new `LivingStory`.
    *   Adds the centroid to ChromaDB `active_living_stories`.
    *   Removes articles from the pending pool.

## Configuration (`global.env`)

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `LS_SIMILARITY_THRESHOLD` | `0.85` | Cutoff for auto-merging an article into a story. |
| `LS_DRIFT_DECAY_RATE` | `0.2` | How much a new article shifts the story centroid. |
| `LS_MIN_SOURCES_FOR_CREATION` | `3` | Minimum pending articles/sources to form a new story. |

## Infrastructure
*   **Database**: MariaDB (tables defined in `justnews_publisher/news/models.py`).
*   **Vector Store**: ChromaDB (Collection: `active_living_stories`).
    *   *Note*: The `articles` collection is still used for general RAG. `active_living_stories` is a specialized optimization index.
