import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.models.request import ChatRequest
from app.services.aiops_service import aiops_service
from app.services.orchestrator_service import orchestrator_service
from app.services.rag_stream_run_service import rag_stream_run_service

router = APIRouter()


def _json_event(message: dict[str, Any]) -> str:
    return json.dumps(message, ensure_ascii=False)


@router.post("/chat/unified")
async def unified_chat(
    http_request: Request,
    chat_request: ChatRequest,
) -> EventSourceResponse:
    async def generator() -> AsyncIterator[str]:
        # Step 1: 意图分类（单次 LLM 调用）
        intent = await orchestrator_service.classify(chat_request.question)
        yield _json_event({"type": "routed_to", "agent": intent})

        # Step 2: 按意图透传对应 agent 的流式事件
        if intent == "rag":
            run_id = await rag_stream_run_service.start_run(
                session_id=chat_request.session_id,
                question=chat_request.question,
                run_id=chat_request.run_id,
            )
            # subscribe() 已返回 JSON 字符串，直接透传
            async for event in rag_stream_run_service.subscribe(run_id):
                if await http_request.is_disconnected():
                    break
                yield event
        else:
            stream = aiops_service.run_stream(chat_request.question)
            try:
                async for event_dict in stream:
                    if await http_request.is_disconnected():
                        break
                    yield _json_event(event_dict)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("AIOps unified 流异常中断")
                yield _json_event({
                    "type": "error",
                    "stage": "error",
                    "message": f"智能运维分析中断：{type(exc).__name__}: {exc}",
                })
            finally:
                await stream.aclose()

    return EventSourceResponse(
        generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
