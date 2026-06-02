from textwrap import dedent
from typing import List

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_qwq import ChatQwen
from loguru import logger
from pydantic import BaseModel

from app.agent.mcp_client import get_mcp_client_with_retry, load_mcp_tools_safe
from app.agent.aiops.state import PlanExecuteState
from app.agent.aiops.streaming import emit_status
from app.agent.aiops.utils import format_tools_description
from app.config import config, get_dashscope_api_key
from app.tools import DEFAULT_LOCAL_AGENT_TOOLS
from app.tools.knowledge_tool import retrieve_knowledge

DASHSCOPE_COMPATIBLE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class Plan(BaseModel):
    steps: List[str]


# Planner 提示词
planner_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            dedent(
                """
                作为一个专家级别的规划者，你需要将复杂的任务分解为可执行的步骤。

                可用工具列表（用于制定计划时参考）：

                {tools_description}

                注意：你的职责是制定计划，实际的工具调用由 Executor 负责执行。

                {experience_context}

                对于给定的任务，请创建一个简单的、逐步的计划来完成它。计划应该：
                - 将任务分解为逻辑上独立的步骤
                - 每个步骤应该明确使用哪些工具（如果需要工具的话）来获取信息，最好能同时提供工具执行所需要的参数
                - 步骤之间应该有清晰的依赖关系
                - 步骤描述要具体、可操作
                - **如果有相关经验文档，请参考其中的方法和步骤制定计划**

                示例输入："分析当前系统的性能问题"
                示例输出（假设有对应工具）：
                步骤1：使用 get_metrics 工具收集系统的 CPU 和内存使用情况
                步骤2：使用 query_logs 工具检查最近的错误日志
                步骤3：使用 query_database 工具分析慢查询日志
                步骤4：综合以上信息生成性能分析报告
                """
            ).strip(),
        ),
        ("placeholder", "{messages}"),
    ]
)


async def planner(state: PlanExecuteState) -> dict[str, List[str]]:
    input_text = state["input"]
    emit_status("正在检索知识库经验并准备诊断计划...")
    experience_docs = await retrieve_knowledge.ainvoke({"query": input_text})
    mcp_client = await get_mcp_client_with_retry()
    mcp_tools, error_message = await load_mcp_tools_safe(mcp_client)
    if error_message:
        logger.warning("MCP 工具加载失败，planner 将仅使用本地工具：{}", error_message)

    all_tools = [*DEFAULT_LOCAL_AGENT_TOOLS, *mcp_tools]
    tools_description = format_tools_description(all_tools)
    emit_status("知识库与工具信息已就绪，正在生成执行计划...")

    llm = ChatQwen(
        model=config.rag_model,
        api_key=get_dashscope_api_key(),
        base_url=DASHSCOPE_COMPATIBLE_BASE_URL,
        streaming=False,
    )
    chain = planner_prompt | llm.with_structured_output(Plan)
    plan_result = await chain.ainvoke(
        {
            "messages": [HumanMessage(content=input_text)],
            "tools_description": tools_description,
            "experience_context": experience_docs or "暂无相关经验文档。",
        }
    )
    if not plan_result or not plan_result.steps:
        logger.warning("AIOps planner 结构化输出为空，使用保底诊断计划")
        return {
            "plan": [
                "查询当前监控告警和关键指标，确认是否存在活跃异常。",
                "结合知识库经验分析可能根因，并补充必要的日志或指标检查。",
                "根据已获取信息整理排查结论和处理建议。",
            ]
        }

    return {"plan": plan_result.steps}
