import os
import sys
import json
import uuid
from datetime import datetime, timedelta
import numpy as np

# Ensure Repo Root is FIRST in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# If script is in scripts/, root is up one level
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

if REPO_ROOT in sys.path:
    sys.path.remove(REPO_ROOT)
sys.path.insert(0, REPO_ROOT)

# WARNING: 'common.observability' import is failing due to circular imports or path issues in this environment.
# We will define a simple local logger to bypass this for the bootstrap script.
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("bootstrap_living_stories")
def get_logger(name): return logger

try:
    # We still need database utils, but they import observability internally.
    # If that fails, we might need to mock sys.modules['common.observability']
    import sys
    from types import ModuleType
    if 'common.observability' not in sys.modules:
        m = ModuleType('common.observability')
        m.get_logger = get_logger
        m.bootstrap_observability = lambda *args, **kwargs: None
        sys.modules['common.observability'] = m
    
    # Also Mock common.json_utils if needed, or rely on pythonpath
    # The previous error "No module named 'common.json_utils'" implies pythonpath is still not sticking for sub-imports
    # despite PYTHONPATH env var.
    # We will try to rely on the sys.path.insert(0, REPO_ROOT) we did above.
        
    from database.utils.migrated_database_utils import create_database_service
except ImportError:
    # Manual Fallback if path hack fails unexpectedly
    import logging
    logging.basicConfig(level=logging.INFO)
    def get_logger(name): return logging.getLogger(name)

from database.utils.migrated_database_utils import create_database_service
# We need an embedding model. Use the tool helper.
from agents.memory.tools import get_embedding_model

logger = get_logger("bootstrap_living_stories")

def bootstrap():
    logger.info("Starting Living Stories Bootstrap (Last 7 Days)")
    
    db = create_database_service()
    try:
        db.ensure_conn()
    except Exception as e:
        logger.error(f"DB Connection failed: {e}")
        return

    # Initialize Embedding Model
    logger.info("Loading embedding model (this may take a moment)...")
    model = get_embedding_model()
    if not model:
        logger.error("Failed to load embedding model")
        return

    # Configuration
    ls_threshold = float(os.environ.get("LS_SIMILARITY_THRESHOLD", "0.85"))
    ls_decay = float(os.environ.get("LS_DRIFT_DECAY_RATE", "0.2"))
    
    # 1. Fetch Articles
    days = 7
    cutoff = datetime.now() - timedelta(days=days)
    logger.info(f"Fetching articles since {cutoff}")
    
    cursor = db.mb_conn.cursor(dictionary=True)
    articles = []
    try:
        query = "SELECT id, content, metadata, created_at FROM articles WHERE created_at >= %s ORDER BY created_at ASC"
        cursor.execute(query, (cutoff,))
        articles = cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to fetch articles: {e}")
        return
    finally:
        cursor.close()
        
    logger.info(f"Found {len(articles)} articles to process.")
    
    # Pre-check Chroma Collection
    try:
        ls_collection = db.chroma_client.get_collection("active_living_stories")
    except Exception:
        logger.error("Active Living Stories collection not found. Run setup script first.")
        return
    
    # Try to grab the main articles collection to key-off existing embeddings (Optimization)
    main_collection = None
    try:
        main_collection = db.chroma_client.get_collection("articles")
    except Exception:
        pass

    processed = 0
    assigned = 0
    buffered = 0
    errors = 0

    for art in articles:
        try:
            aid = art['id']
            content = art['content']
            if not content:
                continue
            
            # --- Get Embedding ---
            embedding = None
            if main_collection:
                try:
                    # Chroma usually returns dict with 'embeddings': [[...]] or None
                    res = main_collection.get(ids=[str(aid)], include=["embeddings"])
                    if res and res.get('embeddings') and len(res['embeddings']) > 0:
                        embedding = res['embeddings'][0]
                except Exception:
                    pass
            
            if not embedding:
                # Fallback to model inference
                embedding = model.encode(content).tolist()
            
            # --- Assign-or-Buffer Logic ---
            match_found = False
            
            # Query Active Stories
            # Note: Chroma expects list of list for query
            query_vec = embedding if isinstance(embedding, list) else embedding.tolist()
            
            results = ls_collection.query(
                query_embeddings=[query_vec],
                n_results=1,
                include=["embeddings", "distances", "metadatas"]
            )
            
            if results["ids"] and len(results["ids"][0]) > 0:
                distance = results["distances"][0][0]
                # Cosine distance: 0=identical, 2=opposite. Similarity = 1 - distance
                if distance < (1.0 - ls_threshold):
                    match_found = True
                    story_id = results["ids"][0][0]
                    old_centroid = results["embeddings"][0][0]
                    
                    # Calculate new centroid
                    req_vec = np.array(query_vec)
                    cur_vec = np.array(old_centroid)
                    new_vec = (cur_vec * (1 - ls_decay)) + (req_vec * ls_decay)
                    
                    # Normalize
                    norm = np.linalg.norm(new_vec)
                    if norm > 0:
                        new_vec = new_vec / norm
                    new_centroid = new_vec.tolist()
                    
                    # 1. Update Chroma
                    ls_collection.update(
                        ids=[story_id],
                        embeddings=[new_centroid]
                    )
                    
                    # 2. Update DB
                    cursor = db.mb_conn.cursor()
                    cursor.execute(
                        "UPDATE living_stories SET last_updated_at = NOW(), semantic_centroid = %s WHERE id = %s",
                        (json.dumps(new_centroid), story_id)
                    )
                    
                    # 3. Add StoryUpdate
                    update_id = str(uuid.uuid4())
                    cursor.execute(
                        """
                        INSERT INTO story_updates (id, story_id, article_ids, article_count, batch_centroid, timestamp)
                        VALUES (%s, %s, %s, 1, %s, NOW())
                        """,
                        (update_id, story_id, json.dumps([aid]), json.dumps(new_centroid))
                    )
                    db.mb_conn.commit()
                    cursor.close()
                    assigned += 1

            if not match_found:
                # Buffer
                metadata = {}
                if isinstance(art['metadata'], str):
                    try: metadata = json.loads(art['metadata'])
                    except: pass
                elif isinstance(art['metadata'], dict):
                    metadata = art['metadata']
                    
                domain = metadata.get("domain") or "unknown"
                vector_blob = json.dumps(query_vec)
                
                cursor = db.mb_conn.cursor()
                # Use INSERT IGNORE or ON DUPLICATE to allow re-runs
                cursor.execute(
                    """
                    INSERT INTO pending_articles_pool (article_id, source_domain, vector_blob, added_at)
                    VALUES (%s, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE 
                        vector_blob = VALUES(vector_blob),
                        source_domain = VALUES(source_domain)
                    """,
                    (aid, domain, vector_blob)
                )
                db.mb_conn.commit()
                cursor.close()
                buffered += 1

            processed += 1
            if processed % 100 == 0:
                logger.info(f"Processed {processed}/{len(articles)}...")
                
        except Exception as e:
            logger.error(f"Error processing article {art.get('id')}: {e}")
            errors += 1
            
    logger.info(f"Bootstrap Complete. Processed: {processed}, Assigned: {assigned}, Buffered: {buffered}, Errors: {errors}")
    db.close()

if __name__ == "__main__":
    bootstrap()
