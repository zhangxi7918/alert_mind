from langchain_core.documents import Document
from loguru import logger

from app.config import config
from app.services.rerank_service import rerank_service
from app.services.vector_store_manager import VectorStoreManager, vector_store_manager


class VectorSearchService:
    def __init__(self, store_manager: VectorStoreManager) -> None:
        self.store_manager = store_manager

    def search(self, query: str) -> list[Document]:
        if config.rag_rerank_enabled:
            return self._search_with_rerank(query)
        return self._search(query)

    def _search(self, query: str) -> list[Document]:
        results = self.store_manager.similarity_search(
            query,
            k=config.rag_top_k,
            score_threshold=config.rag_score_threshold,
        )
        if not results:
            logger.warning("知识库检索无相关结果（threshold={:.2f}）：{}", config.rag_score_threshold, query)
        return results

    def _search_with_rerank(self, query: str) -> list[Document]:
        # 粗召回先保留向量相关性门槛，避免 reranker 在无关候选里强行选 top-k。
        candidates = self.store_manager.similarity_search(
            query,
            k=config.rag_rerank_top_n,
            score_threshold=config.rag_score_threshold,
        )
        if not candidates:
            logger.warning("知识库粗召回无相关结果（threshold={:.2f}）：{}", config.rag_score_threshold, query)
            return []
        return rerank_service.rerank(
            query, candidates,
            top_n=config.rag_top_k,
            model=config.rag_rerank_model,
            min_score=config.rag_rerank_min_score,
        )


vector_search_service = VectorSearchService(vector_store_manager)
