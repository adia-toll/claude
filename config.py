"""Configuration and settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── LinkedIn profile provider ─────────────────────────────────────────────
    # "apollo"     — FREE. Uses Apollo's free search tier to look up profiles.
    # "netrows"    — Paid. https://netrows.com
    # "pdl"        — Paid. https://peopledatalabs.com
    # "brightdata" — Paid. https://brightdata.com
    linkedin_provider: str = "apollo"

    netrows_api_key: Optional[str] = None
    pdl_api_key: Optional[str] = None
    brightdata_api_key: Optional[str] = None
    brightdata_dataset_id: Optional[str] = None

    # ── Apollo.io — FREE for search ───────────────────────────────────────────
    # Get a free key at https://app.apollo.io/#/settings/integrations/api
    apollo_api_key: Optional[str] = None
    apollo_base_url: str = "https://api.apollo.io/api/v1"

    # ── AI narrative generation ───────────────────────────────────────────────
    # "gemini"    — FREE. Google Gemini Flash via AI Studio free tier.
    # "anthropic" — Paid. Claude Opus 4.6, highest quality.
    ai_provider: str = "gemini"

    # Google Gemini — get a free key at https://aistudio.google.com/apikey
    google_api_key: Optional[str] = None

    # Anthropic Claude (only needed if ai_provider=anthropic)
    anthropic_api_key: Optional[str] = None

    # ── Behavior ──────────────────────────────────────────────────────────────
    max_companies_to_search: int = 10
    max_prospects_per_company: int = 25
    min_relationship_score: float = 20.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
