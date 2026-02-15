"""
Workflow Policies for the Orchestrator.

This module defines the abstract base class and concrete implementations
for data pipeline transitions.
"""

from abc import ABC, abstractmethod
from typing import List, Any
import requests
import asyncio
import os
import json
import uuid
import time
import hashlib
from difflib import SequenceMatcher
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

logger = get_logger(__name__)


def _safe_json_list(raw_value: Any) -> list[int]:
    if raw_value is None:
        return []
    try:
        parsed = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[int] = []
    for item in parsed:
        try:
            out.append(int(item))
        except Exception:
            continue
    return out


def _normalize_text_for_diff(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(str(text).lower().split())


def _text_similarity(left: str | None, right: str | None) -> float:
    a = _normalize_text_for_diff(left)
    b = _normalize_text_for_diff(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _cluster_input_fingerprint(article_ids: list[int]) -> str:
    normalized = sorted({int(x) for x in article_ids})
    payload = ",".join(str(x) for x in normalized)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_json_dict(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def upsert_living_story_record(
    db_service,
    cluster_id: str,
    article_ids: list[int],
    title_text: str,
    body_text: str,
) -> dict[str, Any]:
    normalized_ids = sorted({int(x) for x in article_ids})
    input_arts_json = json.dumps(normalized_ids)
    fingerprint = _cluster_input_fingerprint(normalized_ids)
    now_iso = datetime.utcnow().isoformat() + "Z"

    major_delta = float(os.environ.get("LIVING_STORY_MAJOR_TEXT_DELTA", "0.12"))
    minor_delta = float(os.environ.get("LIVING_STORY_MINOR_TEXT_DELTA", "0.03"))
    min_new_articles = int(os.environ.get("LIVING_STORY_MIN_NEW_ARTICLES", "2"))

    db_service.ensure_conn()
    cursor = db_service.mb_conn.cursor()
    cursor.execute(
        """
        SELECT story_id, body, input_articles, synth_metadata, is_published
        FROM synthesized_articles
        WHERE cluster_id = %s
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (cluster_id,),
    )
    existing = cursor.fetchone()

    if not existing:
        story_id = f"STORY-{uuid.uuid4().hex[:8]}"
        synth_metadata = {
            "living_story": {
                "revision": 1,
                "input_fingerprint": fingerprint,
                "last_meaningful_score": 1.0,
                "last_new_articles": len(normalized_ids),
                "last_update_action": "created",
                "updated_at": now_iso,
            }
        }
        cursor.execute(
            """
            INSERT INTO synthesized_articles
            (story_id, cluster_id, input_articles, title, body, created_at, updated_at, is_published, critique_status, synth_metadata)
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), 0, 'pending', %s)
            """,
            (story_id, cluster_id, input_arts_json, title_text, body_text, json.dumps(synth_metadata)),
        )
        return {
            "story_id": story_id,
            "action": "created",
            "meaningful": True,
            "new_article_count": len(normalized_ids),
            "text_delta": 1.0,
        }

    story_id, prev_body, prev_input_articles, prev_meta_raw, _is_published = existing
    prev_ids = _safe_json_list(prev_input_articles)
    prev_ids_set = set(prev_ids)
    new_ids_set = set(normalized_ids)
    new_article_count = len(new_ids_set - prev_ids_set)
    similarity = _text_similarity(prev_body, body_text)
    text_delta = 1.0 - similarity

    meaningful = (
        text_delta >= major_delta
        or (new_article_count > 0 and text_delta >= minor_delta)
        or new_article_count >= min_new_articles
    )

    previous_meta = _load_json_dict(prev_meta_raw)
    living_story_meta = previous_meta.get("living_story", {}) if isinstance(previous_meta.get("living_story"), dict) else {}
    previous_revision = int(living_story_meta.get("revision", 1)) if living_story_meta else 1
    revision = previous_revision + 1 if meaningful else previous_revision

    next_meta = previous_meta.copy()
    next_meta["living_story"] = {
        "revision": revision,
        "input_fingerprint": fingerprint,
        "last_meaningful_score": round(text_delta, 4),
        "last_new_articles": new_article_count,
        "last_update_action": "updated" if meaningful else "tracked_noop",
        "updated_at": now_iso,
    }

    if meaningful:
        cursor.execute(
            """
            UPDATE synthesized_articles
            SET title = %s,
                body = %s,
                input_articles = %s,
                synth_metadata = %s,
                updated_at = NOW(),
                is_published = 0,
                critique_status = 'pending',
                critique_text = NULL
            WHERE story_id = %s
            """,
            (title_text, body_text, input_arts_json, json.dumps(next_meta), story_id),
        )
    else:
        cursor.execute(
            """
            UPDATE synthesized_articles
            SET input_articles = %s,
                synth_metadata = %s,
                updated_at = NOW()
            WHERE story_id = %s
            """,
            (input_arts_json, json.dumps(next_meta), story_id),
        )

    return {
        "story_id": story_id,
        "action": "updated" if meaningful else "tracked_noop",
        "meaningful": meaningful,
        "new_article_count": new_article_count,
        "text_delta": round(text_delta, 4),
    }

class WorkflowPolicy(ABC):
    """Abstract base class for a workflow policy."""
    
    def __init__(self, mcp_bus_url: str):
        self.mcp_bus_url = mcp_bus_url
        self.db_service = create_database_service()

    @abstractmethod
    def name(self) -> str:
        """Name of the policy."""
        pass

    @abstractmethod
    def check_condition(self, limit: int) -> List[Any]:
        """Return a list of items (IDs) that match the condition."""
        pass

    @abstractmethod
    async def execute(self, items: List[Any]):
        """Execute the workflow action on the items."""
        pass
    
    def _call_mcp_tool_sync(self, agent: str, tool: str, kwargs: dict) -> dict:
        """Synchronous call to MCP Bus."""
        try:
            payload = {
                "agent": agent,
                "tool": tool,
                "kwargs": kwargs,
                "args": []
            }
            # Increase timeout for synthesis operations
            response = requests.post(f"{self.mcp_bus_url}/call", json=payload, timeout=300)
            response.raise_for_status()
            
            result = response.json()
            # Unwrap MCP Bus packet if it follows the status/data pattern
            if isinstance(result, dict) and result.get("status") == "success" and "data" in result:
                return result["data"]
                
            return result
        except Exception as e:
            logger.error(f"Failed to call {agent}.{tool}: {e}")
            return {"status": "error", "error": str(e)}

    async def _call_mcp_tool(self, agent: str, tool: str, kwargs: dict):
        """Async wrapper for MCP tool call."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._call_mcp_tool_sync, agent, tool, kwargs)


class IngestionToAnalysisPolicy(WorkflowPolicy):
    """
    Policy: Ingested -> Analyzed
    Condition: articles.analyzed = 0
    Action: Call 'analyst.analyze_article'
    """

    def name(self) -> str:
        return "ingestion_to_analysis"

    def check_condition(self, limit: int) -> List[int]:
        ids = []
        try:
            self.db_service.ensure_conn()
            # Commit any existing transaction to ensure we see fresh data
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            # Select unanalyzed articles, preferring newer ones
            query = """
                SELECT id FROM articles 
                WHERE analyzed = 0 
                ORDER BY created_at DESC 
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            # Try to reconnect on next pass
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[int]):
        logger.info(f"Triggering analysis for {len(items)} articles.")
        tasks = []
        for article_id in items:
            # We call the analyst agent via MCP Bus
            # Based on previous investigation, Analyst expects a ToolCall wrapped payload if called directly,
            # but via MCP bus, we send standard args/kwargs.
            # The MCP Bus 'call' endpoint takes: agent, tool, args, kwargs.
            # The Analyst 'analyze_article' tool expects a 'call: ToolCall' object if hitting the endpoint directly,
            # BUT wait.
            # Let's verify how MCP Bus calls the agent.
            # MCP Bus calls `{agent_address}/{tool_name}` with `{"args": ..., "kwargs": ...}`.
            # Analyst `analyze_article` endpoint expects `ToolCall` which has `args` and `kwargs`.
            # So MCP Bus payload matches Analyst expectation exactly.
            
            # Param: article_id via kwargs
            tasks.append(
                self._call_mcp_tool(
                    agent="analyst",
                    tool="analyze_article",
                    kwargs={"article_id": article_id}
                )
            )
        
        # Run concurrent triggers
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = 0
        for res in results:
            if isinstance(res, dict) and res.get("status") == "success":
                success_count += 1
            elif isinstance(res, Exception):
                logger.error(f"Task failed: {res}")
        
        logger.info(f"Triggered batch complete. Success: {success_count}/{len(items)}")


class AnalysisToEmbeddingPolicy(WorkflowPolicy):
    """
    Policy: Analyzed -> Embedded
    Condition: articles.analyzed = 1 AND articles.embedded = 0
    Action: Call 'memory.embed_article'
    """

    def name(self) -> str:
        return "analysis_to_embedding"

    def check_condition(self, limit: int) -> List[int]:
        ids = []
        try:
            self.db_service.ensure_conn()
            # Commit any existing transaction to ensure we see fresh data
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            # Select analyzed but not embedded articles
            query = """
                SELECT id FROM articles 
                WHERE analyzed = 1 AND embedded = 0
                ORDER BY created_at DESC 
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[int]):
        logger.info(f"Triggering embedding for {len(items)} articles.")
        tasks = []
        for article_id in items:
            tasks.append(
                self._call_mcp_tool(
                    agent="memory",
                    tool="embed_article",
                    kwargs={"article_id": article_id}
                )
            )
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = 0
        for res in results:
            if isinstance(res, dict) and res.get("status") == "success":
                success_count += 1
            elif isinstance(res, Exception):
                logger.error(f"Embedding task failed: {res}")
        
        logger.info(f"Embedding batch complete. Success: {success_count}/{len(items)}")


class AnalysisToSummaryPolicy(WorkflowPolicy):
    """
    Policy: Analyzed -> Summarized
    Condition: articles.analyzed = 1 AND (articles.summary IS NULL OR articles.summary = '')
    Action: Call 'synthesizer.summarize_article'
    """

    def name(self) -> str:
        return "analysis_to_summary"

    def check_condition(self, limit: int) -> List[int]:
        ids = []
        try:
            self.db_service.ensure_conn()
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            query = """
                SELECT id FROM articles 
                WHERE analyzed = 1 AND (summary IS NULL OR summary = '')
                ORDER BY created_at DESC 
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[int]):
        logger.info(f"Triggering summarization for {len(items)} articles.")
        tasks = []
        for article_id in items:
            tasks.append(
                self._call_mcp_tool(
                    agent="synthesizer",
                    tool="summarize_article",
                    kwargs={"article_id": article_id}
                )
            )
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = 0
        for res in results:
            if isinstance(res, dict) and res.get("status") == "success":
                success_count += 1
            elif isinstance(res, Exception):
                logger.error(f"Summarization task failed: {res}")
        
        logger.info(f"Summarization batch complete. Success: {success_count}/{len(items)}")


class SummaryToFactCheckPolicy(WorkflowPolicy):
    """
    Policy: Summarized -> Fact Checked
    Condition: articles.analyzed = 1 AND articles.summary IS NOT NULL AND articles.fact_check_status IS NULL
    Action: Call 'fact_checker.verify_article' (requires fact_checker agent update)
    """

    def name(self) -> str:
        return "summary_to_fact_check"

    def check_condition(self, limit: int) -> List[int]:
        ids = []
        try:
            self.db_service.ensure_conn()
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            query = """
                SELECT id FROM articles 
                WHERE analyzed = 1 
                  AND (summary IS NOT NULL AND summary != '')
                  AND fact_check_status IS NULL
                ORDER BY created_at DESC 
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[int]):
        logger.info(f"Triggering fact check for {len(items)} articles.")
        tasks = []
        for article_id in items:
            tasks.append(
                self._call_mcp_tool(
                    agent="fact_checker",
                    tool="verify_article",
                    kwargs={"article_id": article_id}
                )
            )
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = 0
        for res in results:
            if isinstance(res, dict) and res.get("status") == "success":
                success_count += 1
            elif isinstance(res, Exception):
                logger.error(f"Fact check task failed: {res}")
        
        logger.info(f"Fact check batch complete. Success: {success_count}/{len(items)}")



