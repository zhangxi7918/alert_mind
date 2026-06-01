import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.models.request import ChatRequest
from app.services.rag_agent_service import rag_agent_service

router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest) -> dict[str, str]:
    result = await rag_agent_service.query(request.question, request.session_id)

    return {
        "answer": result,
        "session_id": request.session_id,
    }


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> EventSourceResponse:
    async def generator() -> AsyncIterator[str]:
        async for chunk in rag_agent_service.query_stream(
            request.question,
            request.session_id,
        ):
            yield json.dumps(chunk, ensure_ascii=False)

    return EventSourceResponse(generator())
