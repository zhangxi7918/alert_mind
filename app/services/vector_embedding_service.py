from openai import OpenAI
from openai import OpenAIError
from langchain_core.embeddings import Embeddings

from app.config import config

DASHSCOPE_COMPATIBLE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_EMBEDDING_DIMENSIONS = 1024


class DashScopeEmbeddings(Embeddings):
    def __init__(
        self,
        api_key: str,
        model: str,
        dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    ) -> None:
        self.api_key = api_key
        self.client: OpenAI | None = None
        self.model = model
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = self._get_client().embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions,
        )

        return [embedding_data.embedding for embedding_data in response.data]

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

        if not self.api_key:
            raise RuntimeError("DashScope API key is missing. Set DASHSCOPE_API_KEY in .env or environment.")

        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=DASHSCOPE_COMPATIBLE_BASE_URL,
            )
        except OpenAIError as exc:
            raise RuntimeError("Failed to initialize DashScope embedding client.") from exc

        return self.client


vector_embedding_service = DashScopeEmbeddings(
    api_key=config.dashscope_api_key,
    model=config.dashscope_embedding_model,
    dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
)
