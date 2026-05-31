from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from app.config import config

CONNECTION_ALIAS = "default"
COLLECTION_NAME = "biz"
VECTOR_DIM = 1024
ID_MAX_LENGTH = 128
CONTENT_MAX_LENGTH = 65535
VECTOR_INDEX_NAME = "vector_ivf_flat_l2_idx"
VECTOR_INDEX_NLIST = 128


class MilvusClientManager:
    def __init__(self) -> None:
        self.collection: Collection | None = None

    def connect(self) -> None:
        connections.connect(
            alias=CONNECTION_ALIAS,
            host=config.milvus_host,
            port=config.milvus_port,
        )

        if not self._collection_exists():
            self.collection = self._create_collection()
        else:
            self.collection = Collection(COLLECTION_NAME, using=CONNECTION_ALIAS)

        self.collection.load()

    def close(self) -> None:
        if self.collection is not None:
            self.collection.release()
            self.collection = None

        connections.disconnect(CONNECTION_ALIAS)

    def get_collection(self) -> Collection:
        if self.collection is None:
            raise RuntimeError("Milvus collection is not connected. Call connect() first.")

        return self.collection

    def _collection_exists(self) -> bool:
        return utility.has_collection(COLLECTION_NAME, using=CONNECTION_ALIAS)

    def _create_collection(self) -> Collection:
        fields = [
            FieldSchema(
                name="id",
                dtype=DataType.VARCHAR,
                is_primary=True,
                auto_id=False,
                max_length=ID_MAX_LENGTH,
            ),
            FieldSchema(
                name="vector",
                dtype=DataType.FLOAT_VECTOR,
                dim=VECTOR_DIM,
            ),
            FieldSchema(
                name="content",
                dtype=DataType.VARCHAR,
                max_length=CONTENT_MAX_LENGTH,
            ),
            FieldSchema(
                name="metadata",
                dtype=DataType.JSON,
            ),
        ]
        schema = CollectionSchema(fields=fields, description="Business content vectors")
        collection = Collection(
            name=COLLECTION_NAME,
            schema=schema,
            using=CONNECTION_ALIAS,
        )
        collection.create_index(
            field_name="vector",
            index_params={
                "index_type": "IVF_FLAT",
                "metric_type": "L2",
                "params": {"nlist": VECTOR_INDEX_NLIST},
            },
            index_name=VECTOR_INDEX_NAME,
        )

        return collection


milvus_manager = MilvusClientManager()
