"""
Core application configuration using Pydantic settings.
"""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Environment
    environment: str = Field(default="development")
    debug: bool = Field(default=True)

    # PostgreSQL
    database_url: str = Field(
        default="postgresql+asyncpg://neuronal_seo:neuronal_seo_pass@localhost:5432/neuronal_seo",
        alias="DATABASE_URL",
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg2://neuronal_seo:neuronal_seo_pass@localhost:5432/neuronal_seo",
        alias="DATABASE_URL_SYNC",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
    )

    # OpenAI
    openai_api_key: str = Field(default="sk-your-key-here", alias="OPENAI_API_KEY")
    openai_embedding_model: str = Field(
        default="text-embedding-3-large", alias="OPENAI_EMBEDDING_MODEL"
    )
    openai_llm_model: str = Field(default="gpt-4o", alias="OPENAI_LLM_MODEL")

    # DataForSEO
    dataforseo_login: Optional[str] = Field(default=None, alias="DATAFORSEO_LOGIN")
    dataforseo_api_key: Optional[str] = Field(default=None, alias="DATAFORSEO_API_KEY")

    # SerpAPI
    serpapi_key: Optional[str] = Field(default=None, alias="SERPAPI_KEY")

    # Local embeddings
    local_embedding_model: str = Field(
        default="paraphrase-multilingual-MiniLM-L12-v2",
        alias="LOCAL_EMBEDDING_MODEL",
    )

    # Report settings
    report_output_dir: str = Field(default="./reports", alias="REPORT_OUTPUT_DIR")
    email_enabled: bool = Field(default=False, alias="EMAIL_ENABLED")
    smtp_host: Optional[str] = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: Optional[str] = Field(default=None, alias="SMTP_USER")
    smtp_password: Optional[str] = Field(default=None, alias="SMTP_PASSWORD")
    report_email_to: Optional[str] = Field(default=None, alias="REPORT_EMAIL_TO")

    # Scheduler
    enable_scheduler: bool = Field(default=False, alias="ENABLE_SCHEDULER")
    schedule_day: str = Field(default="mon", alias="SCHEDULE_DAY")
    schedule_hour: int = Field(default=8, alias="SCHEDULE_HOUR")
    schedule_minute: int = Field(default=0, alias="SCHEDULE_MINUTE")

    # Crawler
    crawler_user_agent: str = Field(
        default="Mozilla/5.0 (compatible; NeuronalSEO/1.0)",
        alias="CRAWLER_USER_AGENT",
    )
    crawler_rate_limit: int = Field(default=2, alias="CRAWLER_RATE_LIMIT")
    crawler_max_pages: int = Field(default=500, alias="CRAWLER_MAX_PAGES")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "populate_by_name": True}


settings = Settings()
