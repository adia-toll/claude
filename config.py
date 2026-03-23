"""Configuration and settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── LinkedIn profile provider ─────────────────────────────────────────────
    # Proxycurl shut down mid-2025 (LinkedIn lawsuit). Pick one of:
    #   "netrows"    — https://netrows.com  (Proxycurl-compatible)
    #   "pdl"        — https://peopledatalabs.com  (enrichment by LinkedIn URL)
    #   "brightdata" — https://brightdata.com  (enterprise scraping)
    linkedin_provider: str = "netrows"

    netrows_api_key: Optional[str] = None
    pdl_api_key: Optional[str] = None
    brightdata_api_key: Optional[str] = None
    brightdata_dataset_id: Optional[str] = None

    # ── Apollo.io (prospect search) ───────────────────────────────────────────
    apollo_api_key: Optional[str] = None
    apollo_base_url: str = "https://api.apollo.io/api/v1"

    # ── Behavior ──────────────────────────────────────────────────────────────
    max_companies_to_search: int = 10   # Limit company searches to control API cost
    max_prospects_per_company: int = 25
    min_relationship_score: float = 20.0  # Only return prospects above this threshold


@lru_cache
def get_settings() -> Settings:
    return Settings()
