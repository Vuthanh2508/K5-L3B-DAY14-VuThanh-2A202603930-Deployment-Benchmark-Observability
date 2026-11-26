"""
Kết nối Redis dùng chung cho rate limiter, cost guard và readiness check.

Không ping Redis lúc import để app vẫn khởi động được khi Redis chưa sẵn sàng.
"""
import redis
from redis.exceptions import RedisError

from app.config import settings

r: redis.Redis | None = (
    redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )
    if settings.redis_url
    else None
)


def get_redis() -> redis.Redis | None:
    """Trả về Redis client dùng chung (hoặc None nếu chưa cấu hình REDIS_URL)."""
    return r


def redis_healthy() -> bool:
    """Ping Redis phục vụ GET /ready; trả False nếu không kết nối được."""
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except RedisError:
        return False
