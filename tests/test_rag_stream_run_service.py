import asyncio
import unittest
from collections import defaultdict
from unittest.mock import patch

from app.services.rag_stream_run_service import RagStreamRunService


class FakePubSub:
    def __init__(self, redis) -> None:
        self.redis = redis
        self.channels = set()
        self.queue = asyncio.Queue()

    async def subscribe(self, channel: str) -> None:
        self.channels.add(channel)
        self.redis.subscribers[channel].append(self.queue)

    async def unsubscribe(self, channel: str) -> None:
        if channel in self.channels:
            self.redis.subscribers[channel].remove(self.queue)
            self.channels.remove(channel)

    async def aclose(self) -> None:
        for channel in list(self.channels):
            await self.unsubscribe(channel)

    async def get_message(self, ignore_subscribe_messages=True, timeout=0):
        try:
            return await asyncio.wait_for(self.queue.get(), timeout)
        except asyncio.TimeoutError:
            return None


class FakeRedis:
    def __init__(self) -> None:
        self.hashes = defaultdict(dict)
        self.lists = defaultdict(list)
        self.expirations = {}
        self.subscribers = defaultdict(list)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def exists(self, key: str) -> int:
        return int(key in self.hashes or key in self.lists)

    async def hset(self, key: str, mapping: dict) -> None:
        self.hashes[key].update({name: str(value) for name, value in mapping.items()})

    async def hget(self, key: str, name: str):
        return self.hashes[key].get(name)

    async def hgetall(self, key: str) -> dict:
        return dict(self.hashes[key])

    async def hincrby(self, key: str, name: str, amount: int) -> int:
        current = int(self.hashes[key].get(name, "0")) + amount
        self.hashes[key][name] = str(current)
        return current

    async def rpush(self, key: str, value: str) -> None:
        self.lists[key].append(value)

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        values = self.lists[key]
        if end == -1:
            return values[start:]
        return values[start : end + 1]

    async def publish(self, channel: str, value: str) -> None:
        for queue in list(self.subscribers[channel]):
            await queue.put({"type": "message", "channel": channel, "data": value})

    async def expire(self, key: str, ttl: int) -> None:
        self.expirations[key] = ttl

    def pubsub(self) -> FakePubSub:
        return FakePubSub(self)


class FakeRagAgent:
    def __init__(self, stream_factory) -> None:
        self.stream_factory = stream_factory

    def query_stream(self, question: str, session_id: str):
        return self.stream_factory(question, session_id)


class RagStreamRunServiceTest(unittest.IsolatedAsyncioTestCase):
    def _build_service(self, terminal_ttl_seconds: int = 86400) -> RagStreamRunService:
        service = RagStreamRunService("redis://test", terminal_ttl_seconds=terminal_ttl_seconds)
        service.redis = FakeRedis()
        return service

    async def test_background_run_continues_after_subscriber_disconnect(self) -> None:
        first_content_written = asyncio.Event()
        release_second_content = asyncio.Event()

        async def stream(_question: str, _session_id: str):
            yield {"type": "content", "data": "a"}
            first_content_written.set()
            await release_second_content.wait()
            yield {"type": "content", "data": "b"}
            yield {"type": "complete"}

        service = self._build_service()
        with patch(
            "app.services.rag_stream_run_service.rag_agent_service",
            FakeRagAgent(stream),
        ):
            run_id = await service.start_run("你好", "s1", "run-1")
            await first_content_written.wait()

            subscriber = service.subscribe(run_id)
            try:
                first_event = await anext(subscriber)
                second_event = await anext(subscriber)
            finally:
                await subscriber.aclose()

            self.assertEqual(first_event["type"], "run_started")
            self.assertEqual(second_event["type"], "content")

            release_second_content.set()
            await asyncio.wait_for(service._tasks[run_id], 1)

            resumed_events = [event async for event in service.subscribe(run_id, 2)]

        self.assertEqual([event["type"] for event in resumed_events], ["content", "complete"])
        self.assertEqual(resumed_events[0]["data"], "b")

    async def test_resume_replays_only_events_after_offset(self) -> None:
        async def stream(_question: str, _session_id: str):
            yield {"type": "content", "data": "a"}
            yield {"type": "content", "data": "b"}
            yield {"type": "complete"}

        service = self._build_service()
        with patch(
            "app.services.rag_stream_run_service.rag_agent_service",
            FakeRagAgent(stream),
        ):
            run_id = await service.start_run("你好", "s1", "run-2")
            await asyncio.wait_for(service._tasks[run_id], 1)

            events = [event async for event in service.subscribe(run_id, 2)]

        self.assertEqual([event["type"] for event in events], ["content", "complete"])
        self.assertEqual(events[0]["event_id"], 3)

    async def test_cancel_writes_cancelled_terminal_event(self) -> None:
        stream_started = asyncio.Event()

        async def stream(_question: str, _session_id: str):
            yield {"type": "content", "data": "a"}
            stream_started.set()
            await asyncio.Event().wait()

        service = self._build_service()
        with patch(
            "app.services.rag_stream_run_service.rag_agent_service",
            FakeRagAgent(stream),
        ):
            run_id = await service.start_run("你好", "s1", "run-3")
            await stream_started.wait()

            cancelled = await service.cancel_run(run_id)
            events = [event async for event in service.subscribe(run_id, 0)]

        self.assertTrue(cancelled)
        self.assertEqual(events[-1]["type"], "cancelled")

    async def test_completed_run_sets_ttl_on_meta_and_events(self) -> None:
        async def stream(_question: str, _session_id: str):
            yield {"type": "complete"}

        service = self._build_service(terminal_ttl_seconds=60)
        with patch(
            "app.services.rag_stream_run_service.rag_agent_service",
            FakeRagAgent(stream),
        ):
            run_id = await service.start_run("你好", "s1", "run-4")
            await asyncio.wait_for(service._tasks[run_id], 1)

        self.assertEqual(service.redis.expirations[f"rag:stream:{run_id}:meta"], 60)
        self.assertEqual(service.redis.expirations[f"rag:stream:{run_id}:events"], 60)

    async def test_orphaned_running_run_returns_failed_event(self) -> None:
        service = self._build_service()
        await service.redis.hset(
            "rag:stream:run-5:meta",
            mapping={
                "run_id": "run-5",
                "session_id": "s1",
                "question": "你好",
                "status": "running",
                "last_event_id": "0",
            },
        )

        events = [event async for event in service.subscribe("run-5", 0)]

        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("服务已重启", events[-1]["data"])

    async def test_snapshot_rebuilds_assistant_content_from_events(self) -> None:
        async def stream(_question: str, _session_id: str):
            yield {"type": "content", "data": "hello"}
            yield {"type": "content", "data": " world"}
            yield {"type": "complete"}

        service = self._build_service()
        with patch(
            "app.services.rag_stream_run_service.rag_agent_service",
            FakeRagAgent(stream),
        ):
            run_id = await service.start_run("你好", "s1", "run-6")
            await asyncio.wait_for(service._tasks[run_id], 1)

            snapshot = await service.get_snapshot(run_id)

        self.assertEqual(snapshot["run_id"], "run-6")
        self.assertEqual(snapshot["session_id"], "s1")
        self.assertEqual(snapshot["assistant_content"], "hello world")
        self.assertEqual(snapshot["last_event_id"], 4)


if __name__ == "__main__":
    unittest.main()
