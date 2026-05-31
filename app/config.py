from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "alert-mind-agent"
    app_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 9000
    alert_mind_debug: bool = False
    dashscope_api_key: str = ""
    
    milvus_host: str = "localhost"
    milvus_port: int = 19531

    chunk_max_size: int = 800
    chunk_overlap: int = 100

config = Settings()
