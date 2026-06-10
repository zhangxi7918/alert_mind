from textwrap import dedent
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_qwq import ChatQwen
from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from typing_extensions import TypedDict

from app.config import config, get_dashscope_api_key

DASHSCOPE_COMPATIBLE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 意图分类 prompt：区分知识库问答 vs 实时运维分析
CLASSIFIER_SYSTEM_PROMPT = dedent("""\
    你是智能运维助手的意图分类器。根据用户输入，判断应路由到哪个子系统：

    - rag：用户询问文档性内容，例如：Runbook 操作步骤、历史故障复盘、排障指南、服务架构说明。
          也包括：问候、闲聊、自我介绍、非技术性对话等所有无法归入 aiops 的输入。
    - aiops：用户明确需要实时分析，例如：查询 Prometheus 告警或指标、诊断当前系统异常、分析根因、生成诊断报告。

    遇到模糊或不确定的输入，默认选择 rag。只输出分类结果，不作任何解释。
""")


class OrchestratorState(TypedDict):
    input: str
    intent: Literal["rag", "aiops"] | None


class IntentClassification(BaseModel):
    intent: Literal["rag", "aiops"]


async def classify_node(state: OrchestratorState) -> dict:
    llm = ChatQwen(
        model=config.rag_model,
        api_key=get_dashscope_api_key(),
        base_url=DASHSCOPE_COMPATIBLE_BASE_URL,
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", CLASSIFIER_SYSTEM_PROMPT),
        ("human", "{input}"),
    ])
    chain = prompt | llm.with_structured_output(IntentClassification)
    result = await chain.ainvoke({"input": state["input"]})
    return {"intent": result.intent}


def _route(state: OrchestratorState) -> str:
    return state["intent"] or "rag"


def build_orchestrator_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("classify_intent", classify_node)
    graph.set_entry_point("classify_intent")
    graph.add_conditional_edges("classify_intent", _route, {"rag": END, "aiops": END})
    return graph.compile()


orchestrator_graph = build_orchestrator_graph()
