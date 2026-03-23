"""
Apollo.io API integration for prospect search and enrichment.

Apollo docs: https://apolloio.github.io/apollo-api-docs/
"""

from __future__ import annotations

from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_settings
from models import ICPCriteria


# Map human-readable company sizes to Apollo's num_employees_ranges format
COMPANY_SIZE_MAP = {
    "1-10": "1,10",
    "11-50": "11,50",
    "51-200": "51,200",
    "201-500": "201,500",
    "501-1000": "501,1000",
    "1001-5000": "1001,5000",
    "5001+": "5001,10000000",
}


class ApolloFetcher:
    def __init__(self):
        settings = get_settings()
        if not settings.apollo_api_key:
            raise ValueError(
                "APOLLO_API_KEY is not set. Get one at https://app.apollo.io/#/settings/integrations/api"
            )
        self._api_key = settings.apollo_api_key
        self._base_url = settings.apollo_base_url
        self._client = httpx.Client(timeout=30.0)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _post(self, path: str, body: dict) -> dict:
        url = f"{self._base_url}{path}"
        body["api_key"] = self._api_key
        response = self._client.post(url, json=body)
        response.raise_for_status()
        return response.json()

    def search_people_at_company(
        self,
        company_name: str,
        icp: ICPCriteria,
        page: int = 1,
        per_page: int = 25,
    ) -> list[dict]:
        """
        Search Apollo for people at a specific company matching ICP criteria.
        Returns raw Apollo person objects.
        """
        body: dict[str, Any] = {
            "page": page,
            "per_page": min(per_page, 100),
            "organization_names": [company_name],
        }

        if icp.titles:
            body["titles"] = icp.titles

        if icp.industries:
            body["organization_industry_tag_ids"] = []
            body["q_organization_industry_tags"] = icp.industries

        if icp.company_sizes:
            body["organization_num_employees_ranges"] = [
                COMPANY_SIZE_MAP[s] for s in icp.company_sizes if s in COMPANY_SIZE_MAP
            ]

        if icp.locations:
            body["person_locations"] = icp.locations

        try:
            data = self._post("/mixed_people/search", body)
            return data.get("people") or []
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 422):
                return []
            raise

    def enrich_person(self, linkedin_url: str) -> Optional[dict]:
        """Enrich a person profile using their LinkedIn URL."""
        try:
            data = self._post(
                "/people/match",
                {"linkedin_url": linkedin_url, "reveal_personal_emails": False},
            )
            return data.get("person")
        except httpx.HTTPStatusError:
            return None
