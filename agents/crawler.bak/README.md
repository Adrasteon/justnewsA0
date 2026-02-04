Crawler agent notes ===================

Security --------

- `CRAWLER_API_TOKEN`: when set, the crawler endpoints (e.g.,`/unified_production_crawl`,`/job_status`) require a bearer
  token or`X-Api-Token` header. If unset, endpoints are open for compatibility.

Persistent job store ---------------------

- The crawler persists job status to a MariaDB `crawler_jobs` table when available and falls back to in-memory storage
  when the database is unreachable.

- The jobs table is created during `scripts/init_database.py`initialization. Startup recovers`running`jobs and marks
  them as`failed`with a restoration note to avoid orphaned`running` states on restarts.

Process cleanup & safety ------------------------

- The crawler uses `psutil` to identify and clean up only process descendants it started (e.g., Chrome/Playwright
  drivers). This avoids killing unrelated processes.

Robots.txt ----------

- A `RobotsChecker`with TTL caching is used to fetch and respect robots.txt for each domain; the TTL is configurable
  with`CRAWLER_ROBOTS_TTL` (defaults to 86400 seconds).

Testing -------

- Unit tests cover token auth, job store behaviour, robots checker, and process cleanup.
