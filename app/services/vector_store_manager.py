from uuid import uuid4

from langchain_core.documents import Document
from langchain_milvus import Milvus
from pymilvus import Collection, connections

from app.config import config
from app.core.milvus_client import COLLECTION_NAME, CONNECTION_ALIAS, milvus_manager
from app.services.vector_embedding_service import vector_embedding_service


class LegacyCompatibleMilvus(Milvus):
    def __init__(self, *args, legacy_aliases: set[str], **kwargs) -> None:
        self._legacy_aliases = legacy_aliases
        super().__init__(*args, **kwargs)

    @property
    def col(self) -> Collection | None:
        if not connections.has_connection(self.alias):
            connections.connect(alias=self.alias, uri=self._connection_args["uri"])
            self._legacy_aliases.add(self.alias)

        return super().col


class VectorStoreManager:
    def __init__(self) -> None:
        self.vector_store: Milvus | None = None
        self._legacy_aliases: set[str] = set()

    def initialize(self) -> None:
        if self.vector_store is not None:
            return

        if milvus_manager.collection is None:
            milvus_manager.connect()

        self.vector_store = LegacyCompatibleMilvus(
            embedding_function=vector_embedding_service,
            connection_args={
                "uri": f"http://{config.milvus_host}:{config.milvus_port}",
            },
            collection_name=COLLECTION_NAME,
            primary_field="id",
            text_field="content",
            vector_field="vector",
            metadata_field="metadata",
            legacy_aliases=self._legacy_aliases,
        )

    def close(self) -> None:
        self.vector_store = None

        for alias in self._legacy_aliases:
            if connections.has_connection(alias):
                connections.disconnect(alias)
        self._legacy_aliases.clear()

        if milvus_manager.collection is not None or connections.has_connection(CONNECTION_ALIAS):
            milvus_manager.close()

    def _get_vector_store(self) -> Milvus:
        self.initialize()
        if self.vector_store is None:
            raise RuntimeError("Milvus vector store is not initialized.")

        return self.vector_store

    def add_documents(self, docs: list[Document]) -> list[str]:
        ids = [uuid4().hex for _ in docs]

        return self._get_vector_store().add_documents(docs, ids=ids)

    def similarity_search(self, query: str, k: int) -> list[Document]:
        return self._get_vector_store().similarity_search(query, k=k)


vector_store_manager = VectorStoreManager()
