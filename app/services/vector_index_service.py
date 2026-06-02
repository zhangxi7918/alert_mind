from dataclasses import dataclass
from hashlib import sha256

from langchain_core.documents import Document

from app.services.vector_store_manager import VectorStoreManager, vector_store_manager


@dataclass(frozen=True)
class VectorIndexResult:
    chunks_count: int
    inserted_count: int
    skipped_count: int


class VectorIndexService:
    def __init__(self, store_manager: VectorStoreManager) -> None:
        self.store_manager = store_manager

    def index_documents(self, docs: list[Document]) -> VectorIndexResult:
        unique_docs: list[Document] = []
        unique_ids: list[str] = []
        seen_hashes: set[str] = set()

        for chunk_index, document in enumerate(docs):
            content_hash = sha256(document.page_content.encode("utf-8")).hexdigest()
            document.metadata = dict(document.metadata)
            document.metadata["chunk_index"] = chunk_index
            document.metadata["content_hash"] = content_hash

            if content_hash in seen_hashes:
                continue

            seen_hashes.add(content_hash)
            unique_docs.append(document)
            unique_ids.append(content_hash)

        existing_ids = self.store_manager.get_existing_ids(unique_ids)
        new_docs: list[Document] = []
        new_ids: list[str] = []

        for document, document_id in zip(unique_docs, unique_ids, strict=True):
            if document_id in existing_ids:
                continue

            new_docs.append(document)
            new_ids.append(document_id)

        inserted_ids = self.store_manager.add_documents(new_docs, ids=new_ids)

        return VectorIndexResult(
            chunks_count=len(docs),
            inserted_count=len(inserted_ids),
            skipped_count=len(docs) - len(inserted_ids),
        )


vector_index_service = VectorIndexService(vector_store_manager)
