"""
Configurazione applicazione - carica variabili d'ambiente
"""

import os
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings applicazione caricate da .env"""

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Database
    database_url: str = "postgresql://datachat_user:AIEngineeringPOC@localhost:5432/datachat_db"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # LLM Provider
    default_llm_provider: Literal["claude", "azure", "gpt52"] = "claude"
    openrouter_api_key: Optional[str] = None
    openrouter_model: str = "anthropic/claude-sonnet-4-6"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    
    # Azure OpenAI
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_deployment_name: Optional[str] = None
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_embedding_endpoint: Optional[str] = None
    azure_openai_embedding_deployment: str = "text-embedding-3-large"

    # Azure OpenAI GPT-5.2
    azure_gpt52_endpoint: Optional[str] = None
    azure_gpt52_api_key: Optional[str] = None
    azure_gpt52_deployment_name: str = "gpt-5.2"
    azure_gpt52_api_version: str = "2024-12-01-preview"

    # LLM Parameters
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096
    llm_timeout_seconds: int = 60

    # MCP Configuration
    mcp_postgres_read_only: bool = True
    mcp_postgres_connection_string: str = "postgresql://datachat_user:AIEngineeringPOC@localhost:5432/datachat_db"
    
    # MCP Configuration - Supabase
    supabase_project_ref: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    supabase_database_password: Optional[str] = None
    
    # Supabase OAuth App
    supabase_oauth_client_id: Optional[str] = None
    supabase_oauth_client_secret: Optional[str] = None
    supabase_oauth_redirect_uri: str = "http://localhost:5173/oauth/callback"

    # Vanna 2.0
    vanna_model: str = "datachat_superstore"
    vanna_training_auto_save: bool = True
    vanna_rag_top_k: int = 5
    vanna_temperature: float = 0.1

    # ChromaDB
    chromadb_persist_directory: str = "./data/chromadb"
    chromadb_collection_name: str = "vanna_superstore"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = True
    api_workers: int = 1
    cors_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:5174"

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "text"

    # Performance
    sql_query_timeout_seconds: int = 30

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = Settings()
