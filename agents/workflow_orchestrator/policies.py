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
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

logger = get_logger(__name__)

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


class FactCheckToClusterPolicy(WorkflowPolicy):
    """
    Policy: Fact Checked -> Clustered
    Condition: articles.fact_check_status IS NOT NULL 
               AND (articles.input_cluster_ids IS NULL OR articles.input_cluster_ids = '[]')
               AND article.created_at >= NOW() - CLUSTER_DATERANGE
    Action: Call 'synthesizer.cluster_articles', generate Cluster IDs, and update articles.
    """

    def name(self) -> str:
        return "fact_check_to_cluster"

    def check_condition(self, limit: int) -> List[int]:
        ids = []
        try:
            days_val = os.environ.get("CLUSTER_DATERANGE", 7)
            try:
                days_range = int(days_val)
            except ValueError:
                days_range = 7
            cutoff_date = datetime.now() - timedelta(days=days_range)
            
            self.db_service.ensure_conn()
            try:
                self.db_service.mb_conn.commit()
            except:
                pass
            cursor = self.db_service.mb_conn.cursor()
            
            # We explicitly ignore the small default 'limit' (usually 5) 
            # and fetch a larger batch for meaningful clustering.
            query = """
                SELECT id FROM articles 
                WHERE fact_check_status IS NOT NULL 
                  AND (input_cluster_ids IS NULL OR input_cluster_ids = '[]' OR input_cluster_ids = '')
                  AND created_at >= %s
                ORDER BY created_at DESC
                LIMIT 50
            """
            cursor.execute(query, (cutoff_date,))
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
            
        logger.info(f"Clustering policy triggered for {len(items)} articles.")
        
        # 1. Fetch content
        articles_data = [] # List of dict {id, content}
        try:
            self.db_service.ensure_conn()
            cursor = self.db_service.mb_conn.cursor()
            # Construct "IN" query safely
            format_strings = ','.join(['%s'] * len(items))
            cursor.execute(f"SELECT id, content FROM articles WHERE id IN ({format_strings})", tuple(items))
            rows = cursor.fetchall()
            for row in rows:
                if row[1]: # Has content
                    articles_data.append({"id": row[0], "content": row[1]})
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to fetch content for clustering: {e}")
            return
            
        if not articles_data:
            return

        texts = [a["content"] for a in articles_data]
        
        # 2. Call Clustering Agent
        # Dynamic cluster count: at least 2, roughly 1 cluster per 5 articles
        n_clusters = max(2, len(items) // 5)
        
        try:
            # Call 'cluster_articles' tool
            clustering_result = await self._call_mcp_tool(
                agent="synthesizer",
                tool="cluster_articles",
                kwargs={"article_texts": texts, "n_clusters": n_clusters}
            )
            
            # Check for success (support both boolean 'success' and string 'status'="success")
            is_success = False
            if isinstance(clustering_result, dict):
                if clustering_result.get("success"):
                    is_success = True
                elif clustering_result.get("status") == "success":
                    is_success = True

            if is_success:
                clusters = clustering_result.get("clusters", [])
                # clusters is list of lists of indices
                
                # 3. Update DB with Cluster IDs
                self.db_service.ensure_conn()
                cursor = self.db_service.mb_conn.cursor()
                
                updates = 0
                for cluster_indices in clusters:
                    if not cluster_indices:
                        continue
                        
                    cluster_id = f"CL-{uuid.uuid4().hex[:8]}"
                    # Store as JSON list
                    input_cluster_json = json.dumps([cluster_id])
                    
                    cluster_article_ids = []
                    for idx in cluster_indices:
                        # Ensure index is int and within bounds
                        try:
                            idx_int = int(idx)
                            if 0 <= idx_int < len(articles_data):
                                cluster_article_ids.append(articles_data[idx_int]["id"])
                        except (ValueError, TypeError):
                            continue
                    
                    if not cluster_article_ids:
                        continue
                        
                    for aid in cluster_article_ids:
                        cursor.execute(
                            "UPDATE articles SET input_cluster_ids = %s WHERE id = %s",
                            (input_cluster_json, aid)
                        )
                    updates += len(cluster_article_ids)
                
                self.db_service.mb_conn.commit()
                cursor.close()
                logger.info(f"Clustering complete. Assigned {updates} articles to {len(clusters)} clusters.")
                
            else:
                error_msg = clustering_result.get('error') if isinstance(clustering_result, dict) else str(clustering_result)
                logger.error(f"Clustering failed: {error_msg}")
                
        except Exception as e:
             logger.error(f"Error executing clustering policy: {e}")


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
            # We fetch a reasonable batch to find a complete cluster
            query = """
                SELECT input_cluster_ids FROM articles 
                WHERE is_synthesized = 0 
                  AND input_cluster_ids IS NOT NULL 
                  AND input_cluster_ids != '[]'
                  AND input_cluster_ids != ''
                LIMIT 200
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()
            
            # Tally counts per cluster
            counts = {}
            for row in rows:
                try:
                    c_ids = json.loads(row[0])
                    if isinstance(c_ids, list) and c_ids:
                        cid = c_ids[0] # Assume primary cluster
                        counts[cid] = counts.get(cid, 0) + 1
                except:
                    continue
            
            # Pick the largest clusters first, or just any valid ones
            # We return a list of cluster IDs up to 'limit'
            sorted_clusters = sorted(counts.items(), key=lambda x: x[1], reverse=True)
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
                
                # 2. Call Synthesizer
                # Using aggregate_cluster_tool
                synthesis_result = await self._call_mcp_tool(
                    agent="synthesizer",
                    tool="aggregate_cluster",
                    kwargs={"article_texts": texts}
                )
                
                if isinstance(synthesis_result, dict) and synthesis_result.get("success"):
                    body_text = synthesis_result.get("summary", "")
                    title_text = f"Synthesis Report: {cid}" # Placeholder title
                    
                    # 3. Save to synthesized_articles
                    self.db_service.ensure_conn()
                    cursor = self.db_service.mb_conn.cursor()
                    
                    # Columns: id, story_id, cluster_id, input_articles, title, body, created_at, is_published
                    new_id = int(time.time() * 1000) # Simple numeric ID gen or use auto-increment if schema allows
                    story_id = f"STORY-{uuid.uuid4().hex[:8]}"
                    input_arts_json = json.dumps(article_ids)
                    
                    insert_query = """
                        INSERT INTO synthesized_articles 
                        (story_id, cluster_id, input_articles, title, body, created_at, is_published)
                        VALUES (%s, %s, %s, %s, %s, NOW(), 0)
                    """
                    cursor.execute(insert_query, (story_id, cid, input_arts_json, title_text, body_text))
                    
                    # 4. Mark articles as synthesized
                    format_strings = ','.join(['%s'] * len(article_ids))
                    update_query = f"UPDATE articles SET is_synthesized = 1 WHERE id IN ({format_strings})"
                    cursor.execute(update_query, tuple(article_ids))
                    
                    self.db_service.mb_conn.commit()
                    cursor.close()
                    
                    logger.info(f"✅ Created story {story_id} from cluster {cid}.")
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
                    
                    # 3. Save to synthesized_articles
                    self.db_service.ensure_conn()
                    cursor = self.db_service.mb_conn.cursor()
                    
                    new_id = int(time.time() * 1000)
                    story_id = f"STORY-{uuid.uuid4().hex[:8]}"
                    input_arts_json = json.dumps(article_ids)
                    
                    insert_query = """
                        INSERT INTO synthesized_articles 
                        (story_id, cluster_id, input_articles, title, body, created_at, is_published)
                        VALUES (%s, %s, %s, %s, %s, NOW(), 0)
                    """
                    cursor.execute(insert_query, (story_id, cid, input_arts_json, title_text, body_text))
                    
                    # 4. Mark articles as synthesized
                    format_strings = ','.join(['%s'] * len(article_ids))
                    update_query = f"UPDATE articles SET is_synthesized = 1 WHERE id IN ({format_strings})"
                    cursor.execute(update_query, tuple(article_ids))
                    
                    self.db_service.mb_conn.commit()
                    cursor.close()
                    
                    logger.info(f"✅ Successfully created story {story_id} from heavy cluster {cid}.")
                    
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




