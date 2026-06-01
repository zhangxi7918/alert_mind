from typing import Any

from langchain_core.messages import HumanMessage
from langchain_qwq import ChatQwen
from langgraph.prebuilt import create_react_agent

from app.agent.aiops.planner import DASHSCOPE_COMPATIBLE_BASE_URL
from app.agent.aiops.state import PlanExecuteState
from app.config import config
from app.tools import DEFAULT_LOCAL_AGENT_TOOLS


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return str(content)


async def executor(state: PlanExecuteState) -> dict[str, Any]:
    plan = state.get("plan", [])
    if not plan:
        return state

    current_step = plan[0]
    llm = ChatQwen(
        model=config.rag_model,
        api_key=config.dashscope_api_key or "missing-dashscope-api-key",
        base_url=DASHSCOPE_COMPATIBLE_BASE_URL,
        streaming=False,
    )

    # ReAct Agent 会自行判断是否调用工具，并处理工具结果回传给 LLM 的循环。
    agent_executor = create_react_agent(
        model=llm,
        tools=DEFAULT_LOCAL_AGENT_TOOLS,
    )
    agent_result = await agent_executor.ainvoke(
        {"messages": [HumanMessage(content=current_step)]}
    )

    messages = agent_result.get("messages", [])
    result = ""
    if messages:
        result = _message_content_to_text(messages[-1].content)

    return {
        "past_steps": state.get("past_steps", []) + [(current_step, result)],
        "plan": plan[1:],
    }
