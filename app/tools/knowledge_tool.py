from langchain.tools import tool

from app.services.vector_search_service import vector_search_service


@tool
def retrieve_knowledge(query: str) -> str:
    """从知识库中检索与查询相关的文档内容。"""
    documents = vector_search_service.search(query)
    return "\n".join(document.page_content for document in documents)
