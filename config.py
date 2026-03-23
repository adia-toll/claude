"""Configuration and settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    proxycurl_api_key: Optional[str] = None
    apollo_api_key: Optional[str] = None

    # Proxycurl base URL
    proxycurl_base_url: str = "https://nubela.co/proxycurl/api"

    # Apollo base URL
    apollo_base_url: str = "https://api.apollo.io/api/v1"

    # Behavior
    max_companies_to_search: int = 10   # Limit company searches to control API cost
    max_prospects_per_company: int = 25
    min_relationship_score: float = 20.0  # Only return prospects above this score


@lru_cache
def get_settings() -> Settings:
    return Settings()
