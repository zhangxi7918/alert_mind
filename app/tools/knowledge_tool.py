from langchain.tools import tool
from loguru import logger

from app.services.vector_search_service import vector_search_service


@tool
def retrieve_knowledge(query: str) -> str:
    """从知识库中检索与查询相关的文档内容。"""
    try:
        documents = vector_search_service.search(query)
    except Exception as exc:
        logger.warning("知识库检索失败，将返回降级提示：{}", exc)
        return f"知识库检索暂不可用：{type(exc).__name__}: {exc}"

    return "\n".join(document.page_content for document in documents)
