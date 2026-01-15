"""Configuration settings for the FastAPI application."""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import List


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
    
    # CORS
    cors_origins: List[str] = ["http://localhost:3000"]
    
    # Environment
    environment: str = "development"
    debug: bool = False
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"  # Ignore extra environment variables (like AWS_* variables)
    )


settings = Settings()
