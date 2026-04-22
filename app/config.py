from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "Contract Analyzer API"
    version: str = "1.0.0"
    environment: str = "development"
    log_level: str = "info"

    # Limits
    max_pdf_size_mb: int = 50

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # RAG
    chroma_persist_dir: str = "./data/chroma"

    # Optional server-side default key (not required — users send their own)
    anthropic_api_key: str | None = Field(default=None)

    @property
    def max_pdf_size_bytes(self) -> int:
        return self.max_pdf_size_mb * 1024 * 1024

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
