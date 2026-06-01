from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用配置
    app_name: str = "alert-mind-agent"
    app_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 9000
    alert_mind_debug: bool = False

    # DashScope 配置
    dashscope_api_key: str = "sk-a292c383da6149ed844d82f1af284e50"
    dashscope_embedding_model: str = "text-embedding-v4"
    
    # Milvus 配置
    milvus_host: str = "localhost"
    milvus_port: int = 19531

    # 文档分块配置
    chunk_max_size: int = 800
    chunk_overlap: int = 100

    # RAG 配置
    rag_top_k: int = 3
    rag_model: str = "qwen-max"

config = Settings()
