import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import uuid4

from loguru import logger
from redis.asyncio import Redis

from app.config import config
from app.services.rag_agent_service import rag_agent_service

RunStatus = Literal["running", "completed", "failed", "cancelled"]


class RagStreamRunService:
    """管理可恢复的 RAG 流式回答运行状态。"""

    def __init__(self, redis_url: str, terminal_ttl_seconds: int = 86400) -> None:
        self.redis_url = redis_url
        self.terminal_ttl_seconds = terminal_ttl_seconds
        self.redis: Redis | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def initialize(self) -> None:
        if self.redis is not None:
            return

        self.redis = Redis.from_url(self.redis_url, decode_responses=True)
        await self.redis.ping()

    async def close(self) -> None:
        for task in self._tasks.values():
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
            self._tasks.clear()

        if self.redis is not None:
            await self.redis.aclose()
            self.redis = None

    async def start_run(
        self,
        question: str,
        session_id: str,
        run_id: str | None = None,
    ) -> str:
        await self.initialize()
        run_id = run_id or str(uuid4())
        meta_key = self._meta_key(run_id)
        exists = await self.redis.exists(meta_key)

        if exists:
            status = await self._get_status(run_id)
            if status == "running":
                await self._fail_orphaned_run(run_id)
            return run_id

        now = self._now()
        await self.redis.hset(
            meta_key,
            mapping={
                "run_id": run_id,
                "session_id": session_id,
                "question": question,
                "status": "running",
                "last_event_id": "0",
                "created_at": now,
                "updated_at": now,
            },
        )
        await self._append_event(
            run_id,
            {
                "type": "run_started",
                "session_id": session_id,
                "question": question,
            },
        )

        self._tasks[run_id] = asyncio.create_task(
            self._produce_run(run_id, question, session_id)
        )
        self._tasks[run_id].add_done_callback(
            lambda task, current_run_id=run_id: self._tasks.pop(current_run_id, None)
        )

        return run_id

    async def subscribe(
        self,
        run_id: str,
        from_event_id: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        await self.initialize()
        if not await self.redis.exists(self._meta_key(run_id)):
            yield self._transient_event(run_id, from_event_id, "error", "流式运行不存在，请重新发送问题。")
            return

        await self._fail_orphaned_run(run_id)

        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self._channel(run_id))
        last_sent_event_id = from_event_id

        try:
            async for event in self._load_events_after(run_id, from_event_id):
                last_sent_event_id = max(last_sent_event_id, int(event["event_id"]))
                yield event

            if await self._is_terminal(run_id):
                return

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is not None:
                    event = json.loads(message["data"])
                    event_id = int(event["event_id"])
                    if event_id <= last_sent_event_id:
                        continue

                    last_sent_event_id = event_id
                    yield event

                    if self._is_terminal_event(event):
                        return
                    continue

                if await self._is_terminal(run_id):
                    async for event in self._load_events_after(run_id, last_sent_event_id):
                        last_sent_event_id = max(last_sent_event_id, int(event["event_id"]))
                        yield event
                    return
        finally:
            await pubsub.unsubscribe(self._channel(run_id))
            await pubsub.aclose()

    async def cancel_run(self, run_id: str) -> bool:
        await self.initialize()
        if not await self.redis.exists(self._meta_key(run_id)):
            return False

        task = self._tasks.pop(run_id, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        status = await self._get_status(run_id)
        if status not in {"completed", "failed", "cancelled"}:
            await self._append_event(
                run_id,
                {"type": "cancelled", "message": "已停止生成"},
                status="cancelled",
            )

        return True

    async def get_snapshot(self, run_id: str) -> dict[str, Any] | None:
        await self.initialize()
        if not await self.redis.exists(self._meta_key(run_id)):
            return None

        await self._fail_orphaned_run(run_id)

        meta = await self.redis.hgetall(self._meta_key(run_id))
        events = [event async for event in self._load_events_after(run_id, 0)]
        assistant_content = "".join(
            str(event.get("data", ""))
            for event in events
            if event.get("type") == "content"
        )

        return {
            "run_id": run_id,
            "session_id": meta.get("session_id", ""),
            "question": meta.get("question", ""),
            "status": meta.get("status", "failed"),
            "last_event_id": int(meta.get("last_event_id", "0")),
            "assistant_content": assistant_content,
        }

    async def _produce_run(self, run_id: str, question: str, session_id: str) -> None:
        try:
            async for chunk in rag_agent_service.query_stream(question, session_id):
                if chunk.get("type") == "content":
                    await self._append_event(
                        run_id,
                        {"type": "content", "data": chunk.get("data", "")},
                    )
                elif chunk.get("type") in {"complete", "done"}:
                    await self._append_event(
                        run_id,
                        {"type": "complete"},
                        status="completed",
                    )
        except asyncio.CancelledError:
            logger.info("RAG 可恢复流已取消：run_id={}", run_id)
            raise
        except Exception as exc:
            logger.exception("RAG 可恢复流异常：run_id={}", run_id)
            await self._append_event(
                run_id,
                {
                    "type": "error",
                    "data": f"流式回答失败：{type(exc).__name__}: {exc}",
                },
                status="failed",
            )

    async def _append_event(
        self,
        run_id: str,
        event: dict[str, Any],
        status: RunStatus | None = None,
    ) -> dict[str, Any]:
        event_id = await self.redis.hincrby(self._meta_key(run_id), "last_event_id", 1)
        payload = {
            "run_id": run_id,
            "event_id": event_id,
            **event,
        }
        encoded = json.dumps(payload, ensure_ascii=False)
        await self.redis.rpush(self._events_key(run_id), encoded)
        mapping: dict[str, str] = {"updated_at": self._now()}
        if status is not None:
            mapping["status"] = status
        await self.redis.hset(self._meta_key(run_id), mapping=mapping)
        await self.redis.publish(self._channel(run_id), encoded)

        if status in {"completed", "failed", "cancelled"}:
            await self.redis.expire(self._meta_key(run_id), self.terminal_ttl_seconds)
            await self.redis.expire(self._events_key(run_id), self.terminal_ttl_seconds)

        return payload

    async def _load_events_after(
        self,
        run_id: str,
        from_event_id: int,
    ) -> AsyncIterator[dict[str, Any]]:
        raw_events = await self.redis.lrange(self._events_key(run_id), from_event_id, -1)
        for raw_event in raw_events:
            event = json.loads(raw_event)
            if int(event["event_id"]) > from_event_id:
                yield event

    async def _fail_orphaned_run(self, run_id: str) -> None:
        status = await self._get_status(run_id)
        if status == "running" and run_id not in self._tasks:
            await self._append_event(
                run_id,
                {
                    "type": "error",
                    "data": "服务已重启，当前回答无法继续生成，请重新发送问题。",
                },
                status="failed",
            )

    async def _get_status(self, run_id: str) -> str | None:
        return await self.redis.hget(self._meta_key(run_id), "status")

    async def _is_terminal(self, run_id: str) -> bool:
        return await self._get_status(run_id) in {"completed", "failed", "cancelled"}

    def _is_terminal_event(self, event: dict[str, Any]) -> bool:
        return event.get("type") in {"complete", "error", "cancelled"}

    def _transient_event(
        self,
        run_id: str,
        from_event_id: int,
        event_type: str,
        message: str,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "event_id": from_event_id + 1,
            "type": event_type,
            "data": message,
        }

    def _meta_key(self, run_id: str) -> str:
        return f"rag:stream:{run_id}:meta"

    def _events_key(self, run_id: str) -> str:
        return f"rag:stream:{run_id}:events"

    def _channel(self, run_id: str) -> str:
        return f"rag:stream:{run_id}:channel"

    def _now(self) -> str:
        return str(time.time())


rag_stream_run_service = RagStreamRunService(config.redis_url)
