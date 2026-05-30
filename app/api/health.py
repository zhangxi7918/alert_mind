from fastapi import APIRouter

from app.config import config

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": config.app_version,
    }
