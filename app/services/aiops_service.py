from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import uuid4

from langgraph.graph import END, StateGraph

from app.agent.aiops.executor import executor
from app.agent.aiops.planner import planner
from app.agent.aiops.replanner import replanner
from app.agent.aiops.state import PlanExecuteState


def _status_event(message: str, stage: str = "running") -> dict[str, Any]:
    return {
        "type": "status",
        "stage": stage,
        "message": message,
    }


def _events_from_stream_payload(stream_mode: str, payload: Any) -> list[dict[str, Any]]:
    if stream_mode == "custom":
        if isinstance(payload, dict) and payload.get("type") == "status":
            return [_status_event(str(payload.get("message", "")))]
        return []

    if not isinstance(payload, dict):
        return []

    events: list[dict[str, Any]] = []
    planner_output = payload.get("planner")
    if isinstance(planner_output, dict) and planner_output.get("plan"):
        steps = planner_output["plan"]
        events.append(
            {
                "type": "plan",
                "stage": "plan_created",
                "message": f"执行计划已制定，共 {len(steps)} 个步骤",
                "steps": steps,
            }
        )

    executor_output = payload.get("executor")
    if isinstance(executor_output, dict) and executor_output.get("past_steps"):
        past_steps = executor_output["past_steps"]
        current_step, result = past_steps[-1]
        plan = executor_output.get("plan", [])
        events.append(
            {
                "type": "step_complete",
                "stage": "step_executed",
                "message": "步骤执行完成",
                "current_step": current_step,
                "result": result,
                "remaining_steps": len(plan),
            }
        )

    replanner_output = payload.get("replanner")
    if isinstance(replanner_output, dict):
        if replanner_output.get("response"):
            events.append(
                {
                    "type": "report",
                    "stage": "final_report",
                    "message": "诊断报告已生成",
                    "report": replanner_output["response"],
                }
            )
        elif replanner_output.get("plan"):
            steps = replanner_output["plan"]
            events.append(
                {
                    "type": "plan_update",
                    "stage": "plan_updated",
                    "message": "后续计划已更新",
                    "steps": steps,
                }
            )

    return events


class AIOpsService:
    def __init__(self) -> None:
        self.app = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(PlanExecuteState)

        graph.add_node("planner", planner)
        graph.add_node("executor", executor)
        graph.add_node("replanner", replanner)

        graph.set_entry_point("planner")
        graph.add_edge("planner", "executor")
        graph.add_edge("executor", "replanner")
        graph.add_conditional_edges(
            "replanner",
            self._should_end,
            {"continue": "executor", "end": END},
        )

        return graph.compile()

    def _should_end(self, state: PlanExecuteState) -> Literal["continue", "end"]:
        if state.get("response"):
            return "end"
        return "continue"

    async def run_stream(self, input_text: str) -> AsyncIterator[dict[str, Any]]:
        request_id = str(uuid4())
        async for stream_mode, payload in self.app.astream(
            self._build_initial_state(input_text),
            config=self._build_trace_config(request_id),
            stream_mode=["custom", "updates"],
        ):
            for event in _events_from_stream_payload(stream_mode, payload):
                yield event

        yield {
            "type": "complete",
            "stage": "complete",
            "message": "诊断流程完成",
        }

    async def run(self, input_text: str) -> PlanExecuteState:
        request_id = str(uuid4())
        return await self.app.ainvoke(
            self._build_initial_state(input_text),
            config=self._build_trace_config(request_id),
        )

    def _build_initial_state(self, input_text: str) -> PlanExecuteState:
        return {
            "input": input_text,
            "plan": [],
            "past_steps": [],
            "response": "",
        }

    def _build_trace_config(self, request_id: str) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": request_id},
            "run_name": "aiops_diagnosis",
            "tags": ["alert-mind", "aiops", "plan-execute-replan"],
            "metadata": {
                "request_id": request_id,
                "entrypoint": "aiops",
            },
        }


aiops_service = AIOpsService()
