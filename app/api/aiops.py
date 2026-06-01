import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.models.request import AiopsRequest
from app.services.aiops_service import aiops_service

router = APIRouter()


def _json_event(message: dict[str, Any]) -> str:
    return json.dumps(message, ensure_ascii=False)


def _format_plan_steps(steps: list[str]) -> str:
    return "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))


def _events_from_node_output(node_output: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    planner_output = node_output.get("planner")
    if planner_output and planner_output.get("plan"):
        events.append(
            {
                "type": "plan",
                "message": _format_plan_steps(planner_output["plan"]),
            }
        )

    executor_output = node_output.get("executor")
    if executor_output and executor_output.get("past_steps"):
        step, result = executor_output["past_steps"][-1]
        events.append(
            {
                "type": "step_complete",
                "message": f"{step}\n\n{result}",
            }
        )

    replanner_output = node_output.get("replanner")
    if replanner_output:
        if replanner_output.get("response"):
            events.append(
                {
                    "type": "report",
                    "report": replanner_output["response"],
                }
            )
        elif replanner_output.get("plan"):
            events.append(
                {
                    "type": "status",
                    "message": "已更新后续计划：\n" + _format_plan_steps(replanner_output["plan"]),
                }
            )

    return events


def _stream_aiops(input_text: str) -> EventSourceResponse:
    async def generator() -> AsyncIterator[str]:
        async for node_output in aiops_service.run_stream(input_text):
            for event in _events_from_node_output(node_output):
                yield _json_event(event)

        yield _json_event({"type": "complete"})

    return EventSourceResponse(generator())


@router.post("/aiops/query")
async def aiops_query(request: AiopsRequest) -> EventSourceResponse:
    return _stream_aiops(request.input)
