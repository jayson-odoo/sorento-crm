"""Configuration settings for the FastAPI application."""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Union


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    database_url: str
    direct_url: str | None = None
    
    # JWT Authentication
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    
    # API Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # CORS - accept as string and parse
    cors_origins: str = "http://localhost:3000"
    
    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> str:
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, list):
            return ','.join(v)
        return v
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Get CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]
    
    # Environment
    environment: str = "development"
    debug: bool = False

    # Respond.io
    respond_api_key: str | None = None
    respond_base_url: str = "https://api.respond.io"
    respond_app_base_url: str = "https://app.respond.io"  # Base URL for inbox links (e.g. /space/{id}/inbox/{contact_id})
    respond_space_id: str | None = None
    
    # External API Access
    external_api_key: str | None = None  # API key for external parties to access endpoints
    
    # Redis Queue
    redis_url: str = "redis://localhost:6379/0"

    # Frontend app URL (for password reset and other links in emails)
    frontend_base_url: str | None = None

    # Feature flags (progressive rollout)
    notifications_v1_enabled: bool = True  # NOTIFICATIONS_V1_ENABLED
    # When False (default), module guards allow all API routes if tenant has no module rows yet (legacy).
    # When True, disabled modules return 403 from guarded routers.
    module_guard_strict: bool = False  # MODULE_GUARD_STRICT

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables (like AWS_* variables)
    )


# Values come from environment / .env at runtime; static analysis cannot infer required env vars.
settings = Settings()  # type: ignore[call-arg]
