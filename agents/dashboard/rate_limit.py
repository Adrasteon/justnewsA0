import os
import time

from fastapi import HTTPException, Request

try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None

_windows = {}
_redis_client: object | None = None


def allow_request(
    request: Request, max_requests: int = 10, window_seconds: int = 60
) -> bool:
    """Simple in-memory per-IP rate limiter. For production use, consider
    Redis-backed limiter to support multiple replicas.
    """
    try:
        client_ip = request.client.host if request.client else "unknown"
    except Exception:
        client_ip = "unknown"

    now = time.time()
    key = (client_ip,)
    bucket = _windows.get(key)
    if not bucket:
        _windows[key] = {"reset": now + window_seconds, "count": 1}
        return True

    if now > bucket["reset"]:
        _windows[key] = {"reset": now + window_seconds, "count": 1}
        return True

    if bucket["count"] >= max_requests:
        return False

    bucket["count"] += 1
    return True


def _get_redis_client():
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = os.environ.get("REDIS_URL")
    if not redis_url or redis is None:
        return None

    try:
        _redis_client = redis.from_url(redis_url, decode_responses=True)
    except Exception:
        _redis_client = None

    return _redis_client


def allow_request_redis(
    request: Request, max_requests: int = 10, window_seconds: int = 60
) -> bool:
    """Redis-backed rate limiter using fixed windows and INCR+EXPIRE.

    NOTE: This design provides eventual correctness for small windows. For
    strict atomicity across replicas use a Redis Lua script (not required for
    our initial implementation).
    """
    # Prefer the cached client when available; when tests monkeypatch
    # _get_redis_client to return a fresh fake instance on each call we want
    # to keep a stable client for the duration of the process.
    global _redis_client
    client = _redis_client if _redis_client is not None else _get_redis_client()
    if _redis_client is None and client is not None:
        _redis_client = client
    if client is None:
        return allow_request(
            request, max_requests=max_requests, window_seconds=window_seconds
        )

    try:
        client_ip = request.client.host if request.client else "unknown"
    except Exception:
        client_ip = "unknown"

    now = int(time.time())
    window_start = int(now // window_seconds) * window_seconds
    key = f"rl:{client_ip}:{window_start}"

    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds + 1)
        return int(count) <= int(max_requests)
    except Exception:
        # On failure gracefully fall back to in-memory limiter to avoid
        # blocking the public API when Redis is temporarily unavailable.
        return allow_request(
            request, max_requests=max_requests, window_seconds=window_seconds
        )


def rate_limiter_dependency(
    request: Request, max_requests: int = 10, window_seconds: int = 60
):
    # Prefer a Redis-backed store when configured — it ensures consistent
    # accounting across multiple replicas. Fall back to in-memory limiter
    # when Redis is not configured or unavailable.
    ok = allow_request_redis(
        request, max_requests=max_requests, window_seconds=window_seconds
    )
    if not ok:
        raise HTTPException(status_code=429, detail="Too many requests")
