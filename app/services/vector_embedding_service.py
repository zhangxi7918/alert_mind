from openai import OpenAI
from openai import OpenAIError
from langchain_core.embeddings import Embeddings

from app.config import config, get_dashscope_api_key

DASHSCOPE_COMPATIBLE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_EMBEDDING_DIMENSIONS = 1024


class DashScopeEmbeddings(Embeddings):
    def __init__(
        self,
        api_key: str | None,
        model: str,
        dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    ) -> None:
        self.api_key = api_key
        self.client: OpenAI | None = None
        self.model = model
        self.dimensions = dimensions

    # DashScope embedding API 单次最多接受 10 条文本
    BATCH_SIZE = 10

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        results = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            response = self._get_client().embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dimensions,
            )
            results.extend(embedding_data.embedding for embedding_data in response.data)
        return results

    def embed_query(self, text: str) -> list[float]:
        response = self._get_client().embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimensions,
        )

        return response.data[0].embedding

    def _get_client(self) -> OpenAI:
        if self.client is not None:
            return self.client

        api_key = self.api_key or get_dashscope_api_key()

        try:
            self.client = OpenAI(
                api_key=api_key,
                base_url=DASHSCOPE_COMPATIBLE_BASE_URL,
            )
        except OpenAIError as exc:
            raise RuntimeError("Failed to initialize DashScope embedding client.") from exc

        return self.client


vector_embedding_service = DashScopeEmbeddings(
    api_key=None,
    model=config.dashscope_embedding_model,
    dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
)
