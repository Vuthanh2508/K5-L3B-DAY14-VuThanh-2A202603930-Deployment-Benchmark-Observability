"""
Rate limiting (tiêu chí 7) — Sliding Window bằng Redis Sorted Set.

Lưu state trong Redis để chia sẻ giữa nhiều worker/instance và giữ nguyên sau restart.
"""
import time
import uuid

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import get_redis

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Giới hạn tối đa RATE_LIMIT_PER_MINUTE request / 60s cho mỗi API key."""
    client = get_redis()
    if client is None:
        raise HTTPException(status_code=503, detail="Rate limiter storage not configured")

    redis_key = f"rate_limit:{key}"
    now = time.time()
    window_start = now - WINDOW_SECONDS
    limit = settings.rate_limit_per_minute

    try:
        pipe = client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= limit:
            oldest = client.zrange(redis_key, 0, 0, withscores=True)
            retry_after = (
                max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
                if oldest
                else WINDOW_SECONDS
            )
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now}:{uuid.uuid4().hex}"
        pipe = client.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS + 5)
        pipe.execute()
    except RedisError:
        raise HTTPException(status_code=503, detail="Rate limiter storage unavailable")
