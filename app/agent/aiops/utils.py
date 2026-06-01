from langchain_core.tools import BaseTool


def format_tools_description(tools: list[BaseTool]) -> str:
    return "\n".join(
        f"- {tool.name}: {tool.description or '暂无描述'}"
        for tool in tools
    )
