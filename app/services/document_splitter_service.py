from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from app.config import config

MIN_CHUNK_SIZE = 300
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
MARKDOWN_HEADERS_TO_SPLIT_ON = [
    ("#", "Header 1"),
    ("##", "Header 2"),
]


class DocumentSplitterService:
    def __init__(self) -> None:
        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=MARKDOWN_HEADERS_TO_SPLIT_ON,
            strip_headers=False,
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_max_size * 2,
            chunk_overlap=config.chunk_overlap,
        )

    def split_markdown(self, content: str, file_path: str) -> list[Document]:
        header_documents = self.markdown_splitter.split_text(content)
        chunk_documents = self.text_splitter.split_documents(header_documents)
        merged_documents = self._merge_small_chunks(chunk_documents)

        return self._with_file_metadata(merged_documents, file_path)

    def split_text(self, content: str, file_path: str) -> list[Document]:
        documents = self.text_splitter.create_documents([content])

        return self._with_file_metadata(documents, file_path)

    def split_document(self, content: str, file_path: str) -> list[Document]:
        if Path(file_path).suffix.lower() in MARKDOWN_EXTENSIONS:
            return self.split_markdown(content, file_path)

        return self.split_text(content, file_path)

    def _merge_small_chunks(self, documents: list[Document]) -> list[Document]:
        merged_documents: list[Document] = []

        for document in documents:
            if len(document.page_content) < MIN_CHUNK_SIZE and merged_documents:
                previous_document = merged_documents[-1]
                previous_document.page_content = (
                    f"{previous_document.page_content}\n\n{document.page_content}"
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
        file_name = Path(file_path).name

        for document in documents:
            document.metadata["_source"] = file_path
            document.metadata["_file_name"] = file_name

        return documents


document_splitter_service = DocumentSplitterService()
