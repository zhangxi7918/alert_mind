import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.models.request import ChatRequest
from app.models.response import ClearSessionResponse, SessionHistoryResponse
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
async def chat_stream(
    request: Request,
    chat_request: ChatRequest,
) -> EventSourceResponse:
    async def generator() -> AsyncIterator[str]:
        stream = rag_agent_service.query_stream(
            chat_request.question,
            chat_request.session_id,
        )
        try:
            async for chunk in stream:
                if await request.is_disconnected():
                    break

                yield json.dumps(chunk, ensure_ascii=False)
        finally:
            await stream.aclose()

    return EventSourceResponse(generator())


@router.get("/session/{session_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(session_id: str) -> SessionHistoryResponse:
    messages = await rag_agent_service.get_history(session_id)

    return SessionHistoryResponse(session_id=session_id, messages=messages)


@router.delete("/session/{session_id}", response_model=ClearSessionResponse)
async def clear_session(session_id: str) -> ClearSessionResponse:
    await rag_agent_service.clear_session(session_id)

    return ClearSessionResponse(session_id=session_id, status="cleared")
