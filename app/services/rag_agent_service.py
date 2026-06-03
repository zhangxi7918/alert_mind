from collections.abc import AsyncIterator

from langchain.agents import create_agent
from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from langchain_qwq import ChatQwen
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger

from app.agent.mcp_client import get_mcp_client_with_retry, load_mcp_tools_safe
from app.config import config, get_dashscope_api_key
from app.tools import DEFAULT_LOCAL_AGENT_TOOLS

DASHSCOPE_COMPATIBLE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class RagAgentService:
    def __init__(self) -> None:
        self.model: ChatQwen | None = None
        self.checkpointer = MemorySaver()
        self.system_prompt = self._build_system_prompt()
        self.agent = None
        self._initialized = False

    async def _initialize_agent(self) -> None:
        if self._initialized:
            return

        mcp_client = await get_mcp_client_with_retry()
        mcp_tools, error_message = await load_mcp_tools_safe(mcp_client)
        if error_message:
            logger.warning("MCP 工具加载失败，将仅使用本地工具：{}", error_message)

        all_tools = [*DEFAULT_LOCAL_AGENT_TOOLS, *mcp_tools]
        self.agent = create_agent(
            self._get_model(),
            tools=all_tools,
            checkpointer=self.checkpointer,
        )
        self._initialized = True

    async def query(self, question: str, session_id: str) -> str:
        await self._initialize_agent()

        result = await self.agent.ainvoke(
            self._build_input(question),
            config=self._build_config(session_id),
        )
        return result["messages"][-1].content

    async def query_stream(
        self,
        question: str,
        session_id: str,
    ) -> AsyncIterator[dict[str, str]]:
        await self._initialize_agent()

        async for token, _metadata in self.agent.astream(
            self._build_input(question),
            config=self._build_config(session_id),
            stream_mode="messages",
        ):
            if not isinstance(token, AIMessageChunk):
                continue

            for block in token.content_blocks:
                if block.get("type") == "text":
                    yield {"type": "content", "data": block.get("text", "")}

        yield {"type": "complete"}

    def _build_system_prompt(self) -> str:
        return (
            "你是一个专业的运维助手。"
            "回答问题前，先使用工具检索知识库中相关的故障、告警和处理文档；"
            "再基于检索结果给出清晰、可执行的分析和处置建议。"
            "如果检索结果中包含 [来源: xxx] 标注，回答末尾必须注明参考来源，格式为：\n> 参考来源：xxx"
        )

    def _build_input(
        self,
        question: str,
    ) -> dict[str, list[SystemMessage | HumanMessage]]:
        return {
            "messages": [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=question),
            ],
        }

    def _build_config(self, session_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": session_id}}

    def _get_model(self) -> ChatQwen:
        if self.model is None:
            self.model = ChatQwen(
                model=config.rag_model,
                api_key=get_dashscope_api_key(),
                base_url=DASHSCOPE_COMPATIBLE_BASE_URL,
                streaming=True,
            )

        return self.model


rag_agent_service = RagAgentService()
