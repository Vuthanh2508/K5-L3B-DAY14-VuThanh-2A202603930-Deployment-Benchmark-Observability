"""
Production AI Agent — Part 6 Final Project.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import signal
import sys
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Format mọi log record thành đúng 1 JSON object hợp lệ trên 1 dòng."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
        }
        msg = record.getMessage()
        try:
            parsed = json.loads(msg)
            if isinstance(parsed, dict):
                payload.update(parsed)
            else:
                payload["msg"] = msg
        except ValueError:
            payload["msg"] = msg
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level, logging.INFO))
    return logging.getLogger("agent")


logger = _configure_logging()
START_TIME = time.time()
DEMO_HTML_PATH = Path(__file__).resolve().parent.parent / "static" / "index.html"
_is_ready = False
_in_flight = 0


_previous_sigterm = signal.getsignal(signal.SIGTERM)


def _handle_sigterm(signum, frame):
    """Ghi log nhận SIGTERM rồi chuyển tiếp về handler của uvicorn để shutdown êm."""
    global _is_ready
    _is_ready = False
    logger.info(json.dumps({"event": "sigterm_received", "in_flight": _in_flight}))
    if callable(_previous_sigterm):
        _previous_sigterm(signum, frame)


signal.signal(signal.SIGTERM, _handle_sigterm)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý vòng đời startup và graceful shutdown."""
    global _is_ready
    _is_ready = True
    logger.info(
        json.dumps(
            {
                "event": "startup",
                "environment": settings.environment,
                "port": settings.port,
            }
        )
    )
    yield
    _is_ready = False
    deadline = time.time() + 8.0
    while _in_flight > 0 and time.time() < deadline:
        await asyncio.sleep(0.05)
    logger.info(json.dumps({"event": "shutdown_complete", "in_flight": _in_flight}))


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def track_and_log_requests(request: Request, call_next):
    """Đếm in-flight request và ghi access log dạng JSON."""
    global _in_flight
    _in_flight += 1
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        _in_flight -= 1
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            json.dumps(
                {
                    "event": "request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "ms": elapsed_ms,
                }
            )
        )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Không để lộ stack trace ra response client."""
    logger.error(
        json.dumps(
            {
                "event": "unhandled_error",
                "path": request.url.path,
                "error_type": type(exc).__name__,
            }
        )
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


def _demo_client_key(request: Request) -> str:
    """Lấy key rate-limit theo IP cho endpoint public demo (không dùng AGENT_API_KEY)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else ""
    if not client_ip and request.client:
        client_ip = request.client.host
    return f"demo:{client_ip or 'anonymous'}"


def _run_agent(question: str, rate_limit_key: str) -> dict:
    """Pipeline chung: Rate Limit (Redis) -> Cost Guard (Redis) -> LLM -> ghi cost."""
    check_rate_limit(rate_limit_key)
    check_budget()

    answer = llm_ask(question)
    input_tokens = max(1, len(question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    cost_usd = record_cost(input_tokens, output_tokens)

    return {
        "question": question,
        "answer": answer,
        "cost_usd": round(cost_usd, 6),
    }


@app.get("/", include_in_schema=False)
def demo_page():
    """Trang Web Demo gọn nhẹ để người dùng thử agent trực tiếp trên trình duyệt."""
    if not DEMO_HTML_PATH.is_file():
        raise HTTPException(status_code=404, detail="Demo UI not found")
    return FileResponse(DEMO_HTML_PATH)


@app.get("/health")
def health():
    """Liveness probe — luôn trả 200 khi process còn sống, không phụ thuộc Redis."""
    return {
        "status": "ok",
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
    }


@app.get("/ready")
def ready():
    """Readiness probe — 200 khi sẵn sàng, 503 khi shutdown hoặc mất Redis."""
    if not _is_ready or not redis_healthy():
        raise HTTPException(status_code=503, detail="Service not ready")
    return {"ready": True, "redis": "ok"}


@app.post("/demo/ask")
def demo_ask(body: AskRequest, request: Request):
    """Endpoint cho trang Web Demo công khai: rate limit theo IP + Cost Guard, không lộ AGENT_API_KEY."""
    result = _run_agent(body.question, _demo_client_key(request))
    return {**result, "mode": "public-demo"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    """Endpoint chính: API Key -> Rate Limit (Redis) -> Cost Guard (Redis) -> LLM."""
    return _run_agent(body.question, api_key)
