import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.models.request import AiopsRequest
from app.services.aiops_service import aiops_service

router = APIRouter()


def _json_event(message: dict[str, Any]) -> str:
    return json.dumps(message, ensure_ascii=False)


def _stream_aiops(input_text: str) -> EventSourceResponse:
    async def generator() -> AsyncIterator[str]:
        try:
            async for event in aiops_service.run_stream(input_text):
                yield _json_event(event)
        except Exception as exc:
            logger.exception("AIOps SSE 流异常中断")
            yield _json_event(
                {
                    "type": "error",
                    "stage": "error",
                    "message": f"智能运维分析中断：{type(exc).__name__}: {exc}",
                }
            )

    return EventSourceResponse(
        generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/aiops/query")
async def aiops_query(request: AiopsRequest) -> EventSourceResponse:
    return _stream_aiops(request.input)
