import unittest
from unittest.mock import patch

from langchain_core.documents import Document

import app.services.vector_search_service as search_module
from app.services.vector_search_service import VectorSearchService


class FakeStoreManager:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.calls: list[dict[str, object]] = []

    def similarity_search(
        self,
        query: str,
        k: int,
        score_threshold: float | None = None,
    ) -> list[Document]:
        self.calls.append(
            {
                "query": query,
                "k": k,
                "score_threshold": score_threshold,
            }
        )
        return self.documents


class FakeRerankService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def rerank(
        self,
        query: str,
        documents: list[Document],
        top_n: int,
        model: str,
    ) -> list[Document]:
        self.calls.append(
            {
                "query": query,
                "documents": documents,
                "top_n": top_n,
                "model": model,
            }
        )
        return documents[:top_n]


class VectorSearchServiceTest(unittest.TestCase):
    def test_rerank_search_applies_score_threshold_to_candidate_recall(self) -> None:
        document = Document(page_content="CPU runbook")
        store_manager = FakeStoreManager([document])
        rerank_service = FakeRerankService()
        service = VectorSearchService(store_manager)  # type: ignore[arg-type]

        with _temporary_rag_config(
            rag_top_k=1,
            rag_rerank_top_n=20,
            rag_score_threshold=0.7,
            rag_rerank_model="test-rerank",
        ):
            with patch.object(search_module, "rerank_service", rerank_service):
                results = service._search_with_rerank("CPU 怎么排查？")

        self.assertEqual(results, [document])
        self.assertEqual(
            store_manager.calls,
            [
                {
                    "query": "CPU 怎么排查？",
                    "k": 20,
                    "score_threshold": 0.7,
                }
            ],
        )
        self.assertEqual(len(rerank_service.calls), 1)
        self.assertEqual(rerank_service.calls[0]["documents"], [document])
        self.assertEqual(rerank_service.calls[0]["top_n"], 1)
        self.assertEqual(rerank_service.calls[0]["model"], "test-rerank")

    def test_rerank_search_skips_reranker_when_threshold_filters_all_candidates(self) -> None:
        store_manager = FakeStoreManager([])
        rerank_service = FakeRerankService()
        service = VectorSearchService(store_manager)  # type: ignore[arg-type]

        with _temporary_rag_config(rag_score_threshold=0.8):
            with patch.object(search_module, "rerank_service", rerank_service):
                results = service._search_with_rerank("今天上海天气怎么样？")

        self.assertEqual(results, [])
        self.assertEqual(store_manager.calls[0]["score_threshold"], 0.8)
        self.assertEqual(rerank_service.calls, [])


class _temporary_rag_config:
    def __init__(self, **overrides: object) -> None:
        self.overrides = overrides
        self.original_values: dict[str, object] = {}

    def __enter__(self) -> None:
        for name, value in self.overrides.items():
            self.original_values[name] = getattr(search_module.config, name)
            setattr(search_module.config, name, value)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        for name, value in self.original_values.items():
            setattr(search_module.config, name, value)


if __name__ == "__main__":
    unittest.main()
