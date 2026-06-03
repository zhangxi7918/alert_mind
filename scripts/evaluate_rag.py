"""
离线评测当前 RAG 检索配置的 source-level 命中效果。

用法：
    uv run python scripts/evaluate_rag.py
    uv run python scripts/evaluate_rag.py --dataset eval/rag_golden.jsonl --json
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import config
from app.services.rag_evaluation import (  # noqa: E402
    RagEvalResult,
    evaluate_case,
    extract_document_sources,
    load_golden_dataset,
    summarize_results,
)
from app.services.vector_search_service import vector_search_service  # noqa: E402
from app.services.vector_store_manager import vector_store_manager  # noqa: E402

DEFAULT_DATASET_PATH = Path("eval/rag_golden.jsonl")


def main() -> None:
    args = _parse_args()
    dataset_path = Path(args.dataset)
    cases = load_golden_dataset(dataset_path)

    vector_store_manager.initialize()
    try:
        results = [
            evaluate_case(golden_case, _search_sources(golden_case.query))
            for golden_case in cases
        ]
    finally:
        vector_store_manager.close()

    summary = summarize_results(results)
    if args.json:
        print(
            json.dumps(
                {
                    "summary": asdict(summary),
                    "results": [asdict(result) for result in results],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    _print_report(dataset_path, results)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评测当前 RAG 检索命中效果")
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help="golden dataset JSONL 路径，默认 eval/rag_golden.jsonl",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON，便于脚本消费",
    )
    return parser.parse_args()


def _search_sources(query: str) -> list[str]:
    documents = vector_search_service.search(query)
    return extract_document_sources(documents)


def _print_report(dataset_path: Path, results: list[RagEvalResult]) -> None:
    summary = summarize_results(results)

    print("\nRAG 检索评测")
    print("=" * 72)
    print(f"dataset: {dataset_path}")
    print(f"rag_top_k: {config.rag_top_k}")
    print(f"rag_score_threshold: {config.rag_score_threshold}")
    print(f"rag_rerank_enabled: {config.rag_rerank_enabled}")
    print("-" * 72)

    for result in results:
        status = "PASS" if result.passed else "FAIL"
        expected = ", ".join(result.expected_sources) or "(negative)"
        retrieved = ", ".join(result.retrieved_sources) or "(无结果)"
        print(f"[{status}] {result.id} ({result.category})")
        print(f"  query: {result.query}")
        print(f"  expected: {expected}")
        print(f"  retrieved: {retrieved}")
        print(
            "  metrics: "
            f"hit={int(result.hit)} "
            f"recall={_format_percent(result.recall)} "
            f"precision={_format_percent(result.precision)}"
        )
        if result.failure_reason:
            print(f"  reason: {result.failure_reason}")

    print("-" * 72)
    print(f"total_cases: {summary.total_cases}")
    print(f"positive_cases: {summary.positive_cases}")
    print(f"negative_cases: {summary.negative_cases}")
    print(f"passed_cases: {summary.passed_cases}")
    print(f"overall_pass_rate: {_format_percent(summary.overall_pass_rate)}")
    print(f"accuracy@k(hit@k): {_format_percent(summary.accuracy_at_k)}")
    print(f"average_recall@k: {_format_percent(summary.average_recall_at_k)}")
    print(f"average_precision@k: {_format_percent(summary.average_precision_at_k)}")
    print(f"negative_pass_rate: {_format_percent(summary.negative_pass_rate)}")

    failed_results = [result for result in results if not result.passed]
    if not failed_results:
        return

    print("\n失败样例")
    print("-" * 72)
    for result in failed_results:
        print(f"- {result.id}: {result.failure_reason}")


def _format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


if __name__ == "__main__":
    main()
