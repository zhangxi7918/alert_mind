from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from langchain_core.documents import Document

from app.services.rag_evaluation import (
    RagGoldenCase,
    evaluate_case,
    extract_document_sources,
    load_golden_dataset,
    summarize_results,
)


class RagEvaluationTest(unittest.TestCase):
    def test_positive_case_hits_any_expected_source(self) -> None:
        golden_case = RagGoldenCase(
            id="cpu_001",
            query="CPU 怎么排查？",
            expected_sources=["runbook_high_cpu.md"],
            category="cpu",
        )

        result = evaluate_case(
            golden_case,
            ["reference_alert_rules.md", "runbook_high_cpu.md"],
        )

        self.assertTrue(result.hit)
        self.assertTrue(result.passed)
        self.assertEqual(result.recall, 1.0)
        self.assertEqual(result.precision, 0.5)

    def test_recall_counts_covered_expected_sources(self) -> None:
        golden_case = RagGoldenCase(
            id="timeout_001",
            query="服务超时和连接池怎么排查？",
            expected_sources=[
                "runbook_service_timeout.md",
                "runbook_db_connection_pool.md",
            ],
            category="service_timeout",
        )

        result = evaluate_case(golden_case, ["runbook_service_timeout.md"])

        self.assertTrue(result.hit)
        self.assertEqual(result.recall, 0.5)
        self.assertEqual(result.precision, 1.0)

    def test_negative_case_passes_only_when_no_sources_are_returned(self) -> None:
        golden_case = RagGoldenCase(
            id="negative_001",
            query="今天上海天气怎么样？",
            expected_sources=[],
            category="negative",
        )

        passed_result = evaluate_case(golden_case, [])
        failed_result = evaluate_case(golden_case, ["runbook_high_cpu.md"])

        self.assertTrue(passed_result.passed)
        self.assertFalse(failed_result.passed)
        self.assertIn("无关查询不应返回结果", failed_result.failure_reason)

    def test_summarize_results_separates_positive_and_negative_metrics(self) -> None:
        results = [
            evaluate_case(
                RagGoldenCase(
                    id="cpu_001",
                    query="CPU 怎么排查？",
                    expected_sources=["runbook_high_cpu.md"],
                    category="cpu",
                ),
                ["runbook_high_cpu.md"],
            ),
            evaluate_case(
                RagGoldenCase(
                    id="db_001",
                    query="数据库连接怎么查？",
                    expected_sources=["runbook_db_connection_pool.md"],
                    category="database",
                ),
                [],
            ),
            evaluate_case(
                RagGoldenCase(
                    id="negative_001",
                    query="写一首诗",
                    expected_sources=[],
                    category="negative",
                ),
                [],
            ),
        ]

        summary = summarize_results(results)

        self.assertEqual(summary.total_cases, 3)
        self.assertEqual(summary.positive_cases, 2)
        self.assertEqual(summary.negative_cases, 1)
        self.assertEqual(summary.passed_cases, 2)
        self.assertEqual(summary.accuracy_at_k, 0.5)
        self.assertEqual(summary.average_recall_at_k, 0.5)
        self.assertEqual(summary.average_precision_at_k, 0.5)
        self.assertEqual(summary.negative_pass_rate, 1.0)

    def test_extract_document_sources_uses_file_name_metadata(self) -> None:
        documents = [
            Document(page_content="a", metadata={"_file_name": "runbook_high_cpu.md"}),
            Document(page_content="b", metadata={}),
        ]

        self.assertEqual(extract_document_sources(documents), ["runbook_high_cpu.md"])

    def test_load_golden_dataset_rejects_missing_field(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dataset_path = Path(temp_dir) / "bad.jsonl"
            dataset_path.write_text(
                '{"id":"bad","query":"missing expected_sources","category":"cpu"}\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "缺少字段"):
                load_golden_dataset(dataset_path)

    def test_load_golden_dataset_rejects_invalid_expected_sources_type(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dataset_path = Path(temp_dir) / "bad.jsonl"
            dataset_path.write_text(
                (
                    '{"id":"bad","query":"bad sources",'
                    '"expected_sources":"runbook_high_cpu.md","category":"cpu"}\n'
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "expected_sources"):
                load_golden_dataset(dataset_path)


if __name__ == "__main__":
    unittest.main()
