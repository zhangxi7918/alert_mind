from typing import Any


__all__ = ["PlanExecuteState", "executor", "planner"]


def __getattr__(name: str) -> Any:
    if name == "PlanExecuteState":
        from app.agent.aiops.state import PlanExecuteState

        return PlanExecuteState
    if name == "executor":
        from app.agent.aiops.executor import executor

        return executor
    if name == "planner":
        from app.agent.aiops.planner import planner

        return planner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
