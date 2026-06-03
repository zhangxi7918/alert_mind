from langchain_core.documents import Document
from loguru import logger

from app.config import config
from app.services.vector_store_manager import VectorStoreManager, vector_store_manager


class VectorSearchService:
    def __init__(self, store_manager: VectorStoreManager) -> None:
        self.store_manager = store_manager

    def search(self, query: str) -> list[Document]:
        results = self.store_manager.similarity_search(
            query,
            k=config.rag_top_k,
            score_threshold=config.rag_score_threshold,
        )
        if not results:
            logger.warning("知识库检索无相关结果（threshold={:.2f}）：{}", config.rag_score_threshold, query)
        return results


vector_search_service = VectorSearchService(vector_store_manager)
