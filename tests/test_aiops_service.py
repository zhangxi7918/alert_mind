import asyncio
import operator
from types import SimpleNamespace
from typing import Annotated, get_args, get_origin
import unittest
from unittest.mock import AsyncMock, patch

from app.agent.aiops.executor import executor
from app.agent.aiops.state import PlanExecuteState
from app.agent.aiops.tool_loader import AIOpsToolLoadError, load_aiops_tools
from app.services.aiops_service import AIOpsService, _events_from_stream_payload


class FakeAIOpsStreamApp:
    def __init__(self) -> None:
        self.astream_calls = []

    async def astream(self, initial_state, *, config, stream_mode):
        self.astream_calls.append(
            {
                "initial_state": initial_state,
                "config": config,
                "stream_mode": stream_mode,
            }
        )
        yield "updates", {}


class FakeAIOpsInvokeApp:
    def __init__(self) -> None:
        self.ainvoke_calls = []

    async def ainvoke(self, initial_state, *, config):
        self.ainvoke_calls.append(
            {
                "initial_state": initial_state,
                "config": config,
            }
        )
        return {
            "input": initial_state["input"],
            "plan": [],
            "past_steps": [],
            "response": "完成",
        }


class CloseTrackingAIOpsStream:
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


class CancellingAIOpsStream(CloseTrackingAIOpsStream):
    async def __anext__(self):
        raise asyncio.CancelledError


class FakeCloseTrackingAIOpsApp:
    def __init__(self, stream: CloseTrackingAIOpsStream) -> None:
        self.stream = stream

    def astream(self, initial_state, *, config, stream_mode):
        return self.stream


class AIOpsEventConversionTest(unittest.TestCase):
    def test_custom_status_event_gets_running_stage(self) -> None:
        events = _events_from_stream_payload(
            "custom",
            {"type": "status", "message": "正在准备工具链"},
        )

        self.assertEqual(
            events,
            [
                {
                    "type": "status",
                    "stage": "running",
                    "message": "正在准备工具链",
                }
            ],
        )

    def test_planner_update_creates_plan_event(self) -> None:
        events = _events_from_stream_payload(
            "updates",
            {"planner": {"plan": ["查告警", "查指标"]}},
        )

        self.assertEqual(events[0]["type"], "plan")
        self.assertEqual(events[0]["stage"], "plan_created")
        self.assertEqual(events[0]["steps"], ["查告警", "查指标"])

    def test_executor_update_creates_current_step_event(self) -> None:
        events = _events_from_stream_payload(
            "updates",
            {
                "executor": {
                    "past_steps": [("查指标", "延迟稳定在 50ms")],
                    "plan": ["生成报告"],
                }
            },
        )

        self.assertEqual(events[0]["type"], "step_complete")
        self.assertEqual(events[0]["stage"], "step_executed")
        self.assertEqual(events[0]["current_step"], "查指标")
        self.assertEqual(events[0]["result"], "延迟稳定在 50ms")
        self.assertEqual(events[0]["remaining_steps"], 1)

    def test_replanner_plan_creates_plan_update_event(self) -> None:
        events = _events_from_stream_payload(
            "updates",
            {"replanner": {"plan": ["补充日志检查"]}},
        )

        self.assertEqual(events[0]["type"], "plan_update")
        self.assertEqual(events[0]["stage"], "plan_updated")
        self.assertEqual(events[0]["steps"], ["补充日志检查"])

    def test_replanner_response_creates_report_event(self) -> None:
        events = _events_from_stream_payload(
            "updates",
            {"replanner": {"response": "## 诊断报告"}},
        )

        self.assertEqual(events[0]["type"], "report")
        self.assertEqual(events[0]["stage"], "final_report")
        self.assertEqual(events[0]["report"], "## 诊断报告")


