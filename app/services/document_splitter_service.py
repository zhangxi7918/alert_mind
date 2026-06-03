from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from loguru import logger

from app.config import config

MIN_CHUNK_SIZE = 300
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
# H3 纳入切分，避免同一 H2 下多个子章节（如各原因分析）被合并成超大块
MARKDOWN_HEADERS_TO_SPLIT_ON = [
    ("#", "Header 1"),
    ("##", "Header 2"),
    ("###", "Header 3"),
]


class DocumentSplitterService:
    def __init__(self) -> None:
        # chunk_size 存为实例属性，供 _merge_small_chunks 上限判断使用
        self.chunk_size = config.chunk_max_size * 2
        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=MARKDOWN_HEADERS_TO_SPLIT_ON,
            strip_headers=False,
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )

    def split_markdown(self, content: str, file_path: str) -> list[Document]:
        if not content or not content.strip():
            logger.warning(f"skip empty content: {file_path}")
            return []
        try:
            header_documents = self.markdown_splitter.split_text(content)
            # header 切分已按语义边界分块，超长节才二次切分，不做 merge
            chunk_documents = self.text_splitter.split_documents(header_documents)
            return self._with_file_metadata(chunk_documents, file_path)
        except Exception as e:
            logger.error(f"split_markdown failed [{file_path}]: {e}")
            raise

    def split_text(self, content: str, file_path: str) -> list[Document]:
        if not content or not content.strip():
            logger.warning(f"skip empty content: {file_path}")
            return []
        try:
            # 纯文本无结构边界，合并过小的碎片
            documents = self.text_splitter.create_documents([content])
            merged_documents = self._merge_small_chunks(documents)
            return self._with_file_metadata(merged_documents, file_path)
        except Exception as e:
            logger.error(f"split_text failed [{file_path}]: {e}")
            raise

    def split_document(self, content: str, file_path: str) -> list[Document]:
        if Path(file_path).suffix.lower() in MARKDOWN_EXTENSIONS:
            return self.split_markdown(content, file_path)

        return self.split_text(content, file_path)

    def _merge_small_chunks(
        self, documents: list[Document], min_size: int = MIN_CHUNK_SIZE
    ) -> list[Document]:
        merged_documents: list[Document] = []

        for document in documents:
            content_len = len(document.page_content)
            if content_len < min_size and merged_documents:
                previous = merged_documents[-1]
                # 合并后超过 chunk_size 则放弃合并，保留语义边界
                if len(previous.page_content) + content_len + 2 <= self.chunk_size:
                    previous.page_content = (
                        f"{previous.page_content}\n\n{document.page_content}"
                    )
                    continue

            merged_documents.append(
                Document(
                    page_content=document.page_content,
                    metadata=dict(document.metadata),
                )
            )

        return merged_documents

    def _with_file_metadata(
        self,
        documents: list[Document],
        file_path: str,
    ) -> list[Document]:
        path = Path(file_path)

        for document in documents:
            document.metadata["_source"] = file_path
            document.metadata["_file_name"] = path.name
            document.metadata["_extension"] = path.suffix.lower()

        return documents


document_splitter_service = DocumentSplitterService()
