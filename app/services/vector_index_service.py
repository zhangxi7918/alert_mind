from langchain_core.documents import Document

from app.services.vector_store_manager import VectorStoreManager, vector_store_manager


class VectorIndexService:
    def __init__(self, store_manager: VectorStoreManager) -> None:
        self.store_manager = store_manager

    def index_documents(self, docs: list[Document]) -> int:
        inserted_ids = self.store_manager.add_documents(docs)

        return len(inserted_ids)


vector_index_service = VectorIndexService(vector_store_manager)
