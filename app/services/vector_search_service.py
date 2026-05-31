from langchain_core.documents import Document

from app.config import config
from app.services.vector_store_manager import VectorStoreManager, vector_store_manager


class VectorSearchService:
    def __init__(self, store_manager: VectorStoreManager) -> None:
        self.store_manager = store_manager

    def search(self, query: str) -> list[Document]:
        return self.store_manager.similarity_search(query, k=config.rag_top_k)


vector_search_service = VectorSearchService(vector_store_manager)
