from typing import Any

from langchain_core.messages import HumanMessage
from langchain_qwq import ChatQwen
from langgraph.prebuilt import create_react_agent
from loguru import logger

from app.agent.mcp_client import get_mcp_client_with_retry, load_mcp_tools_safe
from app.agent.aiops.planner import DASHSCOPE_COMPATIBLE_BASE_URL
from app.agent.aiops.state import PlanExecuteState
from app.agent.aiops.streaming import emit_status
from app.config import config, get_dashscope_api_key
from app.tools import DEFAULT_LOCAL_AGENT_TOOLS


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
    mcp_client = await get_mcp_client_with_retry()
    mcp_tools, error_message = await load_mcp_tools_safe(mcp_client)
    if error_message:
        logger.warning("MCP 工具加载失败，executor 将仅使用本地工具：{}", error_message)

    all_tools = [*DEFAULT_LOCAL_AGENT_TOOLS, *mcp_tools]
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
