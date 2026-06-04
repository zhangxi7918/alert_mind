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
INITIAL_STREAM_ID = "0-0"
ORPHANED_RUN_ERROR = "服务已重启或运行超时，当前回答无法继续生成，请重新发送问题。"
STREAM_META_PATTERN = "rag:stream:*:meta"


class RagStreamRunService:
    """管理可恢复的 RAG 流式回答运行状态。"""

    def __init__(
        self,
        redis_url: str,
        terminal_ttl_seconds: int = 86400,
        running_timeout_seconds: int = 7200,
    ) -> None:
        self.redis_url = redis_url
        self.terminal_ttl_seconds = terminal_ttl_seconds
        self.running_timeout_seconds = running_timeout_seconds
        self.redis: Redis | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def initialize(self) -> None:
        if self.redis is not None:
            return

        self.redis = Redis.from_url(self.redis_url, decode_responses=True)
        await self.redis.ping()
        await self.cleanup_running_runs()

    async def cleanup_running_runs(self) -> None:
        """清理 Redis 中无法由当前进程继续恢复的 running stream run。"""
        if self.redis is None:
            return

        async for meta_key in self.redis.scan_iter(match=STREAM_META_PATTERN):
            meta = await self.redis.hgetall(meta_key)
            if meta.get("status") != "running":
                continue

            run_id = meta.get("run_id") or self._run_id_from_meta_key(str(meta_key))
            if not run_id:
                continue

            await self._fail_orphaned_run(str(run_id), meta)

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
                "last_event_id": INITIAL_STREAM_ID,
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
        from_event_id: str = INITIAL_STREAM_ID,
    ) -> AsyncIterator[dict[str, Any]]:
        await self.initialize()
        if not await self.redis.exists(self._meta_key(run_id)):
            yield self._transient_event(run_id, from_event_id, "error", "流式运行不存在，请重新发送问题。")
            return

        await self._fail_orphaned_run(run_id)

        snapshot = await self.get_snapshot(run_id, until_event_id=from_event_id)
        if snapshot is None:
            yield self._transient_event(run_id, from_event_id, "error", "流式运行不存在，请重新发送问题。")
            return

        yield snapshot
        last_event_id = str(snapshot["event_id"])

        async for event in self._load_events_after(run_id, last_event_id):
            last_event_id = str(event["event_id"])
            yield event

            if self._is_terminal_event(event):
                return

        while True:
            stream_events = await self.redis.xread(
                streams={self._events_key(run_id): last_event_id},
                count=20,
                block=1000,
            )

            if not stream_events:
                if await self._is_terminal(run_id):
                    return
                continue

            for _stream_name, messages in stream_events:
                for event_id, fields in messages:
                    event = self._decode_stream_event(str(event_id), fields)
                    last_event_id = str(event["event_id"])
                    yield event

                    if self._is_terminal_event(event):
                        return

            if await self._is_terminal(run_id):
                return

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

    async def get_snapshot(
        self,
        run_id: str,
        until_event_id: int | str | None = None,
    ) -> dict[str, Any] | None:
        await self.initialize()
        if not await self.redis.exists(self._meta_key(run_id)):
            return None

        await self._fail_orphaned_run(run_id)

        meta = await self.redis.hgetall(self._meta_key(run_id))
        events = [event async for event in self._load_events_after(run_id, 0)]
        if until_event_id in {0, "0", INITIAL_STREAM_ID}:
            events = []
        elif until_event_id is not None:
            events = [
                event
                for event in events
                if self._stream_id_at_or_before(str(event["event_id"]), until_event_id)
            ]
        assistant_content = "".join(
            str(event.get("data", ""))
            for event in events
            if event.get("type") == "content"
        )
        last_event = events[-1] if events else None
        last_event_id = str(last_event["event_id"]) if last_event else INITIAL_STREAM_ID
        status = self._snapshot_status(meta.get("status", "failed"), last_event)

        return {
            "run_id": run_id,
            "event_id": last_event_id,
            "type": "snapshot",
            "session_id": meta.get("session_id", ""),
            "question": meta.get("question", ""),
            "status": status,
            "last_event_id": last_event_id,
            "assistant_content": assistant_content,
            "error_message": self._snapshot_error_message(last_event),
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
        payload = {"run_id": run_id, **event}
        encoded = json.dumps(payload, ensure_ascii=False)
        await self._ensure_stream_events_key(run_id)
        event_id = await self.redis.xadd(self._events_key(run_id), {"payload": encoded})
        payload["event_id"] = str(event_id)
        mapping: dict[str, str] = {"updated_at": self._now()}
        mapping["last_event_id"] = str(event_id)
        if status is not None:
            mapping["status"] = status
        await self.redis.hset(self._meta_key(run_id), mapping=mapping)

        if status in {"completed", "failed", "cancelled"} and self.terminal_ttl_seconds > 0:
            await self.redis.expire(self._meta_key(run_id), self.terminal_ttl_seconds)
            await self.redis.expire(self._events_key(run_id), self.terminal_ttl_seconds)

        return payload

    async def _load_events_after(
        self,
        run_id: str,
        from_event_id: int | str,
    ) -> AsyncIterator[dict[str, Any]]:
        entries = await self.redis.xrange(self._events_key(run_id), min="-", max="+")
        for event_id, fields in entries:
            event = self._decode_stream_event(str(event_id), fields)
            if self._stream_id_after(str(event["event_id"]), from_event_id):
                yield event

    async def _fail_orphaned_run(
        self,
        run_id: str,
        meta: dict[str, str] | None = None,
    ) -> None:
        status = meta.get("status") if meta is not None else await self._get_status(run_id)
        if status != "running":
            return

        task = self._tasks.get(run_id)
        if task is not None and meta is None:
            meta = await self.redis.hgetall(self._meta_key(run_id))

        if task is not None and not self._is_running_timeout(meta):
            return

        task = self._tasks.pop(run_id, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        await self._append_event(
            run_id,
            {
                "type": "error",
                "data": ORPHANED_RUN_ERROR,
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
        from_event_id: str,
        event_type: str,
        message: str,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "event_id": from_event_id,
            "type": event_type,
            "data": message,
        }

    def _meta_key(self, run_id: str) -> str:
        return f"rag:stream:{run_id}:meta"

    def _events_key(self, run_id: str) -> str:
        return f"rag:stream:{run_id}:events"

    def _now(self) -> str:
        return str(self._now_seconds())

    def _now_seconds(self) -> float:
        return time.time()

    def _is_running_timeout(self, meta: dict[str, str] | None) -> bool:
        if self.running_timeout_seconds <= 0:
            return False
        if not meta:
            return False

        timestamp = meta.get("updated_at") or meta.get("created_at")
        if not timestamp:
            return True

        try:
            last_active_at = float(timestamp)
        except ValueError:
            return True

        return self._now_seconds() - last_active_at >= self.running_timeout_seconds

    def _run_id_from_meta_key(self, meta_key: str) -> str:
        prefix = "rag:stream:"
        suffix = ":meta"
        if not meta_key.startswith(prefix) or not meta_key.endswith(suffix):
            return ""

        return meta_key[len(prefix) : -len(suffix)]

    async def _ensure_stream_events_key(self, run_id: str) -> None:
        events_key = self._events_key(run_id)
        key_type = await self.redis.type(events_key)
        if isinstance(key_type, bytes):
            key_type = key_type.decode()

        if key_type in {"none", "stream"}:
            return

        logger.warning(
            "清理不兼容的 RAG 流事件键：run_id={} key={} type={}",
            run_id,
            events_key,
            key_type,
        )
        await self.redis.delete(events_key)

    def _decode_stream_event(
        self,
        event_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        payload = json.loads(fields.get("payload", "{}"))
        payload["event_id"] = event_id
        return payload

    def _snapshot_status(
        self,
        meta_status: str,
        last_event: dict[str, Any] | None,
    ) -> str:
        if last_event is None:
            return meta_status if meta_status == "running" else "running"

        event_type = last_event.get("type")
        if event_type == "complete":
            return "completed"
        if event_type == "error":
            return "failed"
        if event_type == "cancelled":
            return "cancelled"

        return "running"

    def _snapshot_error_message(self, last_event: dict[str, Any] | None) -> str:
        if last_event is None or last_event.get("type") != "error":
            return ""

        return str(last_event.get("data") or last_event.get("message") or "")

    def _stream_id_after(self, event_id: str, from_event_id: int | str) -> bool:
        if from_event_id in {0, "0", INITIAL_STREAM_ID}:
            return True

        current_id = self._stream_id_parts(event_id)
        offset_id = self._stream_id_parts(str(from_event_id))
        return current_id > offset_id

    def _stream_id_at_or_before(self, event_id: str, until_event_id: int | str) -> bool:
        current_id = self._stream_id_parts(event_id)
        offset_id = self._stream_id_parts(str(until_event_id))
        return current_id <= offset_id

    def _stream_id_parts(self, event_id: str) -> tuple[int, int]:
        milliseconds, sequence = event_id.split("-", 1)
        return int(milliseconds), int(sequence)


rag_stream_run_service = RagStreamRunService(
    config.redis_url,
    terminal_ttl_seconds=config.rag_stream_terminal_ttl_seconds,
    running_timeout_seconds=config.rag_stream_running_timeout_seconds,
)
