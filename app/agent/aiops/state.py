from typing import List, TypedDict


class PlanExecuteState(TypedDict):
    input: str
    plan: List[str]
    past_steps: List[tuple]
    response: str
