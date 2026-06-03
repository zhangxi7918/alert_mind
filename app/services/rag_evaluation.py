from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RagGoldenCase:
    id: str
    query: str
    expected_sources: list[str]
    category: str


@dataclass(frozen=True)
class RagEvalResult:
    id: str
    query: str
    category: str
    expected_sources: list[str]
    retrieved_sources: list[str]
    hit: bool
    recall: float
    precision: float
    passed: bool
    failure_reason: str


@dataclass(frozen=True)
class RagEvalSummary:
    total_cases: int
    positive_cases: int
    negative_cases: int
    passed_cases: int
    overall_pass_rate: float
    accuracy_at_k: float
    average_recall_at_k: float
    average_precision_at_k: float
    negative_pass_rate: float


def load_golden_dataset(dataset_path: Path) -> list[RagGoldenCase]:
    cases: list[RagGoldenCase] = []

    with dataset_path.open(encoding="utf-8") as dataset_file:
        for line_no, raw_line in enumerate(dataset_file, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{dataset_path}:{line_no} 不是合法 JSON：{exc.msg}"
                ) from exc

            cases.append(_parse_golden_case(payload, dataset_path, line_no))

    if not cases:
        raise ValueError(f"{dataset_path} 未包含任何评测样本")

    return cases


def extract_document_sources(documents: list[Any]) -> list[str]:
    sources: list[str] = []
    for document in documents:
        metadata = getattr(document, "metadata", {}) or {}
        source = metadata.get("_file_name")
        if source:
            sources.append(str(source))

    return sources


def evaluate_case(
    golden_case: RagGoldenCase,
    retrieved_sources: list[str],
) -> RagEvalResult:
    expected_sources = set(golden_case.expected_sources)

    if not expected_sources:
        passed = len(retrieved_sources) == 0
        failure_reason = ""
        if not passed:
            failure_reason = "无关查询不应返回结果，实际返回：" + ", ".join(retrieved_sources)

        return RagEvalResult(
            id=golden_case.id,
            query=golden_case.query,
            category=golden_case.category,
            expected_sources=golden_case.expected_sources,
            retrieved_sources=retrieved_sources,
            hit=passed,
            recall=1.0 if passed else 0.0,
            precision=1.0 if passed else 0.0,
            passed=passed,
            failure_reason=failure_reason,
        )

    matched_sources = expected_sources.intersection(retrieved_sources)
    hit = bool(matched_sources)
    recall = len(matched_sources) / len(expected_sources)
    precision = _calculate_precision(retrieved_sources, expected_sources)
    failure_reason = ""

    if not hit:
        expected_text = ", ".join(golden_case.expected_sources)
        retrieved_text = ", ".join(retrieved_sources) or "(无结果)"
        failure_reason = f"未命中期望来源：expected={expected_text}; retrieved={retrieved_text}"

    return RagEvalResult(
        id=golden_case.id,
        query=golden_case.query,
        category=golden_case.category,
        expected_sources=golden_case.expected_sources,
        retrieved_sources=retrieved_sources,
        hit=hit,
        recall=recall,
        precision=precision,
        passed=hit,
        failure_reason=failure_reason,
    )


def summarize_results(results: list[RagEvalResult]) -> RagEvalSummary:
    positive_results = [result for result in results if result.expected_sources]
    negative_results = [result for result in results if not result.expected_sources]

    return RagEvalSummary(
        total_cases=len(results),
        positive_cases=len(positive_results),
        negative_cases=len(negative_results),
        passed_cases=sum(1 for result in results if result.passed),
        overall_pass_rate=_safe_average([1.0 if result.passed else 0.0 for result in results]),
        accuracy_at_k=_safe_average([1.0 if result.hit else 0.0 for result in positive_results]),
        average_recall_at_k=_safe_average([result.recall for result in positive_results]),
        average_precision_at_k=_safe_average([result.precision for result in positive_results]),
        negative_pass_rate=_safe_average(
            [1.0 if result.passed else 0.0 for result in negative_results]
        ),
    )


def _parse_golden_case(
    payload: object,
    dataset_path: Path,
    line_no: int,
) -> RagGoldenCase:
    if not isinstance(payload, dict):
        raise ValueError(f"{dataset_path}:{line_no} 每行必须是 JSON object")

    required_fields = {"id", "query", "expected_sources", "category"}
    missing_fields = sorted(required_fields.difference(payload))
    if missing_fields:
        raise ValueError(f"{dataset_path}:{line_no} 缺少字段：{', '.join(missing_fields)}")

    case_id = payload["id"]
    query = payload["query"]
    expected_sources = payload["expected_sources"]
    category = payload["category"]

    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError(f"{dataset_path}:{line_no} 字段 id 必须是非空字符串")
    if not isinstance(query, str) or not query.strip():
        raise ValueError(f"{dataset_path}:{line_no} 字段 query 必须是非空字符串")
    if not isinstance(category, str) or not category.strip():
        raise ValueError(f"{dataset_path}:{line_no} 字段 category 必须是非空字符串")
    if not isinstance(expected_sources, list) or not all(
        isinstance(source, str) and source.strip() for source in expected_sources
    ):
        raise ValueError(
            f"{dataset_path}:{line_no} 字段 expected_sources 必须是字符串数组"
        )

    return RagGoldenCase(
        id=case_id,
        query=query,
        expected_sources=expected_sources,
        category=category,
    )


def _calculate_precision(
    retrieved_sources: list[str],
    expected_sources: set[str],
) -> float:
    if not retrieved_sources:
        return 0.0

    matched_count = sum(1 for source in retrieved_sources if source in expected_sources)
    return matched_count / len(retrieved_sources)


def _safe_average(values: list[float]) -> float:
    if not values:
        return 0.0

    return sum(values) / len(values)
