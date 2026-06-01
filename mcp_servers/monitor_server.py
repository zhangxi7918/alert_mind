from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP


mcp = FastMCP("monitor-server")


_METRIC_BASELINES: dict[str, dict[str, float]] = {
    "checkout-service": {
        "cpu_usage": 82.4,
        "memory_usage": 76.8,
        "error_rate": 4.2,
        "latency_p95": 1280.0,
    },
    "payment-service": {
        "cpu_usage": 68.7,
        "memory_usage": 71.3,
        "error_rate": 2.1,
        "latency_p95": 860.0,
    },
    "order-service": {
        "cpu_usage": 54.6,
        "memory_usage": 62.9,
        "error_rate": 1.3,
        "latency_p95": 430.0,
    },
}

_ALERTS: dict[str, list[dict[str, str]]] = {
    "checkout-service": [
        {
            "name": "CPUHighUsage",
            "severity": "critical",
            "time": "2026-06-01T20:03:00+08:00",
            "summary": "checkout-service CPU usage exceeded 80% for 10 minutes.",
        },
        {
            "name": "LatencyP95High",
            "severity": "warning",
            "time": "2026-06-01T20:08:00+08:00",
            "summary": "checkout-service p95 latency is above 1s.",
        },
    ],
    "payment-service": [
        {
            "name": "ErrorRateSpike",
            "severity": "warning",
            "time": "2026-06-01T19:54:00+08:00",
            "summary": "payment-service error rate increased in the last 15 minutes.",
        }
    ],
}


def _metric_unit(metric_name: str) -> str:
    if "latency" in metric_name:
        return "ms"
    if "rate" in metric_name or "usage" in metric_name:
        return "%"
    return "count"


@mcp.tool()
def query_metrics(
    service: str,
    metric_name: str,
    time_range: str,
) -> list[dict[str, Any]]:
    """查询指定服务在一段时间内的模拟监控指标数据，用于辅助 LLM 判断服务健康状态。"""
    baseline = _METRIC_BASELINES.get(service, {}).get(metric_name, 50.0)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    unit = _metric_unit(metric_name)

    return [
        {
            "service": service,
            "metric": metric_name,
            "value": round(baseline + offset, 2),
            "unit": unit,
            "timestamp": (now - timedelta(minutes=5 * index)).isoformat(),
            "time_range": time_range,
        }
        for index, offset in enumerate([0.0, -1.7, 2.4, 1.1, -0.9])
    ]


@mcp.tool()
def query_alerts(service: str) -> list[dict[str, str]]:
    """查询指定服务的模拟告警列表，返回告警名称、严重程度、发生时间和摘要。"""
    alerts = _ALERTS.get(service)
    if alerts is None:
        return [
            {
                "service": service,
                "name": "NoActiveAlerts",
                "severity": "info",
                "time": "2026-06-01T20:00:00+08:00",
                "summary": f"No active alerts found for {service}.",
            }
        ]

    return [{"service": service, **alert} for alert in alerts]


if __name__ == "__main__":
    mcp.run(transport="streamable-http", port=8004)
