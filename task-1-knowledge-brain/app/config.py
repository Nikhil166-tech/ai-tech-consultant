import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model_text: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL_TEXT", "claude-3-5-haiku-20241022"))
    anthropic_model_vision: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL_VISION", "claude-3-5-sonnet-20241022"))
    
    knowledge_db_path: str = Field(default_factory=lambda: os.getenv("KNOWLEDGE_DB_PATH", "knowledge_brain.db"))
    default_sitemap_url: str = Field(default_factory=lambda: os.getenv("DEFAULT_SITEMAP_URL", "https://support.brilliantdirectories.com/support/sitemap.xml"))
    
    crawler_delay_seconds: float = Field(default_factory=lambda: float(os.getenv("CRAWLER_DELAY_SECONDS", "0.3")))
    max_concurrent_requests: int = Field(default_factory=lambda: int(os.getenv("MAX_CONCURRENT_REQUESTS", "3")))
    max_retries: int = Field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
    retry_backoff_factor: float = Field(default_factory=lambda: float(os.getenv("RETRY_BACKOFF_FACTOR", "0.5")))
    
    hybrid_alpha: float = Field(default_factory=lambda: float(os.getenv("HYBRID_ALPHA", "0.55")))
    evidence_threshold: float = Field(default_factory=lambda: float(os.getenv("EVIDENCE_THRESHOLD", "0.30")))

settings = Settings()
