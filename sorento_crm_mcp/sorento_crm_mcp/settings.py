"""Environment configuration for the MCP server."""
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """CRM MCP settings (env-prefixed CRM_MCP_ or plain names where noted)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    crm_base_url: str = Field(
        ...,
        validation_alias=AliasChoices("CRM_BASE_URL", "crm_base_url"),
        description="Base URL of Sorento CRM API, e.g. https://api.example.com",
    )
    external_api_key: str = Field(
        ...,
        validation_alias=AliasChoices("EXTERNAL_API_KEY", "external_api_key"),
        description="Same X-API-Key as FastAPI EXTERNAL_API_KEY",
    )
    request_timeout_seconds: float = Field(
        60.0,
        validation_alias=AliasChoices("CRM_MCP_TIMEOUT", "request_timeout_seconds"),
    )
    max_response_bytes: int = Field(
        8_000_000,
        validation_alias=AliasChoices("CRM_MCP_MAX_RESPONSE_BYTES", "max_response_bytes"),
    )
    mcp_host: str = Field("0.0.0.0", validation_alias=AliasChoices("CRM_MCP_HOST", "mcp_host"))
    mcp_port: int = Field(8765, validation_alias=AliasChoices("CRM_MCP_PORT", "mcp_port"))
    log_level: str = Field("INFO", validation_alias=AliasChoices("CRM_MCP_LOG_LEVEL", "log_level"))
