import operator
from types import SimpleNamespace
from typing import Annotated, get_args, get_origin
import unittest
from unittest.mock import AsyncMock, patch

from app.agent.aiops.executor import executor
from app.agent.aiops.state import PlanExecuteState
from app.services.aiops_service import _events_from_stream_payload


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
            patch("app.agent.aiops.executor.get_mcp_client_with_retry", new=AsyncMock()),
            patch(
                "app.agent.aiops.executor.load_mcp_tools_safe",
                new=AsyncMock(return_value=([], None)),
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


if __name__ == "__main__":
    unittest.main()
