from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastmcp import FastMCP


mcp = FastMCP("monitor-server")

PROMETHEUS_BASE_URL = os.getenv("PROMETHEUS_BASE_URL", "http://localhost:9090")

# PromQL 表达式映射
_PROMQL = {
    "cpu_usage": '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)',
    "memory_usage": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100",
    "disk_usage": '(1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})) * 100',
}

# ---- 模拟数据工具（向后兼容，演示微服务告警场景） ----

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
def query_metrics(service: str, metric_name: str, time_range: str) -> list[dict[str, Any]]:
    """查询指定微服务在一段时间内的模拟监控指标数据，用于辅助 LLM 判断服务健康状态。"""
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
    """查询指定微服务的模拟告警列表，返回告警名称、严重程度、发生时间和摘要。"""
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


# ---- 真实 Prometheus 查询工具 ----

@mcp.tool()
def query_active_alerts(severity: str = "") -> list[dict[str, Any]]:
    """查询 Prometheus 当前正在触发的真实告警。

    Args:
        severity: 按严重程度过滤，可选值：critical / warning / info。留空返回全部。

    Returns:
        当前 firing 或 pending 状态的告警列表，每条包含名称、状态、严重程度、触发时间和描述。
    """
    try:
        resp = httpx.get(f"{PROMETHEUS_BASE_URL}/api/v1/alerts", timeout=5)
        resp.raise_for_status()
        alerts = resp.json()["data"]["alerts"]
    except Exception as e:
        return [{"error": f"无法连接 Prometheus：{e}"}]

    results = []
    for alert in alerts:
        state = alert.get("state", "")
        if state not in ("firing", "pending"):
            continue
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        alert_severity = labels.get("severity", "")
        if severity and alert_severity != severity:
            continue
        results.append({
            "name": labels.get("alertname", ""),
            "state": state,
            "severity": alert_severity,
            "active_since": alert.get("activeAt", ""),
            "summary": annotations.get("summary", ""),
            "description": annotations.get("description", ""),
            "labels": labels,
        })

    if not results:
        return [{"message": "当前无活跃告警，系统运行正常。"}]
    return results


@mcp.tool()
def query_metric_history(
    metric: str,
    duration_minutes: int = 60,
    step_seconds: int = 60,
) -> dict[str, Any]:
    """查询 Prometheus 中过去一段时间的真实系统指标历史数据。

    Args:
        metric: 指标名称，可选：cpu_usage / memory_usage / disk_usage
        duration_minutes: 查询时长（分钟），默认 60 分钟
        step_seconds: 采样间隔（秒），默认 60 秒

    Returns:
        包含指标名称、单位、时间范围和数据点列表的字典。
    """
    expr = _PROMQL.get(metric)
    if not expr:
        return {"error": f"不支持的指标：{metric}，可选：{list(_PROMQL.keys())}"}

    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=duration_minutes)).isoformat()
    end = now.isoformat()

    try:
        resp = httpx.get(
            f"{PROMETHEUS_BASE_URL}/api/v1/query_range",
            params={"query": expr, "start": start, "end": end, "step": step_seconds},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
    except Exception as e:
        return {"error": f"查询失败：{e}"}

    results = data.get("result", [])
    if not results:
        return {"error": "Prometheus 无数据，请确认 node_exporter 正在运行。"}

    values = results[0].get("values", [])
    points = [
        {
            "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M"),
            "value": round(float(val), 1),
        }
        for ts, val in values
    ]

    # 统计摘要
    nums = [p["value"] for p in points]
    summary = {
        "metric": metric,
        "unit": "%",
        "duration_minutes": duration_minutes,
        "data_points": len(points),
        "current": nums[-1] if nums else None,
        "max": max(nums) if nums else None,
        "avg": round(sum(nums) / len(nums), 1) if nums else None,
        "history": points,
    }
    return summary


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8004)
