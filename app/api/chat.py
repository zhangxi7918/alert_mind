import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.models.request import ChatRequest
from app.models.response import ClearSessionResponse, SessionHistoryResponse
from app.services.rag_agent_service import rag_agent_service
from app.services.rag_stream_run_service import rag_stream_run_service

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
    run_id = await rag_stream_run_service.start_run(
        chat_request.question,
        chat_request.session_id,
        chat_request.run_id,
    )

    async def generator() -> AsyncIterator[str]:
        async for event in rag_stream_run_service.subscribe(run_id):
            if await request.is_disconnected():
                break

            yield json.dumps(event, ensure_ascii=False)

    return _stream_response(generator())


@router.get("/chat/runs/{run_id}/stream")
async def resume_chat_stream(
    run_id: str,
    request: Request,
    from_event_id: int = Query(default=0, ge=0),
) -> EventSourceResponse:
    async def generator() -> AsyncIterator[str]:
        async for event in rag_stream_run_service.subscribe(run_id, from_event_id):
            if await request.is_disconnected():
                break

            yield json.dumps(event, ensure_ascii=False)

    return _stream_response(generator())


@router.post("/chat/runs/{run_id}/cancel")
async def cancel_chat_stream(run_id: str) -> dict[str, str]:
    cancelled = await rag_stream_run_service.cancel_run(run_id)
    return {
        "run_id": run_id,
        "status": "cancelled" if cancelled else "not_found",
    }


@router.get("/chat/runs/{run_id}/snapshot")
async def get_chat_run_snapshot(run_id: str) -> dict[str, object]:
    snapshot = await rag_stream_run_service.get_snapshot(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="chat run not found")

    return snapshot


@router.get("/session/{session_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(session_id: str) -> SessionHistoryResponse:
    messages = await rag_agent_service.get_history(session_id)

    return SessionHistoryResponse(session_id=session_id, messages=messages)


@router.delete("/session/{session_id}", response_model=ClearSessionResponse)
async def clear_session(session_id: str) -> ClearSessionResponse:
    await rag_agent_service.clear_session(session_id)

    return ClearSessionResponse(session_id=session_id, status="cleared")


def _stream_response(generator: AsyncIterator[str]) -> EventSourceResponse:
    return EventSourceResponse(
        generator,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
