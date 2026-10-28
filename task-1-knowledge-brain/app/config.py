import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Environment
    environment: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))

    # Security & Internal Service Auth
    internal_service_key: str = Field(
        default_factory=lambda: os.getenv("INTERNAL_SERVICE_KEY", "")
    )
    session_secret: str = Field(
        default_factory=lambda: os.getenv("SESSION_SECRET", "dev_session_secret_signing_key_a1b2c3d4e5f6")
    )
    allowed_origins_raw: str = Field(
        default_factory=lambda: os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"
        )
    )

    # Demo Authentication Settings
    demo_auth_enabled: bool = Field(
        default_factory=lambda: os.getenv("DEMO_AUTH_ENABLED", "true").lower() in ["true", "1", "yes"]
    )
    demo_user_email: str = Field(
        default_factory=lambda: os.getenv("DEMO_USER_EMAIL", "demo.consultant@brilliantdirectories.com")
    )
    demo_user_password: str = Field(
        default_factory=lambda: os.getenv("DEMO_USER_PASSWORD", "DemoPassword123!")
    )

    # Auth Rate Limiting & Session Configuration
    session_expiry_days: int = Field(default_factory=lambda: int(os.getenv("SESSION_EXPIRY_DAYS", "7")))
    failed_login_limit: int = Field(default_factory=lambda: int(os.getenv("FAILED_LOGIN_LIMIT", "5")))
    lockout_duration_minutes: int = Field(default_factory=lambda: int(os.getenv("LOCKOUT_DURATION_MINUTES", "15")))

    # AI Model Settings
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", os.getenv("ANTHROPIC_API_KEY", "")))
    gemini_model_text: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL_TEXT", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")))
    gemini_model_vision: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL_VISION", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")))
    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_workspace_id: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_WORKSPACE_ID", ""))
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

    @property
    def allowed_origins(self) -> List[str]:
        return [orig.strip() for orig in self.allowed_origins_raw.split(",") if orig.strip()]

    def is_production(self) -> bool:
        return self.environment.lower() in ["production", "prod"]

    def validate_production_secrets(self):
        """Validates that production environment has explicit, non-default secrets."""
        if self.is_production():
            if not self.internal_service_key or "dev_" in self.internal_service_key:
                raise ValueError("In production mode, INTERNAL_SERVICE_KEY must be set to a secure, unique secret.")
            if not self.session_secret or "dev_" in self.session_secret:
                raise ValueError("In production mode, SESSION_SECRET must be set to a secure, unique secret.")
            if self.demo_auth_enabled:
                # Force disable demo auth in production
                self.demo_auth_enabled = False

settings = Settings()
settings.validate_production_secrets()
