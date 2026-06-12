"""REST routes. P0: chỉ /api/health. Các route P1+ thêm dần (xem SRS §5)."""

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict:
    """Liveness probe — dùng cho compose healthcheck + smoke test frontend."""
    return {"status": "ok"}