class IncrementalClusteringPolicy(WorkflowPolicy):
    """
    Policy: Fact Checked -> Clustered (Incremental)
    Condition: articles.fact_check_status IS NOT NULL 
               AND (articles.input_cluster_ids IS NULL OR articles.input_cluster_ids = '[]')
    Action: Query ChromaDB for neighbors. If close match found, join cluster. Else create new.
    """

    def name(self) -> str:
        return "incremental_clustering"

    def check_condition(self, limit: int) -> List[int]:
        ids = []
        try:
            self.db_service.ensure_conn()
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            
            # Process one by one or small batches.
            query = """
                SELECT id FROM articles 
                WHERE fact_check_status IS NOT NULL 
                      AND embedded = 1
                      AND (input_cluster_ids IS NULL OR input_cluster_ids = '[]' OR input_cluster_ids = '')
                ORDER BY created_at DESC
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[int]):
        if not items:
            return
            
        logger.info(f"Incremental clustering for {len(items)} articles.")
        
        # We need the collection to be available
        if not self.db_service.collection:
             logger.warning("ChromaDB collection not available. Skipping clustering.")
             return

        for article_id in items:
            try:
                # 1. Get Embedding
                # We cast ID to string as Chroma uses string IDs
                result = self.db_service.collection.get(
                    ids=[str(article_id)],
                    include=["embeddings"]
                )
                
                # Safe check for embeddings to avoid numpy ambiguity
                has_embedding = False
                if result and 'embeddings' in result:
                    embs = result['embeddings']
                    if embs is not None and len(embs) > 0:
                        has_embedding = True
                
                if not has_embedding:
                    logger.warning(f"No embedding found for article {article_id}. Skipping.")
                    continue
                    
                embedding = result['embeddings'][0]
                
                # 2. Query Neighbors
                # We look for nearest 5
                # We filter by distance < 0.5
                neighbors = self.db_service.collection.query(
                    query_embeddings=[embedding],
                    n_results=5,
                    include=["metadatas", "distances", "documents"]
                )
                
                found_cluster_id = None
                
                # Handling numpy/list ambiguity safely
                has_results = False
                if neighbors:
                    ids_list = neighbors.get('ids')
                    if ids_list and len(ids_list) > 0 and len(ids_list[0]) > 0:
                        has_results = True
                
                if has_results:
                    neighbor_ids = neighbors['ids'][0]
                    distances = neighbors['distances'][0]
                    
                    # Filter by distance
                    # 0.5 is significant. 0 is identical.
                    valid_neighbor_db_ids = []
                    for nid, dist in zip(neighbor_ids, distances):
                        if dist < 0.5 and str(nid) != str(article_id):
                            # nid is the chroma ID, which is str(article_id)
                            try:
                                valid_neighbor_db_ids.append(int(nid))
                            except:
                                pass
                    
                    if valid_neighbor_db_ids:
                        # Fetch cluster IDs of these neighbors
                        self.db_service.ensure_conn()
                        cursor = self.db_service.mb_conn.cursor()
                        format_strings = ','.join(['%s'] * len(valid_neighbor_db_ids))
                        cursor.execute(f"SELECT input_cluster_ids FROM articles WHERE id IN ({format_strings})", tuple(valid_neighbor_db_ids))
                        rows = cursor.fetchall()
                        cursor.close()
                        
                        cluster_counts = {}
                        for row in rows:
                            if row[0]:
                                try:
                                    c_ids = json.loads(row[0])
                                    if c_ids:
                                        cid = c_ids[0]
                                        cluster_counts[cid] = cluster_counts.get(cid, 0) + 1
                                except:
                                    pass
                        
                        # If we have candidates, pick the most frequent
                        if cluster_counts:
                            found_cluster_id = max(cluster_counts, key=cluster_counts.get)
                            logger.info(f"Article {article_id} matched to existing cluster {found_cluster_id} (neighbors: {len(valid_neighbor_db_ids)})")

                # 3. Assign Cluster
                if not found_cluster_id:
                    found_cluster_id = f"CL-{uuid.uuid4().hex[:8]}"
                    logger.info(f"Article {article_id} assigned to NEW cluster {found_cluster_id}")
                
                # Update DB
                self.db_service.ensure_conn()
                cursor = self.db_service.mb_conn.cursor()
                input_cluster_json = json.dumps([found_cluster_id])
                cursor.execute(
                    "UPDATE articles SET input_cluster_ids = %s WHERE id = %s",
                    (input_cluster_json, article_id)
                )
                self.db_service.mb_conn.commit()
                cursor.close()
                
            except Exception as e:
                logger.error(f"Error processing clustering for article {article_id}: {e}")



class ClusterToSynthesisPolicy(WorkflowPolicy):
    """
    Policy: Clustered -> Synthesized
    Condition: articles.is_synthesized = 0 
               AND articles.input_cluster_ids IS NOT NULL 
               AND articles.input_cluster_ids != '[]'
    Action: Group by cluster_id, call 'synthesizer.aggregate_cluster', save to 'synthesized_articles'.
    """

    def name(self) -> str:
        return "cluster_to_synthesis"


    def check_condition(self, limit: int) -> List[str]:
        # Returns list of Cluster IDs to process
        cluster_ids = []
        try:
            self.db_service.ensure_conn()
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            
            # Fetch candidates: un-synthesized articles with clusters
            # We fetch a larger batch to find a complete cluster
            # New Rule: Only pick clusters with at least 2 articles (to avoid premature singletons)
            # Maturity Rule: Fetch created_at to ensure cluster is stable (no new arrivals in last 20 mins)
            # INCREASED LIMIT: To 2000 to ensure we look past the "Singleton Jam" (backlog of ~1000 items)
            query = """
                SELECT input_cluster_ids, created_at FROM articles 
                WHERE is_synthesized = 0 
                  AND input_cluster_ids IS NOT NULL 
                  AND input_cluster_ids != '[]'
                  AND input_cluster_ids != ''
                ORDER BY created_at ASC
                LIMIT 2000
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()
            
            # Tally counts per cluster and track latest timestamp
            counts = {}
            latest_activity = {}
            
            for row in rows:
                try:
                    c_ids = json.loads(row[0])
                    created_at = row[1]
                    
                    if isinstance(c_ids, list) and c_ids:
                        cid = c_ids[0] # Assume primary cluster
                        counts[cid] = counts.get(cid, 0) + 1
                        
                        if created_at:
                            current_max = latest_activity.get(cid)
                            if not current_max or created_at > current_max:
                                latest_activity[cid] = created_at
                except:
                    continue
            
            # Filter: 
            # 1. Count >= 2
            # 2. Maturity: Last article > 20 mins ago
            # 3. Stale Snapshot: Count == 1 AND Age > 18 hours -> Synthesize as Brief
            valid_counts = {}
            now = datetime.now()
            # Use 20 minutes maturity window for active clusters
            maturity_window = timedelta(minutes=20)
            # Use 18 hours for stale singletons (Briefs)
            stale_window = timedelta(hours=18)
            
            for cid, count in counts.items():
                last_ts = latest_activity.get(cid)
                if last_ts:
                    age = now - last_ts
                    
                    if count >= 2:
                         # Active Cluster Maturity Rule
                         if age > maturity_window:
                             valid_counts[cid] = count
                    elif count == 1:
                         # Stale Brief Rule
                         if age > stale_window:
                             valid_counts[cid] = count
            
            # Pick the largest clusters first
            sorted_clusters = sorted(valid_counts.items(), key=lambda x: x[1], reverse=True)
            cluster_ids = [c[0] for c in sorted_clusters[:limit]]
            
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return cluster_ids

    async def execute(self, cluster_ids: List[str]):
        """
        Execute synthesis for the given cluster IDs.
        Note: The 'items' arg here is a list of cluster_ids, not article_ids.
        """
        logger.info(f"Synthesis policy triggered for {len(cluster_ids)} clusters.")
        
        for cid in cluster_ids:
            try:
                # 1. Fetch articles for this cluster
                self.db_service.ensure_conn()
                cursor = self.db_service.mb_conn.cursor()
                
                # We need to find articles where JSON contains this CID.
                # LIKE is a cheap approximation for logic: ["CL-ABC"] contains CL-ABC
                query = """
                    SELECT id, content FROM articles 
                    WHERE is_synthesized = 0 
                      AND input_cluster_ids LIKE %s
                """
                like_pattern = f"%{cid}%"
                cursor.execute(query, (like_pattern,))
                rows = cursor.fetchall()
                
                if not rows:
                    cursor.close()
                    continue
                    
                article_ids = [row[0] for row in rows]
                texts = [row[1] for row in rows if row[1]]
                cursor.close()
                
                if not texts:
                    continue

                logger.info(f"Synthesizing cluster {cid} with {len(texts)} articles.")
                
                # Check for previous synthesis history (Context Continuity)
                previous_context = None
                try:
                    cursor = self.db_service.mb_conn.cursor()
                    # Get the most recent synthesized version of this cluster
                    hist_query = """
                        SELECT body, created_at FROM synthesized_articles 
                        WHERE cluster_id = %s 
                        ORDER BY created_at DESC LIMIT 1
                    """
                    cursor.execute(hist_query, (cid,))
                    hist_row = cursor.fetchone()
                    
                    if hist_row:
                        prev_body = hist_row[0]
                        prev_date = hist_row[1]
                        
                        # Logic: Only use context if it's somewhat recent (e.g. < 7 days)
                        # otherwise treat as a fresh angle on an old topic.
                        if prev_body:
                             days_diff = (datetime.now() - prev_date).days if prev_date else 0
                             if days_diff < 7:
                                 previous_context = prev_body
                                 logger.info(f"Using previous context from {prev_date} for cluster {cid}")
                    cursor.close()
                except Exception as e:
                    logger.warning(f"Failed to fetch history for {cid}: {e}")

                # 2. Call Synthesizer
                # Using aggregate_cluster_tool
                synthesis_result = await self._call_mcp_tool(
                    agent="synthesizer",
                    tool="aggregate_cluster",
                    kwargs={
                        "article_texts": texts,
                        "type": "brief" if len(texts) == 1 else "full",
                        "previous_context": previous_context
                    }
                )
                
                if isinstance(synthesis_result, dict) and synthesis_result.get("success"):
                    body_text = synthesis_result.get("summary", "")
                    # Mark if it is a brief in the title (optional, can also be a column if schema supports)
                    is_brief = (len(texts) == 1)
                    title_prefix = "[Brief] " if is_brief else ""
                    title_text = f"{title_prefix}Synthesis Report: {cid}" 
                    
                    # 3. Upsert canonical living story per cluster
                    self.db_service.ensure_conn()
                    cursor = self.db_service.mb_conn.cursor()
                    upsert_result = upsert_living_story_record(
                        db_service=self.db_service,
                        cluster_id=cid,
                        article_ids=article_ids,
                        title_text=title_text,
                        body_text=body_text,
                    )

                    # 4. Mark articles as synthesized (always, even when update is not meaningful)
                    format_strings = ','.join(['%s'] * len(article_ids))
                    update_query = f"UPDATE articles SET is_synthesized = 1 WHERE id IN ({format_strings})"
                    cursor.execute(update_query, tuple(article_ids))
                    
                    self.db_service.mb_conn.commit()
                    cursor.close()

                    if upsert_result.get("action") == "tracked_noop":
                        logger.info(
                            f"ℹ️ Cluster {cid} produced no meaningful story delta "
                            f"(text_delta={upsert_result.get('text_delta')}, new_articles={upsert_result.get('new_article_count')}). "
                            f"Tracked inputs without republish for story {upsert_result.get('story_id')}."
                        )
                    else:
                        logger.info(
                            f"✅ Upserted living story {upsert_result.get('story_id')} from cluster {cid} "
                            f"(action={upsert_result.get('action')}, text_delta={upsert_result.get('text_delta')}, "
                            f"new_articles={upsert_result.get('new_article_count')})."
                        )
                else:
                    err = synthesis_result.get('error') if isinstance(synthesis_result, dict) else str(synthesis_result)
                    logger.error(f"Synthesis failed for cluster {cid}: {err}")
                    
                    # Log timeouts to a separate file for later processing
                    if "timed out" in str(err).lower() or "timeout" in str(err).lower():
                        try:
                            failed_log_path = "heavy_clusters.log"
                            entry = {
                                "cluster_id": cid,
                                "article_count": len(texts),
                                "error": str(err),
                                "timestamp": datetime.now().isoformat()
                            }
                            # Append metadata to a JSONL file
                            with open(failed_log_path, "a") as f:
                                f.write(json.dumps(entry) + "\n")
                            logger.info(f"💾 Logged heavy cluster {cid} to {failed_log_path}")
                        except Exception as log_err:
                            logger.error(f"Failed to log heavy cluster: {log_err}")
                    
            except Exception as e:
                logger.error(f"Error processing cluster {cid}: {e}")

