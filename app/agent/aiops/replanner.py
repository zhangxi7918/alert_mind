from textwrap import dedent
from typing import List, Optional

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_qwq import ChatQwen
from loguru import logger
from pydantic import BaseModel

from app.agent.aiops.planner import DASHSCOPE_COMPATIBLE_BASE_URL
from app.agent.aiops.state import PlanExecuteState
from app.agent.aiops.streaming import emit_status
from app.config import config, get_dashscope_api_key


class ReplanDecision(BaseModel):
    response: Optional[str] = None
    plan: Optional[List[str]] = None


replanner_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            dedent(
                """
                你是 AIOps Plan-Execute Graph 的裁判，负责判断任务是否已经完成。

                你会收到：
                - 用户原始任务
                - 已完成步骤和每步结果
                - 当前剩余计划

                请根据已有执行结果判断下一步：
                - 如果任务已经完成，填写 response，给出最终回答，不要填写 plan。
                - 如果任务还没有完成，填写 plan，给出剩余或调整后的可执行步骤，不要填写 response。
                - plan 中只保留后续还需要执行的步骤，不要重复已经完成且结果充分的步骤。
                - 如果当前剩余计划合理，可以原样返回；如果执行结果显示计划需要调整，请返回调整后的计划。
                """
            ).strip(),
        ),
        ("placeholder", "{messages}"),
    ]
)


def _format_past_steps(past_steps: list[tuple]) -> str:
    if not past_steps:
        return "暂无已完成步骤。"

    return "\n".join(
        f"{index}. 步骤：{step}\n   结果：{result}"
        for index, (step, result) in enumerate(past_steps, start=1)
    )


def _format_plan(plan: list[str]) -> str:
    if not plan:
        return "暂无剩余计划。"

    return "\n".join(
        f"{index}. {step}" for index, step in enumerate(plan, start=1)
    )


async def replanner(state: PlanExecuteState) -> dict[str, str | List[str]]:
    input_text = state["input"]
    past_steps = state.get("past_steps", [])
    plan = state.get("plan", [])
    emit_status("正在复核执行结果并判断是否需要继续...")

    llm = ChatQwen(
        model=config.rag_model,
        api_key=get_dashscope_api_key(),
        base_url=DASHSCOPE_COMPATIBLE_BASE_URL,
        streaming=False,
    )
    chain = replanner_prompt | llm.with_structured_output(ReplanDecision)
    decision = await chain.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=dedent(
                        f"""
                        用户原始任务：
                        {input_text}

                        已完成步骤和结果：
                        {_format_past_steps(past_steps)}

                        当前剩余计划：
                        {_format_plan(plan)}
                        """
                    ).strip()
                )
            ]
        }
    )

    if decision is None:
        logger.warning("AIOps replanner 结构化输出为空，沿用剩余计划或生成兜底报告")
        if plan:
            return {"plan": plan}
        return {"response": "已完成现有排查步骤，但复核阶段未返回结构化结论，请结合上方步骤结果继续人工确认。"}

    if decision.response:
        return {"response": decision.response}
    if decision.plan is not None:
        return {"plan": decision.plan}
    return {"plan": plan}