class AIOpsTraceConfigTest(unittest.IsolatedAsyncioTestCase):
    def _expected_trace_config(self) -> dict:
        return {
            "configurable": {"thread_id": "request-123"},
            "run_name": "aiops_diagnosis",
            "tags": ["alert-mind", "aiops", "plan-execute-replan"],
            "metadata": {
                "request_id": "request-123",
                "entrypoint": "aiops",
            },
        }

    async def test_run_stream_passes_langsmith_trace_config(self) -> None:
        service = AIOpsService()
        fake_app = FakeAIOpsStreamApp()
        service.app = fake_app

        with patch("app.services.aiops_service.uuid4", return_value="request-123"):
            events = [event async for event in service.run_stream("诊断服务")]

        self.assertEqual(events[-1]["type"], "complete")
        self.assertEqual(fake_app.astream_calls[0]["initial_state"]["input"], "诊断服务")
        self.assertEqual(
            fake_app.astream_calls[0]["stream_mode"],
            ["custom", "updates"],
        )
        self.assertEqual(fake_app.astream_calls[0]["config"], self._expected_trace_config())

    async def test_run_stream_closes_upstream_when_consumer_stops_early(self) -> None:
        stream = CloseTrackingAIOpsStream(
            [("custom", {"type": "status", "message": "正在准备工具链"})]
        )
        service = AIOpsService()
        service.app = FakeCloseTrackingAIOpsApp(stream)

        generator = service.run_stream("诊断服务")
        try:
            event = await anext(generator)
        finally:
            await generator.aclose()

        self.assertEqual(event["type"], "status")
        self.assertTrue(stream.closed)

    async def test_run_stream_re_raises_cancellation_and_closes_upstream(self) -> None:
        stream = CancellingAIOpsStream([])
        service = AIOpsService()
        service.app = FakeCloseTrackingAIOpsApp(stream)

        with self.assertRaises(asyncio.CancelledError):
            async for _event in service.run_stream("诊断服务"):
                pass

        self.assertTrue(stream.closed)

    async def test_run_passes_langsmith_trace_config(self) -> None:
        service = AIOpsService()
        fake_app = FakeAIOpsInvokeApp()
        service.app = fake_app

        with patch("app.services.aiops_service.uuid4", return_value="request-123"):
            result = await service.run("诊断服务")

        self.assertEqual(result["response"], "完成")
        self.assertEqual(fake_app.ainvoke_calls[0]["initial_state"]["input"], "诊断服务")
        self.assertEqual(fake_app.ainvoke_calls[0]["config"], self._expected_trace_config())


class AIOpsStateAndExecutorTest(unittest.IsolatedAsyncioTestCase):
    def test_past_steps_uses_langgraph_add_reducer(self) -> None:
        annotation = PlanExecuteState.__annotations__["past_steps"]

        self.assertEqual(get_origin(annotation), Annotated)
        self.assertIs(get_args(annotation)[1], operator.add)

    async def test_executor_returns_only_current_step_result(self) -> None:
        fake_agent = AsyncMock()
        fake_agent.ainvoke.return_value = {
            "messages": [SimpleNamespace(content="当前没有活跃告警")]
        }

        with (
            patch("app.agent.aiops.executor.emit_status"),
            patch("app.agent.aiops.executor.get_dashscope_api_key", return_value="test-key"),
            patch("app.agent.aiops.executor.ChatQwen"),
            patch(
                "app.agent.aiops.executor.load_aiops_tools",
                new=AsyncMock(
                    return_value=[
                        SimpleNamespace(name="retrieve_knowledge"),
                        SimpleNamespace(name="query_active_alerts"),
                        SimpleNamespace(name="query_metric_history"),
                    ]
                ),
            ),
            patch("app.agent.aiops.executor.create_react_agent", return_value=fake_agent),
        ):
            result = await executor(
                {
                    "input": "诊断服务",
                    "plan": ["查告警", "生成报告"],
                    "past_steps": [("旧步骤", "旧结果")],
                    "response": "",
                }
            )

        self.assertEqual(result["plan"], ["生成报告"])
        self.assertEqual(result["past_steps"], [("查告警", "当前没有活跃告警")])


class AIOpsToolLoaderTest(unittest.IsolatedAsyncioTestCase):
    async def test_load_aiops_tools_raises_when_mcp_load_fails(self) -> None:
        with (
            patch("app.agent.aiops.tool_loader.get_mcp_client_with_retry", new=AsyncMock()),
            patch(
                "app.agent.aiops.tool_loader.load_mcp_tools_safe",
                new=AsyncMock(return_value=([], "ConnectError: All connection attempts failed")),
            ),
        ):
            with self.assertRaises(AIOpsToolLoadError) as ctx:
                await load_aiops_tools("planner")

        self.assertIn("监控工具服务不可用", str(ctx.exception))

    async def test_load_aiops_tools_raises_when_required_tool_is_missing(self) -> None:
        mcp_tools = [SimpleNamespace(name="query_active_alerts", description="")]

        with (
            patch("app.agent.aiops.tool_loader.get_mcp_client_with_retry", new=AsyncMock()),
            patch(
                "app.agent.aiops.tool_loader.load_mcp_tools_safe",
                new=AsyncMock(return_value=(mcp_tools, None)),
            ),
        ):
            with self.assertRaises(AIOpsToolLoadError) as ctx:
                await load_aiops_tools("executor")

        self.assertIn("query_metric_history", str(ctx.exception))

    async def test_load_aiops_tools_returns_local_and_mcp_tools(self) -> None:
        mcp_tools = [
            SimpleNamespace(name="query_active_alerts", description=""),
            SimpleNamespace(name="query_metric_history", description=""),
        ]

        with (
            patch("app.agent.aiops.tool_loader.get_mcp_client_with_retry", new=AsyncMock()),
            patch(
                "app.agent.aiops.tool_loader.load_mcp_tools_safe",
                new=AsyncMock(return_value=(mcp_tools, None)),
            ),
        ):
            tools = await load_aiops_tools("planner")

        self.assertEqual(tools[0].name, "retrieve_knowledge")
        self.assertEqual([tool.name for tool in tools[1:]], ["query_active_alerts", "query_metric_history"])


if __name__ == "__main__":
    unittest.main()
