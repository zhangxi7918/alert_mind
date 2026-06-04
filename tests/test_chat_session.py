import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.services.rag_agent_service import RagAgentService


class FakeAsyncRedisContext:
    def __init__(self, checkpointer: SimpleNamespace) -> None:
        self.checkpointer = checkpointer
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> SimpleNamespace:
        self.entered = True
        return self.checkpointer

    async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
        self.exited = True


class CloseTrackingStream:
    def __init__(self, items: list) -> None:
        self.items = items
        self.index = 0
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration

        item = self.items[self.index]
        self.index += 1
        return item

    async def aclose(self) -> None:
        self.closed = True


class CancellingStream(CloseTrackingStream):
    async def __anext__(self):
        raise asyncio.CancelledError


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


class RagTraceConfigTest(unittest.TestCase):
    def test_build_config_includes_langsmith_trace_fields(self) -> None:
        service = RagAgentService()

        agent_config = service._build_config("s1")

        self.assertEqual(agent_config["configurable"], {"thread_id": "s1"})
        self.assertEqual(agent_config["run_name"], "rag_chat")
        self.assertEqual(agent_config["tags"], ["alert-mind", "rag"])
        self.assertEqual(
            agent_config["metadata"],
            {
                "session_id": "s1",
                "entrypoint": "chat",
            },
        )


class QueryStreamCancellationTest(unittest.TestCase):
    def _build_service_with_stream(self, stream: CloseTrackingStream) -> RagAgentService:
        service = RagAgentService()
        service._initialize_agent = AsyncMock()
        service.agent = SimpleNamespace(astream=lambda *args, **kwargs: stream)
        return service

    def test_closes_upstream_when_consumer_stops_early(self) -> None:
        token = AIMessageChunk(content="hello")
        stream = CloseTrackingStream([(token, {})])
        service = self._build_service_with_stream(stream)

        async def consume_first_chunk_then_close() -> dict[str, str]:
            generator = service.query_stream("你好", "s1")
            try:
                return await anext(generator)
            finally:
                await generator.aclose()

        chunk = asyncio.run(consume_first_chunk_then_close())

        self.assertEqual(chunk, {"type": "content", "data": "hello"})
        self.assertTrue(stream.closed)

    def test_re_raises_cancellation_and_closes_upstream(self) -> None:
        stream = CancellingStream([])
        service = self._build_service_with_stream(stream)

        async def consume_stream() -> None:
            async for _chunk in service.query_stream("你好", "s1"):
                pass

        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(consume_stream())

        self.assertTrue(stream.closed)


class ClearSessionTest(unittest.TestCase):
    def test_delegates_to_checkpointer(self) -> None:
        service = RagAgentService()
        service.checkpointer = SimpleNamespace(adelete_thread=AsyncMock())

        asyncio.run(service.clear_session("s1"))

        service.checkpointer.adelete_thread.assert_awaited_once_with("s1")


class RedisCheckpointerLifecycleTest(unittest.TestCase):
    def test_initialize_checkpointer_sets_up_redis_saver_with_default_ttl(self) -> None:
        service = RagAgentService()
        fake_checkpointer = SimpleNamespace(
            asetup=AsyncMock(),
            adelete_thread=AsyncMock(),
        )
        fake_context = FakeAsyncRedisContext(fake_checkpointer)

        with patch(
            "app.services.rag_agent_service.AsyncRedisSaver.from_conn_string",
            return_value=fake_context,
        ) as factory:
            asyncio.run(service.initialize_checkpointer())

        factory.assert_called_once_with(
            "redis://localhost:6379",
            ttl={
                "default_ttl": 10080,
                "refresh_on_read": True,
            },
        )
        self.assertTrue(fake_context.entered)
        fake_checkpointer.asetup.assert_awaited_once()
        self.assertIs(service.checkpointer, fake_checkpointer)

    def test_initialize_checkpointer_disables_ttl_when_config_is_non_positive(self) -> None:
        service = RagAgentService()
        fake_checkpointer = SimpleNamespace(
            asetup=AsyncMock(),
            adelete_thread=AsyncMock(),
        )
        fake_context = FakeAsyncRedisContext(fake_checkpointer)

        with (
            patch("app.services.rag_agent_service.config.redis_checkpoint_ttl_minutes", 0),
            patch(
                "app.services.rag_agent_service.AsyncRedisSaver.from_conn_string",
                return_value=fake_context,
            ) as factory,
        ):
            asyncio.run(service.initialize_checkpointer())

        factory.assert_called_once_with("redis://localhost:6379", ttl=None)

    def test_close_exits_redis_context_and_resets_agent(self) -> None:
        service = RagAgentService()
        fake_checkpointer = SimpleNamespace(asetup=AsyncMock())
        fake_context = FakeAsyncRedisContext(fake_checkpointer)

        with patch(
            "app.services.rag_agent_service.AsyncRedisSaver.from_conn_string",
            return_value=fake_context,
        ):
            asyncio.run(service.initialize_checkpointer())

        service.agent = object()
        service._initialized = True

        asyncio.run(service.close())

        self.assertTrue(fake_context.exited)
        self.assertIsNone(service.checkpointer)
        self.assertIsNone(service.agent)
        self.assertFalse(service._initialized)


if __name__ == "__main__":
    unittest.main()
