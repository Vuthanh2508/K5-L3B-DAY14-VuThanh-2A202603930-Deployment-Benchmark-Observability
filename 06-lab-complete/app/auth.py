"""
API Key authentication (tiêu chí 6).

Kiểm tra header X-API-Key khớp với biến môi trường AGENT_API_KEY;
thiếu hoặc sai key trả về HTTP 401.
"""
import secrets

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Dependency cho FastAPI — bắt buộc header X-API-Key hợp lệ."""
    expected = settings.agent_api_key
    if not expected or not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <your-key>",
        )
    return api_key
