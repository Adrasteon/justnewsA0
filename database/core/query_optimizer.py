"""
Query Optimizer - Advanced Implementation
Intelligent query optimization with caching and performance monitoring

Features:
- Query Optimization: Automatic query analysis and optimization suggestions
- Query Caching: Intelligent caching with invalidation strategies
- Performance Monitoring: Query execution time tracking and analysis
- Index Recommendations: Automatic index creation suggestions
- Query Analysis: Detailed query execution plan analysis
"""

import hashlib
import time
from typing import Any

from common.observability import get_logger

from .connection_pool import DatabaseConnectionPool

logger = get_logger(__name__)


class QueryOptimizer:
    """
    Advanced query optimization with caching and performance monitoring
    """

    def __init__(self, connection_pool: DatabaseConnectionPool, cache_size: int = 1000):
        """
        Initialize the query optimizer

        Args:
            connection_pool: Database connection pool instance
            cache_size: Maximum number of cached query results
        """
        self.pool = connection_pool
        self.cache_size = cache_size
        self.query_cache: dict[str, dict[str, Any]] = {}
        self.query_stats: dict[str, dict[str, Any]] = {}

        # Performance metrics
        self.metrics = {
            "queries_executed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_execution_time": 0.0,
            "slow_queries": 0,
        }

    def execute_optimized_query(
        self,
        query: str,
        params: tuple = None,
        use_cache: bool = True,
        cache_ttl: int = 300,
    ) -> list[dict]:
        """
        Execute a query with optimization and caching

        Args:
            query: SQL query string
            params: Query parameters
            use_cache: Whether to use query caching
            cache_ttl: Cache time-to-live in seconds

        Returns:
            Query results
        """
        start_time = time.time()
        query_hash = self._get_query_hash(query, params)

        # Check cache first
        if use_cache and self._is_cache_valid(query_hash, cache_ttl):
            self.metrics["cache_hits"] += 1
            logger.debug(f"Cache hit for query: {query[:50]}...")
            return self.query_cache[query_hash]["result"]

        self.metrics["cache_misses"] += 1

        try:
            # Execute query
            results = self.pool.execute_query(query, params)

            # Cache results
            if use_cache:
                self._cache_result(query_hash, results, query, params)

            # Update statistics
            execution_time = time.time() - start_time
            self._update_query_stats(query_hash, query, execution_time)

            self.metrics["queries_executed"] += 1
            self.metrics["total_execution_time"] += execution_time

            if execution_time > 1.0:  # Slow query threshold
                self.metrics["slow_queries"] += 1
                logger.warning(
                    f"Slow query detected ({execution_time:.2f}s): {query[:100]}..."
                )

            return results

        except Exception as e:
            logger.error(f"Query execution failed: {query} - {e}")
            raise

    def analyze_query_performance(
        self, query: str, params: tuple = None
    ) -> dict[str, Any]:
        """
        Analyze query performance with execution plan

        Args:
            query: SQL query to analyze
            params: Query parameters

        Returns:
            Performance analysis results
        """
        analysis = {
            "query": query,
            "execution_plan": None,
            "estimated_cost": None,
            "actual_execution_time": None,
            "recommendations": [],
        }

        try:
            # Get execution plan
            explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"
            start_time = time.time()

            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(explain_query, params or ())
                plan_result = cursor.fetchone()
                execution_time = time.time() - start_time
                cursor.close()

            if plan_result:
                analysis["execution_plan"] = plan_result[0]
                analysis["actual_execution_time"] = execution_time

                # Extract cost information
                if isinstance(plan_result[0], list) and plan_result[0]:
                    plan_info = plan_result[0][0]
                    analysis["estimated_cost"] = plan_info.get("Total Cost")

                # Generate recommendations
                analysis["recommendations"] = self._generate_recommendations(
                    plan_result[0]
                )

        except Exception as e:
            logger.warning(f"Failed to analyze query performance: {e}")
            analysis["error"] = str(e)

        return analysis

    def get_index_recommendations(self) -> list[dict[str, Any]]:
        """
        Get index creation recommendations based on query patterns

        Returns:
            List of index recommendations
        """
        recommendations = []

        try:
            # Analyze slow queries and missing indexes
            slow_queries = [
                stats
                for stats in self.query_stats.values()
                if stats.get("avg_execution_time", 0) > 1.0
            ]

            for query_stats in slow_queries:
                query = query_stats["query"]

                # Simple heuristic: look for WHERE clauses without indexes
                if "WHERE" in query.upper():
                    # Get table name and column from WHERE clause
                    table_col = self._extract_table_column_from_where(query)
                    if table_col:
                        table, column = table_col
                        recommendations.append(
                            {
                                "type": "index",
                                "table": table,
                                "column": column,
                                "reason": f"Slow query on {table}.{column}",
                                "estimated_impact": "high",
                                "sql": f"CREATE INDEX idx_{table}_{column} ON {table} ({column});",
                            }
                        )

        except Exception as e:
            logger.warning(f"Failed to generate index recommendations: {e}")

        return recommendations

    def optimize_table(self, table_name: str) -> dict[str, Any]:
        """
        Optimize table performance with ANALYZE and potential reindexing

        Args:
            table_name: Name of table to optimize

        Returns:
            Optimization results
        """
        results = {
            "table": table_name,
            "success": False,
            "actions_taken": [],
            "errors": [],
        }

        try:
            # Run ANALYZE to update statistics
            analyze_query = f"ANALYZE {table_name}"
            self.pool.execute_query(analyze_query, fetch=False)
            results["actions_taken"].append("ANALYZE executed")

            # Check if table needs reindexing (simple heuristic)
            reindex_check = """
            SELECT schemaname, tablename, n_dead_tup, n_live_tup
            FROM pg_stat_user_tables
            WHERE tablename = %s
            """
            stats = self.pool.execute_query(reindex_check, (table_name,))

            if stats:
                dead_tuples = stats[0]["n_dead_tup"]
                live_tuples = stats[0]["n_live_tup"]

                if (
                    live_tuples > 0 and (dead_tuples / live_tuples) > 0.2
                ):  # 20% dead tuples
                    reindex_query = f"REINDEX TABLE {table_name}"
                    self.pool.execute_query(reindex_query, fetch=False)
                    results["actions_taken"].append("REINDEX executed")

            results["success"] = True

        except Exception as e:
            results["errors"].append(str(e))
            logger.error(f"Failed to optimize table {table_name}: {e}")

        return results

    def get_performance_metrics(self) -> dict[str, Any]:
        """
        Get comprehensive performance metrics

        Returns:
            Performance metrics dictionary
        """
        cache_hit_rate = 0.0
        total_cache_requests = self.metrics["cache_hits"] + self.metrics["cache_misses"]
        if total_cache_requests > 0:
            cache_hit_rate = (self.metrics["cache_hits"] / total_cache_requests) * 100

        avg_query_time = 0.0
        if self.metrics["queries_executed"] > 0:
            avg_query_time = (
                self.metrics["total_execution_time"] / self.metrics["queries_executed"]
            )

        return {
            **self.metrics,
            "cache_hit_rate": cache_hit_rate,
            "avg_query_time": avg_query_time,
            "cached_queries_count": len(self.query_cache),
            "tracked_queries_count": len(self.query_stats),
        }

    def clear_cache(self, pattern: str | None = None):
        """
        Clear query cache, optionally matching a pattern

        Args:
            pattern: Optional pattern to match for selective clearing
        """
        if pattern:
            keys_to_remove = [
                key
                for key in self.query_cache.keys()
                if pattern in self.query_cache[key].get("query", "")
            ]
            for key in keys_to_remove:
                del self.query_cache[key]
            logger.info(
                f"Cleared {len(keys_to_remove)} cached queries matching pattern: {pattern}"
            )
        else:
            cache_count = len(self.query_cache)
            self.query_cache.clear()
            logger.info(f"Cleared all {cache_count} cached queries")

    def _get_query_hash(self, query: str, params: tuple = None) -> str:
        """Generate hash for query + params combination"""
        content = f"{query}|{params or ()}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def _is_cache_valid(self, query_hash: str, ttl: int) -> bool:
        """Check if cached result is still valid"""
        if query_hash not in self.query_cache:
            return False

        cached_time = self.query_cache[query_hash]["timestamp"]
        return (time.time() - cached_time) < ttl

    def _cache_result(
        self, query_hash: str, result: list[dict], query: str, params: tuple
    ):
        """Cache query result"""
        self.query_cache[query_hash] = {
            "result": result,
            "timestamp": time.time(),
            "query": query,
            "params": params,
        }

        # Maintain cache size limit
        if len(self.query_cache) > self.cache_size:
            # Remove oldest entry
            oldest_key = min(
                self.query_cache.keys(), key=lambda k: self.query_cache[k]["timestamp"]
            )
            del self.query_cache[oldest_key]

    def _update_query_stats(self, query_hash: str, query: str, execution_time: float):
        """Update query execution statistics"""
        if query_hash not in self.query_stats:
            self.query_stats[query_hash] = {
                "query": query,
                "execution_count": 0,
                "total_execution_time": 0.0,
                "avg_execution_time": 0.0,
                "min_execution_time": float("inf"),
                "max_execution_time": 0.0,
                "last_executed": None,
            }

        stats = self.query_stats[query_hash]
        stats["execution_count"] += 1
        stats["total_execution_time"] += execution_time
        stats["avg_execution_time"] = (
            stats["total_execution_time"] / stats["execution_count"]
        )
        stats["min_execution_time"] = min(stats["min_execution_time"], execution_time)
        stats["max_execution_time"] = max(stats["max_execution_time"], execution_time)
        stats["last_executed"] = time.time()

    def _generate_recommendations(self, execution_plan: Any) -> list[str]:
        """Generate optimization recommendations from execution plan"""
        recommendations = []

        try:
            if isinstance(execution_plan, list) and execution_plan:
                plan = execution_plan[0]

                # Check for sequential scans on large tables
                if plan.get("Node Type") == "Seq Scan":
                    relation_name = plan.get("Relation Name")
                    if relation_name:
                        recommendations.append(
                            f"Consider adding indexes on frequently queried columns in table '{relation_name}'"
                        )

                # Check for high cost operations
                total_cost = plan.get("Total Cost", 0)
                if total_cost > 1000:  # Arbitrary threshold
                    recommendations.append(
                        f"High query cost ({total_cost:.0f}) detected - consider query optimization"
                    )

        except Exception as e:
            logger.warning(f"Failed to generate recommendations: {e}")

        return recommendations

    def _extract_table_column_from_where(self, query: str) -> tuple[str, str] | None:
        """Extract table and column from WHERE clause (simple heuristic)"""
        try:
            # Very basic parsing - look for patterns like "table.column = value"
            where_part = (
                query.upper().split("WHERE")[1] if "WHERE" in query.upper() else ""
            )

            # Look for table.column pattern
            if "." in where_part:
                parts = where_part.split(".")[0].strip().split()
                if len(parts) >= 2:
                    table = parts[-2]  # table name before column
                    column = parts[-1]  # column name
                    return table, column

        except Exception:
            pass

        return None
