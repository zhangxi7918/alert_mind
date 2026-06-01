from collections.abc import AsyncIterator
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from app.agent.aiops.executor import executor
from app.agent.aiops.planner import planner
from app.agent.aiops.replanner import replanner
from app.agent.aiops.state import PlanExecuteState


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
        async for node_output in self.app.astream(self._build_initial_state(input_text)):
            yield node_output

    async def run(self, input_text: str) -> PlanExecuteState:
        return await self.app.ainvoke(self._build_initial_state(input_text))

    def _build_initial_state(self, input_text: str) -> PlanExecuteState:
        return {
            "input": input_text,
            "plan": [],
            "past_steps": [],
            "response": "",
        }


aiops_service = AIOpsService()
