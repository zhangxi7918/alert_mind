from hashlib import sha256
import unittest

from langchain_core.documents import Document

from app.services.vector_index_service import VectorIndexService


class FakeVectorStoreManager:
    def __init__(self, existing_ids: set[str] | None = None) -> None:
        self.existing_ids = existing_ids or set()
        self.added_docs: list[Document] = []
        self.added_ids: list[str] = []

    def get_existing_ids(self, ids: list[str]) -> set[str]:
        return self.existing_ids.intersection(ids)

    def add_documents(self, docs: list[Document], ids: list[str] | None = None) -> list[str]:
        self.added_docs = docs
        self.added_ids = ids or []

        return self.added_ids


class VectorIndexServiceTest(unittest.TestCase):
    def test_index_documents_skips_duplicate_and_existing_chunks(self) -> None:
        existing_content = "already indexed"
        existing_hash = sha256(existing_content.encode("utf-8")).hexdigest()
        store_manager = FakeVectorStoreManager(existing_ids={existing_hash})
        service = VectorIndexService(store_manager)  # type: ignore[arg-type]
        docs = [
            Document(page_content="new chunk"),
            Document(page_content="new chunk"),
            Document(page_content=existing_content),
            Document(page_content="another new chunk"),
        ]

        result = service.index_documents(docs)

        self.assertEqual(result.chunks_count, 4)
        self.assertEqual(result.inserted_count, 2)
        self.assertEqual(result.skipped_count, 2)
        self.assertEqual(len(store_manager.added_docs), 2)
        self.assertEqual(store_manager.added_ids[0], docs[0].metadata["content_hash"])
        self.assertEqual(store_manager.added_ids[1], docs[3].metadata["content_hash"])
        self.assertEqual(docs[0].metadata["chunk_index"], 0)
        self.assertEqual(docs[1].metadata["chunk_index"], 1)


if __name__ == "__main__":
    unittest.main()
