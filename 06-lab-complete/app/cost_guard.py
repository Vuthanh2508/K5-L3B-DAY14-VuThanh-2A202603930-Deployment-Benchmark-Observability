"""
Cost guard (tiêu chí 8) — Theo dõi và chặn chi phí LLM trong Redis.

Vượt DAILY_BUDGET_USD hoặc MONTHLY_BUDGET_USD trả về HTTP 402.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import get_redis

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

DAILY_TTL_SECONDS = 48 * 3600
MONTHLY_TTL_SECONDS = 32 * 24 * 3600


def _budget_keys() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return (
        f"cost:daily:{now.strftime('%Y-%m-%d')}",
        f"cost:monthly:{now.strftime('%Y-%m')}",
    )


def check_budget() -> None:
    """Kiểm tra ngân sách trước khi gọi LLM. Hết budget → raise HTTP 402."""
    client = get_redis()
    if client is None:
        raise HTTPException(status_code=503, detail="Cost guard storage not configured")

    daily_key, monthly_key = _budget_keys()
    try:
        raw_daily, raw_monthly = client.mget(daily_key, monthly_key)
        daily_spent = float(raw_daily or 0.0)
        monthly_spent = float(raw_monthly or 0.0)
    except RedisError:
        raise HTTPException(status_code=503, detail="Cost guard storage unavailable")

    if daily_spent >= settings.daily_budget_usd or monthly_spent >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Cộng chi phí request vào Redis và trả về chi phí request (USD)."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    client = get_redis()
    if client is None:
        return cost

    daily_key, monthly_key = _budget_keys()
    try:
        pipe = client.pipeline()
        pipe.incrbyfloat(daily_key, cost)
        pipe.expire(daily_key, DAILY_TTL_SECONDS)
        pipe.incrbyfloat(monthly_key, cost)
        pipe.expire(monthly_key, MONTHLY_TTL_SECONDS)
        pipe.execute()
    except RedisError:
        raise HTTPException(status_code=503, detail="Cost guard storage unavailable")
    return cost
