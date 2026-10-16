import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model_text: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL_TEXT", "claude-haiku-5-5"))
    anthropic_model_vision: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL_VISION", "claude-sonnet-5-5"))
    
    knowledge_db_path: str = Field(default_factory=lambda: os.getenv("KNOWLEDGE_DB_PATH", "knowledge_brain.db"))
    default_sitemap_url: str = Field(default_factory=lambda: os.getenv("DEFAULT_SITEMAP_URL", "https://support.brilliantdirectories.com/support/sitemap.xml"))
    
    # Embedding Configuration (Learned Semantic Provider)
    embedding_provider: str = Field(default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "fastembed"))
    embedding_model_name: str = Field(default_factory=lambda: os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5"))

    # Lightweight Daily Synchronization
    enable_background_sync: bool = Field(default_factory=lambda: os.getenv("ENABLE_BACKGROUND_SYNC", "false").lower() in ["true", "1", "yes"])
    sync_interval_hours: float = Field(default_factory=lambda: float(os.getenv("SYNC_INTERVAL_HOURS", "24.0")))

    # Crawler Settings
    crawler_delay_seconds: float = Field(default_factory=lambda: float(os.getenv("CRAWLER_DELAY_SECONDS", "0.3")))
    max_concurrent_requests: int = Field(default_factory=lambda: int(os.getenv("MAX_CONCURRENT_REQUESTS", "3")))
    max_retries: int = Field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
    retry_backoff_factor: float = Field(default_factory=lambda: float(os.getenv("RETRY_BACKOFF_FACTOR", "0.5")))
    
    # RAG Scoring Thresholds
    hybrid_alpha: float = Field(default_factory=lambda: float(os.getenv("HYBRID_ALPHA", "0.55")))
    evidence_threshold: float = Field(default_factory=lambda: float(os.getenv("EVIDENCE_THRESHOLD", "0.30")))

settings = Settings()
