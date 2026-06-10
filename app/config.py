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
    dashscope_api_key: str = ""
    dashscope_embedding_model: str = "text-embedding-v4"
    
    # Milvus 配置
    milvus_host: str = "localhost"
    milvus_port: int = 19531

    # MCP 配置
    mcp_monitor_transport: str = "streamable-http"
    mcp_monitor_url: str = "http://localhost:8004/mcp"

    # Prometheus 配置
    prometheus_base_url: str = "http://localhost:9090"

    # Redis 配置
    redis_url: str = "redis://localhost:6379"
    redis_checkpoint_ttl_minutes: int = 10080
    redis_checkpoint_refresh_on_read: bool = True
    rag_stream_terminal_ttl_seconds: int = 86400
    rag_stream_running_timeout_seconds: int = 7200

    # 文档分块配置
    chunk_max_size: int = 800
    chunk_overlap: int = 100

    # RAG 配置
    rag_top_k: int = 3
    rag_model: str = "qwen-max"
    # 相关性阈值：[0, 1]，越大越严格；低于阈值的结果会被过滤
    rag_score_threshold: float = 0.7
    # Rerank 配置：开启后先粗召回 rag_rerank_top_n 条，再精排取 rag_top_k 条
    rag_rerank_enabled: bool = False
    rag_rerank_top_n: int = 20
    rag_rerank_model: str = "gte-rerank-v2"
    # Rerank 后置过滤：relevance_score 低于此值的结果直接丢弃（邻域负例通常 < 0.2，正例通常 > 0.3）
    rag_rerank_min_score: float = 0.2

config = Settings()


def get_dashscope_api_key(settings: Settings | None = None) -> str:
    current_config = settings or config
    api_key = current_config.dashscope_api_key.strip()
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置，请在 .env 或环境变量中设置后再启动服务。")

    return api_key
