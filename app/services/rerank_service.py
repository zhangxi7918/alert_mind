import httpx
from langchain_core.documents import Document
from loguru import logger

from app.config import get_dashscope_api_key

DASHSCOPE_RERANK_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"


class RerankService:
    def rerank(self, query: str, documents: list[Document], top_n: int, model: str, min_score: float = 0.0) -> list[Document]:
        if not documents:
            return []

        api_key = get_dashscope_api_key()
        texts = [doc.page_content for doc in documents]

        response = httpx.post(
            DASHSCOPE_RERANK_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "input": {"query": query, "documents": texts},
                "parameters": {"top_n": top_n, "return_documents": False},
            },
            timeout=30,
        )

        if response.status_code != 200:
            logger.warning("Rerank API 返回错误 {}，降级为原始顺序：{}", response.status_code, response.text[:200])
            return documents[:top_n]

        results = response.json()["output"]["results"]
        # results 已按 relevance_score 降序排列，index 指向原始 documents 的位置
        reranked = [documents[r["index"]] for r in results if r["relevance_score"] >= min_score]
        logger.debug("Rerank 完成：{} 条 → {} 条（min_score={:.2f}）", len(documents), len(reranked), min_score)
        return reranked


rerank_service = RerankService()