class HeavyClusterRetryPolicy(WorkflowPolicy):
    """
    Policy: Retry Heavy Clusters
    Condition: 
      1. System load is light (load avg < 6.0)
      2. No significant active backlog in JustNews queues
      3. heavy_clusters.log has entries
    Action: Retry synthesis for one cluster at a time.
    """
    def name(self) -> str:
        return "heavy_cluster_retry"

    def check_condition(self, limit: int) -> List[str]:
        # 1. Check System Load
        try:
            # 1 minute load average. 16 cores. 
            # If load > 6.0, consider it busy.
            load = os.getloadavg()
            if load[0] > 6.0: 
                return []
        except:
            return []

        # 2. Check JustNews Backlog
        try:
            self.db_service.ensure_conn()
            # Check for unanalyzed articles or pending regular clusters
            cursor = self.db_service.mb_conn.cursor()
            query = """
                SELECT 
                    (SELECT COUNT(*) FROM articles WHERE analyzed = 0) +
                    (SELECT COUNT(*) FROM articles WHERE is_synthesized = 0 AND input_cluster_ids IS NOT NULL AND input_cluster_ids != '[]' AND input_cluster_ids != '')
                as backlog
            """
            cursor.execute(query)
            row = cursor.fetchone()
            cursor.close()
            backlog = row[0] if row else 0
            
            # If there are more than 10 regular items pending, defer heavy processing
            if backlog > 10: 
                return []
        except Exception as e:
            logger.error(f"Error checking backlog for HeavyClusterRetryPolicy: {e}")
            return []
            
        # 3. Check for Heavy Clusters
        failed_log_path = "heavy_clusters.log"
        if not os.path.exists(failed_log_path):
            return []

        cluster_id_to_retry = None
        
        try:
            with open(failed_log_path, "r") as f:
                lines = f.readlines()
            
            # Check the first valid entry
            for line in lines:
                if line.strip():
                    try:
                        rec = json.loads(line)
                        cid = rec.get("cluster_id")
                        if cid:
                            # Verify if it is still unsynthesized
                            self.db_service.ensure_conn()
                            cursor = self.db_service.mb_conn.cursor()
                            cursor.execute("SELECT id FROM synthesized_articles WHERE cluster_id = %s", (cid,))
                            exists = cursor.fetchone()
                            cursor.close()
                            
                            if not exists:
                                cluster_id_to_retry = cid
                                break
                            else:
                                # It's already done, we should clean it up later, but for now just skip returning it
                                pass
                    except:
                        pass
        except Exception as e:
            logger.error(f"Error reading heavy_clusters.log: {e}")
            return []

        if cluster_id_to_retry:
            return [cluster_id_to_retry]
            
        return []

    async def execute(self, cluster_ids: List[str]):
        """
        Execute synthesis for the given heavy cluster IDs.
        """
        logger.info(f"🏋️ HeavyClusterRetryPolicy triggered for {len(cluster_ids)} clusters.")
        
        for cid in cluster_ids:
            try:
                # 1. Fetch articles for this cluster
                self.db_service.ensure_conn()
                cursor = self.db_service.mb_conn.cursor()
                
                query = """
                    SELECT id, content FROM articles 
                    WHERE is_synthesized = 0 
                      AND input_cluster_ids LIKE %s
                """
                like_pattern = f"%{cid}%"
                cursor.execute(query, (like_pattern,))
                rows = cursor.fetchall()
                
                if not rows:
                    cursor.close()
                    continue
                    
                article_ids = [row[0] for row in rows]
                texts = [row[1] for row in rows if row[1]]
                cursor.close()
                
                if not texts:
                    continue

                logger.info(f"Retry synthesizing heavy cluster {cid} with {len(texts)} articles.")
                
                # 2. Call Synthesizer
                # Using aggregate_cluster_tool
                synthesis_result = await self._call_mcp_tool(
                    agent="synthesizer",
                    tool="aggregate_cluster",
                    kwargs={"article_texts": texts}
                )
                
                if isinstance(synthesis_result, dict) and synthesis_result.get("success"):
                    body_text = synthesis_result.get("summary", "")
                    title_text = f"Synthesis Report: {cid}" 
                    
                    # 3. Upsert canonical living story per cluster
                    self.db_service.ensure_conn()
                    cursor = self.db_service.mb_conn.cursor()
                    upsert_result = upsert_living_story_record(
                        db_service=self.db_service,
                        cluster_id=cid,
                        article_ids=article_ids,
                        title_text=title_text,
                        body_text=body_text,
                    )

                    # 4. Mark articles as synthesized (always, even when update is not meaningful)
                    format_strings = ','.join(['%s'] * len(article_ids))
                    update_query = f"UPDATE articles SET is_synthesized = 1 WHERE id IN ({format_strings})"
                    cursor.execute(update_query, tuple(article_ids))
                    
                    self.db_service.mb_conn.commit()
                    cursor.close()

                    if upsert_result.get("action") == "tracked_noop":
                        logger.info(
                            f"ℹ️ Heavy cluster {cid} produced no meaningful story delta "
                            f"(text_delta={upsert_result.get('text_delta')}, new_articles={upsert_result.get('new_article_count')}). "
                            f"Tracked inputs without republish for story {upsert_result.get('story_id')}."
                        )
                    else:
                        logger.info(
                            f"✅ Successfully upserted living story {upsert_result.get('story_id')} from heavy cluster {cid} "
                            f"(action={upsert_result.get('action')}, text_delta={upsert_result.get('text_delta')}, "
                            f"new_articles={upsert_result.get('new_article_count')})."
                        )
                    
                    # 5. Remove from heavy_clusters.log
                    self._remove_from_log(cid)
                    
                else:
                    err = synthesis_result.get('error') if isinstance(synthesis_result, dict) else str(synthesis_result)
                    logger.error(f"Retry failed for heavy cluster {cid}: {err}")
                    # Do not remove from log, so it can be retried again later (maybe infinite loop if keeps failing? user can check log)
                    
            except Exception as e:
                logger.error(f"Error processing heavy cluster {cid}: {e}")

    def _remove_from_log(self, cid_to_remove: str):
        try:
            failed_log_path = "heavy_clusters.log"
            if not os.path.exists(failed_log_path):
                return
                
            with open(failed_log_path, "r") as f:
                lines = f.readlines()
            
            new_lines = []
            for line in lines:
                try:
                    rec = json.loads(line)
                    if rec.get("cluster_id") != cid_to_remove:
                        new_lines.append(line)
                except:
                    new_lines.append(line)
            
            with open(failed_log_path, "w") as f:
                f.writelines(new_lines)
                
            logger.info(f"Removed {cid_to_remove} from {failed_log_path}")
        except Exception as e:
            logger.error(f"Failed to update heavy_clusters.log: {e}")





