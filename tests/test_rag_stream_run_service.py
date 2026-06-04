import asyncio
import unittest
from collections import defaultdict
from unittest.mock import patch

from app.services.rag_stream_run_service import RagStreamRunService


class FakeRedis:
    def __init__(self) -> None:
        self.hashes = defaultdict(dict)
        self.streams = defaultdict(list)
        self.stream_counters = defaultdict(int)
        self.expirations = {}
        self.condition = asyncio.Condition()

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def exists(self, key: str) -> int:
        return int(key in self.hashes or key in self.streams)

    async def hset(self, key: str, mapping: dict) -> None:
        self.hashes[key].update({name: str(value) for name, value in mapping.items()})

    async def hget(self, key: str, name: str):
        return self.hashes[key].get(name)

    async def hgetall(self, key: str) -> dict:
        return dict(self.hashes[key])

    async def xadd(self, key: str, fields: dict) -> str:
        self.stream_counters[key] += 1
        event_id = f"{self.stream_counters[key]}-0"
        self.streams[key].append((event_id, dict(fields)))
        async with self.condition:
            self.condition.notify_all()
        return event_id

    async def xrange(self, key: str, min: str = "-", max: str = "+") -> list:
        values = list(self.streams[key])
        if min.startswith("("):
            from_event_id = min[1:]
            values = [
                (event_id, fields)
                for event_id, fields in values
                if self._stream_id_after(event_id, from_event_id)
            ]
        return values

    async def xread(self, streams: dict, count: int = 20, block: int = 0) -> list:
        timeout = block / 1000 if block else 0
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while True:
            result = self._read_streams(streams, count)
            if result:
                return result

            if timeout <= 0:
                return []

            remaining = deadline - loop.time()
            if remaining <= 0:
                return []

            async with self.condition:
                try:
                    await asyncio.wait_for(self.condition.wait(), remaining)
                except asyncio.TimeoutError:
                    return []

    async def expire(self, key: str, ttl: int) -> None:
        self.expirations[key] = ttl

    def _read_streams(self, streams: dict, count: int) -> list:
        result = []
        for key, from_event_id in streams.items():
            messages = [
                (event_id, fields)
                for event_id, fields in self.streams[key]
                if self._stream_id_after(event_id, from_event_id)
            ]
            if messages:
                result.append([key, messages[:count]])
        return result

    def _stream_id_after(self, event_id: str, from_event_id: str) -> bool:
        return self._stream_id_parts(event_id) > self._stream_id_parts(from_event_id)

    def _stream_id_parts(self, event_id: str) -> tuple[int, int]:
        milliseconds, sequence = event_id.split("-", 1)
        return int(milliseconds), int(sequence)


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
                snapshot = await anext(subscriber)
                run_started = await anext(subscriber)
                first_content = await anext(subscriber)
            finally:
                await subscriber.aclose()

            self.assertEqual(snapshot["type"], "snapshot")
            self.assertEqual(snapshot["assistant_content"], "")
            self.assertEqual(run_started["type"], "run_started")
            self.assertEqual(first_content["type"], "content")
            self.assertEqual(first_content["data"], "a")

            release_second_content.set()
            await asyncio.wait_for(service._tasks[run_id], 1)

            resumed_events = [event async for event in service.subscribe(run_id, "2-0")]

        self.assertEqual([event["type"] for event in resumed_events], ["snapshot", "content", "complete"])
        self.assertEqual(resumed_events[0]["assistant_content"], "a")
        self.assertEqual(resumed_events[1]["data"], "b")

    async def test_subscribe_waits_for_stream_events_after_snapshot(self) -> None:
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
            run_id = await service.start_run("你好", "s1", "run-1b")
            await first_content_written.wait()

            subscriber = service.subscribe(run_id, "2-0")
            try:
                snapshot = await anext(subscriber)
                release_second_content.set()
                content = await anext(subscriber)
                complete = await anext(subscriber)
            finally:
                await subscriber.aclose()

        self.assertEqual(snapshot["type"], "snapshot")
        self.assertEqual(snapshot["assistant_content"], "a")
        self.assertEqual(content["type"], "content")
        self.assertEqual(content["data"], "b")
        self.assertEqual(complete["type"], "complete")

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

            events = [event async for event in service.subscribe(run_id, "2-0")]

        self.assertEqual([event["type"] for event in events], ["snapshot", "content", "complete"])
        self.assertEqual(events[0]["assistant_content"], "a")
        self.assertEqual(events[0]["last_event_id"], "2-0")
        self.assertEqual(events[1]["data"], "b")

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
            events = [event async for event in service.subscribe(run_id, "2-0")]

        self.assertTrue(cancelled)
        self.assertEqual([event["type"] for event in events], ["snapshot", "cancelled"])
        self.assertEqual(events[0]["assistant_content"], "a")

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
                "last_event_id": "0-0",
            },
        )

        events = [event async for event in service.subscribe("run-5", "0-0")]

        self.assertEqual([event["type"] for event in events], ["snapshot", "error"])
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
        self.assertEqual(snapshot["last_event_id"], "4-0")


if __name__ == "__main__":
    unittest.main()
