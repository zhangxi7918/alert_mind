from langchain_core.tools import BaseTool
from loguru import logger

from app.agent.mcp_client import get_mcp_client_with_retry, load_mcp_tools_safe
from app.tools import DEFAULT_LOCAL_AGENT_TOOLS

REQUIRED_MONITOR_TOOL_NAMES = {"query_active_alerts", "query_metric_history"}


class AIOpsToolLoadError(RuntimeError):
    """AIOps 监控工具链不可用，当前任务不能继续执行。"""


async def load_aiops_tools(stage: str) -> list[BaseTool]:
    """加载 AIOps 所需工具，监控工具缺失时显式失败。"""
    mcp_client = await get_mcp_client_with_retry()
    mcp_tools, error_message = await load_mcp_tools_safe(mcp_client)
    if error_message:
        logger.warning("MCP 工具加载失败，{} 无法继续：{}", stage, error_message)
        raise AIOpsToolLoadError(
            "监控工具服务不可用，无法执行 Prometheus 指标查询。"
            "请确认 monitor-server 已启动，并且 MCP_MONITOR_URL 指向可访问的 /mcp 地址。"
        )

    loaded_tool_names = {tool.name for tool in mcp_tools}
    missing_tool_names = sorted(REQUIRED_MONITOR_TOOL_NAMES - loaded_tool_names)
    if missing_tool_names:
        logger.warning(
            "MCP 工具缺失，{} 无法继续，missing={}, loaded={}",
            stage,
            missing_tool_names,
            sorted(loaded_tool_names),
        )
        missing_text = "、".join(missing_tool_names)
        raise AIOpsToolLoadError(
            f"监控工具服务已连接，但缺少必要工具：{missing_text}。"
            "请确认 monitor-server 使用最新代码启动。"
        )

    return [*DEFAULT_LOCAL_AGENT_TOOLS, *mcp_tools]