class SynthesisToCritiquePolicy(WorkflowPolicy):
    """
    Policy: Synthesized -> Critiqued
    Condition: synthesized_articles.critique_status IS NULL OR 'pending'
               AND is_published = 0
    Action: Call 'critic.critique_synthesis'
    """
    def name(self) -> str:
        return "synthesis_to_critique"

    def check_condition(self, limit: int) -> List[str]:
        ids = []
        try:
            self.db_service.ensure_conn()
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            query = """
                SELECT story_id FROM synthesized_articles 
                WHERE is_published = 0 
                  AND (critique_status IS NULL OR critique_status = 'pending')
                ORDER BY created_at ASC
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[str]):
        logger.info(f"Triggering critique for {len(items)} stories.")
        
        for story_id in items:
            try:
                # Fetch story body
                self.db_service.ensure_conn()
                cursor = self.db_service.mb_conn.cursor()
                cursor.execute("SELECT body, title FROM synthesized_articles WHERE story_id = %s", (story_id,))
                row = cursor.fetchone()
                cursor.close()
                
                if not row:
                    continue
                    
                body = row[0]
                title = row[1]
                content_to_critique = f"Title: {title}\n\n{body}"
                
                # Call Critic
                result = await self._call_mcp_tool(
                    agent="critic",
                    tool="critique_synthesis",
                    kwargs={"content": content_to_critique}
                )
                
                if isinstance(result, dict):
                    # Save critique
                    critique_text = json.dumps(result)
                    self.db_service.ensure_conn()
                    cursor = self.db_service.mb_conn.cursor()
                    cursor.execute(
                        """UPDATE synthesized_articles 
                           SET critique_status = 'completed', critique_text = %s 
                           WHERE story_id = %s""",
                        (critique_text, story_id)
                    )
                    self.db_service.mb_conn.commit()
                    cursor.close()
                    logger.info(f"✅ Critiqued story {story_id}")
                else:
                    logger.error(f"Critique failed for {story_id}: {result}")
            except Exception as e:
                logger.error(f"Error critiquing story {story_id}: {e}")


class SynthesisToPublishingPolicy(WorkflowPolicy):
    """
    Policy: Synthesized & Critiqued -> Published
    Condition: synthesized_articles.is_published = 0 AND critique_status = 'completed'
    Action: Call 'chief_editor.publish_story'
    """

    def name(self) -> str:
        return "synthesis_to_publishing"

    def check_condition(self, limit: int) -> List[str]:
        ids = []
        try:
            self.db_service.ensure_conn()
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            
            # Select unpublished stories that have been critiqued
            query = """
                SELECT story_id FROM synthesized_articles 
                WHERE is_published = 0 
                  AND critique_status = 'completed'
                ORDER BY created_at ASC
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[str]):
        logger.info(f"Triggering publishing for {len(items)} stories.")
        
        for story_id in items:
            try:
                logger.info(f"Publishing story {story_id}...")
                
                # 1. Call Chief Editor
                result = await self._call_mcp_tool(
                    agent="chief_editor",
                    tool="publish_story",
                    kwargs={"story_id": story_id}
                )
                
                # Unpack EditorialResponse if present
                if isinstance(result, dict) and "result" in result and "status" not in result:
                    result = result["result"]

                # 2. Update DB on Success
                # We accept 'published' or 'published_locally'
                if isinstance(result, dict) and "published" in result.get("status", ""):
                    logger.info(f"✅ Published story {story_id}")
                else:
                    err = result.get('error') if isinstance(result, dict) else str(result)
                    logger.error(f"Publishing failed for {story_id}: {err}")
                    
            except Exception as e:
                logger.error(f"Error publishing story {story_id}: {e}")
