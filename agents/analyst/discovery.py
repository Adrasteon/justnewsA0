"""
Discovery Agent - Slow Path for Living Stories
Clustering pending articles to discover new stories.
"""
import os
import json
import uuid
import numpy as np
try:
    import hdbscan
except ImportError:
    hdbscan = None

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

logger = get_logger(__name__)

def run_discovery_cycle():
    """Main discovery loop iteration."""
    logger.info("Starting Living Stories Discovery Cycle...")
    db = create_database_service()
    try:
        db.ensure_conn()

        # Best-effort hygiene: trim stale rows that can no longer contribute to discovery.
        # Safe criteria: very old rows whose backing article is missing or already synthesized.
        stale_ttl_hours = max(1, int(os.environ.get("LS_PENDING_POOL_TTL_HOURS", "72")))
        stale_purge_limit = max(1, int(os.environ.get("LS_PENDING_POOL_STALE_PURGE_LIMIT", "500")))
        stale_cursor = db.mb_conn.cursor()
        try:
            stale_cursor.execute(
                """
                DELETE p FROM pending_articles_pool p
                LEFT JOIN articles a ON a.id = p.article_id
                WHERE p.added_at < (NOW() - INTERVAL %s HOUR)
                  AND (a.id IS NULL OR COALESCE(a.is_synthesized, 0) = 1)
                LIMIT %s
                """,
                (stale_ttl_hours, stale_purge_limit),
            )
            removed_stale = int(stale_cursor.rowcount or 0)
            if removed_stale > 0:
                db.mb_conn.commit()
                logger.info(
                    "Pending pool stale cleanup removed %s rows (ttl=%sh, limit=%s)",
                    removed_stale,
                    stale_ttl_hours,
                    stale_purge_limit,
                )
        except Exception as cleanup_err:
            logger.warning("Pending pool stale cleanup skipped: %s", cleanup_err)
        finally:
            stale_cursor.close()
        
        # 1. Fetch all pending articles
        # We need vector_blob and article_id
        cursor = db.mb_conn.cursor(dictionary=True)
        pending = []
        try:
            cursor.execute("SELECT article_id, vector_blob, source_domain FROM pending_articles_pool")
            rows = cursor.fetchall()
            for r in rows:
                try:
                    if r['vector_blob']:
                        vec = json.loads(r['vector_blob'])
                        pending.append({
                            'id': r['article_id'],
                            'vector': vec,
                            'domain': r['source_domain']
                        })
                except Exception as e:
                    logger.warning(f"Bad vector blob for {r['article_id']}: {e}")
        finally:
            cursor.close()
            
        if not pending:
            logger.info("No pending articles found.")
            return

        min_sources = int(os.environ.get("LS_MIN_SOURCES_FOR_CREATION", "3"))
        
        logger.info(f"Processing {len(pending)} pending articles. Config min_sources={min_sources}")
        
        if len(pending) < min_sources:
             # Not enough to form a cluster
             return

        # 2. HDBSCAN Clustering
        data = np.array([p['vector'] for p in pending])
        
        # HDBSCAN parameters
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_sources,
            min_samples=1, # Allow small dense clusters
            cluster_selection_epsilon=0.0, # Default
            metric='euclidean' # Assuming normalized vectors, euclidean is ok proxy for cosine
        )
        labels = clusterer.fit_predict(data)
        
        # 3. Process Clusters
        unique_labels = set(labels)
        
        for label in unique_labels:
            if label == -1:
                continue # Noise
            
            # Get indices
            indices = [i for i, x in enumerate(labels) if x == label]
            cluster_articles = [pending[i] for i in indices]
            
            # Check Source Diversity
            domains = set(a['domain'] for a in cluster_articles)
            if len(domains) < min_sources:
                 # Not diverse enough yet. Leave in pending.
                 continue
            
            # Create Living Story!
            logger.info(f"Found new cluster! Label {label}, Size {len(cluster_articles)}, Domains {len(domains)}")
            
            # Calculate Centroid
            vectors = np.array([a['vector'] for a in cluster_articles])
            centroid = np.mean(vectors, axis=0)
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm
            centroid_list = centroid.tolist()
            
            # Create Story
            story_id = uuid.uuid4().hex
            title = f"Emerging Story - {len(cluster_articles)} sources" # Placeholder title
            
            try:
                # Need cursor again
                cur = db.mb_conn.cursor()
                
                # Insert LivingStory
                cur.execute(
                    """
                    INSERT INTO living_stories (id, title, semantic_centroid, status, created_at, last_updated_at)
                    VALUES (%s, %s, %s, 'active', NOW(), NOW())
                    """,
                    (story_id, title, json.dumps(centroid_list))
                )
                
                # Insert StoryUpdate
                update_id = uuid.uuid4().hex
                article_ids = [a['id'] for a in cluster_articles]
                cur.execute(
                    """
                    INSERT INTO story_updates (id, story_id, article_ids, article_count, batch_centroid, timestamp)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    """,
                    (update_id, story_id, json.dumps(article_ids), len(article_ids), json.dumps(centroid_list))
                )
                
                # Update Active Chroma Collection
                if getattr(db, "chroma_client", None):
                    try:
                        try:
                            coll = db.chroma_client.get_collection("active_living_stories")
                        except Exception:
                            coll = db.chroma_client.get_or_create_collection(
                                name="active_living_stories",
                                metadata={"hnsw:space": "cosine"},
                            )
                        coll.add(
                            ids=[story_id],
                            embeddings=[centroid_list],
                            metadatas=[{"title": title}]
                        )
                    except Exception as ce:
                        logger.error(f"Failed to add to Chroma: {ce}")

                # Purge from Pending Pool
                placeholders = ', '.join(['%s'] * len(article_ids))
                cur.execute(f"DELETE FROM pending_articles_pool WHERE article_id IN ({placeholders})", article_ids)
                
                db.mb_conn.commit()
                cur.close()
                logger.info(f"Created Living Story {story_id}")
                
            except Exception as e:
                logger.error(f"Failed to create story for cluster {label}: {e}")
                db.mb_conn.rollback()

    except Exception as e:
        logger.error(f"Discovery cycle failed: {e}")
    finally:
        db.close()
