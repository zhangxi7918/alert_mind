import asyncio
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from loguru import logger

from app.config import config


def _build_mcp_server_config() -> dict[str, dict[str, Any]]:
    return {
        "monitor": {
            "transport": config.mcp_monitor_transport,
            "url": config.mcp_monitor_url,
        }
    }


async def get_mcp_client_with_retry(
    max_retries: int = 3,
    retry_interval: float = 1.0,
) -> MultiServerMCPClient:
    """创建 MCP Client，初始化失败时按固定间隔重试。"""
    last_error: Exception | None = None
    server_config = _build_mcp_server_config()

    for attempt in range(max_retries):
        try:
            return MultiServerMCPClient(server_config)
        except Exception as exc:
            last_error = exc
            if attempt == max_retries - 1:
                break

            logger.warning(
                "MCP client 初始化失败，准备重试 {}/{}：{}",
                attempt + 1,
                max_retries,
                format_exception_chain(exc),
            )
            await asyncio.sleep(retry_interval)

    if last_error is not None:
        raise last_error

    raise RuntimeError("MCP client 初始化失败：max_retries 必须大于 0")


async def load_mcp_tools_safe(
    client: MultiServerMCPClient,
) -> tuple[list[BaseTool], str | None]:
    """安全加载 MCP 工具，失败时返回错误字符串而不是抛出异常。"""
    try:
        tools = await client.get_tools()
    except Exception as exc:
        return [], format_exception_chain(exc)

    return tools, None


def format_exception_chain(exc: BaseException) -> str:
    """把异常及其 cause/context 链格式化成便于日志阅读的字符串。"""
    parts: list[str] = []

    def collect(current: BaseException) -> None:
        parts.append(f"{type(current).__name__}: {current}")

        if isinstance(current, BaseExceptionGroup):
            for nested in current.exceptions:
                collect(nested)

        next_error = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
        if next_error is not None:
            collect(next_error)

    collect(exc)

    return " -> ".join(parts)
