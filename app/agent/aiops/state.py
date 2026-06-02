import operator
from typing import Annotated, List, TypedDict


class PlanExecuteState(TypedDict):
    input: str
    plan: List[str]
    past_steps: Annotated[List[tuple], operator.add]
    response: str
