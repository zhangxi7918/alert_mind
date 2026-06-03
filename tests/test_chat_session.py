import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.services.rag_agent_service import RagAgentService


class GetHistoryTest(unittest.TestCase):
    def _build_service(self, messages: list) -> RagAgentService:
        """构造一个跳过真实初始化、返回指定消息快照的服务实例。"""
        service = RagAgentService()
        service._initialize_agent = AsyncMock()
        snapshot = SimpleNamespace(values={"messages": messages})
        service.agent = SimpleNamespace(aget_state=AsyncMock(return_value=snapshot))
        return service

    def test_filters_system_tool_and_empty_ai_messages(self) -> None:
        messages = [
            SystemMessage(content="你是运维助手"),
            HumanMessage(content="磁盘告警怎么处理"),
            # 仅含工具调用、无文本的 AI 消息应被过滤
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "retrieve_knowledge", "args": {}, "id": "1"},
                ],
            ),
            ToolMessage(content="检索结果", tool_call_id="1"),
            AIMessage(content="先清理日志再扩容"),
        ]
        service = self._build_service(messages)

        history = asyncio.run(service.get_history("s1"))

        self.assertEqual(
            history,
            [
                {"role": "user", "content": "磁盘告警怎么处理"},
                {"role": "assistant", "content": "先清理日志再扩容"},
            ],
        )

    def test_extracts_text_from_content_blocks(self) -> None:
        messages = [
            HumanMessage(content="你好"),
            AIMessage(
                content=[
                    {"type": "text", "text": "你"},
                    {"type": "text", "text": "好"},
                ],
            ),
        ]
        service = self._build_service(messages)

        history = asyncio.run(service.get_history("s1"))

        self.assertEqual(history[1], {"role": "assistant", "content": "你好"})

    def test_empty_thread_returns_empty_history(self) -> None:
        service = RagAgentService()
        service._initialize_agent = AsyncMock()
        snapshot = SimpleNamespace(values={})  # 未知会话的 aget_state 返回空 values
        service.agent = SimpleNamespace(aget_state=AsyncMock(return_value=snapshot))

        history = asyncio.run(service.get_history("unknown"))

        self.assertEqual(history, [])


class ClearSessionTest(unittest.TestCase):
    def test_delegates_to_checkpointer(self) -> None:
        service = RagAgentService()
        service.checkpointer.adelete_thread = AsyncMock()

        asyncio.run(service.clear_session("s1"))

        service.checkpointer.adelete_thread.assert_awaited_once_with("s1")


if __name__ == "__main__":
    unittest.main()
