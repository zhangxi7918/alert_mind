from typing import Any

from langchain_core.messages import HumanMessage
from langchain_qwq import ChatQwen
from langgraph.prebuilt import create_react_agent

from app.agent.aiops.planner import DASHSCOPE_COMPATIBLE_BASE_URL
from app.agent.aiops.state import PlanExecuteState
from app.agent.aiops.streaming import emit_status
from app.agent.aiops.tool_loader import load_aiops_tools
from app.config import config, get_dashscope_api_key


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return str(content)


async def executor(state: PlanExecuteState) -> dict[str, Any]:
    plan = state.get("plan", [])
    if not plan:
        return {}

    current_step = plan[0]
    emit_status(f"正在执行计划步骤：{current_step}")
    llm = ChatQwen(
        model=config.rag_model,
        api_key=get_dashscope_api_key(),
        base_url=DASHSCOPE_COMPATIBLE_BASE_URL,
        streaming=False,
    )
    all_tools = await load_aiops_tools("executor")
    emit_status("工具链已准备完成，正在分析该步骤结果...")

    # ReAct Agent 会自行判断是否调用工具，并处理工具结果回传给 LLM 的循环。
    agent_executor = create_react_agent(
        model=llm,
        tools=all_tools,
    )
    agent_result = await agent_executor.ainvoke(
        {"messages": [HumanMessage(content=current_step)]}
    )

    messages = agent_result.get("messages", [])
    result = ""
    if messages:
        result = _message_content_to_text(messages[-1].content)

    return {
        "past_steps": [(current_step, result)],
        "plan": plan[1:],
    }
