import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.agent.aiops.tool_loader import AIOpsToolLoadError
from app.models.request import AiopsRequest
from app.services.aiops_service import aiops_service

router = APIRouter()


def _json_event(message: dict[str, Any]) -> str:
    return json.dumps(message, ensure_ascii=False)


def _stream_aiops(http_request: Request, input_text: str) -> EventSourceResponse:
    async def generator() -> AsyncIterator[str]:
        stream = aiops_service.run_stream(input_text)
        try:
            async for event in stream:
                if await http_request.is_disconnected():
                    break

                yield _json_event(event)
        except asyncio.CancelledError:
            raise
        except AIOpsToolLoadError as exc:
            logger.warning("AIOps 监控工具不可用：{}", exc)
            yield _json_event(
                {
                    "type": "error",
                    "stage": "error",
                    "message": str(exc),
                }
            )
        except Exception as exc:
            logger.exception("AIOps SSE 流异常中断")
            yield _json_event(
                {
                    "type": "error",
                    "stage": "error",
                    "message": f"智能运维分析中断：{type(exc).__name__}: {exc}",
                }
            )
        finally:
            await stream.aclose()

    return EventSourceResponse(
        generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/aiops/query")
async def aiops_query(
    http_request: Request,
    request: AiopsRequest,
) -> EventSourceResponse:
    return _stream_aiops(http_request, request.input)
