"""
Apollo.io API integration for prospect search and enrichment.

Apollo docs: https://docs.apollo.io/reference/people-api-search

Key facts:
- Auth: x-api-key header (NOT in request body)
- Search endpoint (mixed_people/api_search): FREE, no credits consumed
- Enrichment endpoint (people/match): costs credits
- Employee history is included in search results — no need to enrich just for work history
"""

from __future__ import annotations

import re
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_settings
from models import ICPCriteria


# Apollo seniority level values
SENIORITY_MAP = {
    "vp": "vp",
    "vice president": "vp",
    "director": "director",
    "manager": "manager",
    "head": "director",
    "chief": "c_suite",
    "ceo": "c_suite",
    "cto": "c_suite",
    "coo": "c_suite",
    "cfo": "c_suite",
    "founder": "founder",
    "co-founder": "founder",
    "partner": "partner",
    "senior": "senior",
    "lead": "senior",
    "principal": "senior",
}

# Apollo company size ranges: "min,max" strings
COMPANY_SIZE_MAP = {
    "1-10": "1,10",
    "11-50": "11,50",
    "51-200": "51,200",
    "201-500": "201,500",
    "501-1000": "501,1000",
    "1001-5000": "1001,5000",
    "5001+": "5001,10000000",
}


def _extract_seniorities(titles: list[str]) -> list[str]:
    """Infer Apollo seniority levels from ICP title strings."""
    seniorities = set()
    for title in titles:
        lower = title.lower()
        for keyword, seniority in SENIORITY_MAP.items():
            if keyword in lower:
                seniorities.add(seniority)
    return list(seniorities)


class ApolloFetcher:
    def __init__(self):
        settings = get_settings()
        if not settings.apollo_api_key:
            raise ValueError(
                "APOLLO_API_KEY is not set. "
                "Get one at https://app.apollo.io/#/settings/integrations/api"
            )
        # Apollo auth is via header, not request body
        self._client = httpx.Client(
            headers={
                "x-api-key": settings.apollo_api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            base_url=settings.apollo_base_url,
            timeout=30.0,
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _post(self, path: str, params: dict) -> dict:
        """
        Apollo's search API uses query parameters (not JSON body) for filters.
        The endpoint is FREE and does not consume credits.
        """
        response = self._client.post(path, params=params)
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

        Uses GET-style query params (Apollo's array filter convention).
        Returns raw Apollo person objects including employment_history.
        Does NOT consume credits.
        """
        # Build flat query params — Apollo uses repeated keys for arrays
        params: list[tuple[str, Any]] = [
            ("organization_names[]", company_name),
            ("page", page),
            ("per_page", min(per_page, 100)),
        ]

        for title in icp.titles:
            params.append(("person_titles[]", title))

        for industry in icp.industries:
            params.append(("q_organization_industry_tag_ids[]", industry))

        for size in icp.company_sizes:
            mapped = COMPANY_SIZE_MAP.get(size)
            if mapped:
                params.append(("organization_num_employees_ranges[]", mapped))

        for loc in icp.locations:
            params.append(("person_locations[]", loc))

        for kw in icp.keywords:
            params.append(("keywords[]", kw))

        # Infer seniority levels from title strings to narrow results
        seniorities = _extract_seniorities(icp.titles)
        for s in seniorities:
            params.append(("person_seniorities[]", s))

        try:
            data = self._post("/mixed_people/api_search", dict(params))
            return data.get("people") or []
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 422):
                return []
            raise

    def find_person(self, linkedin_url: str) -> Optional[dict]:
        """
        Look up a person by LinkedIn URL using the free search endpoint.
        Returns a raw Apollo person object with employment_history, or None.
        Does NOT consume credits.
        """
        try:
            data = self._post("/mixed_people/api_search", {
                "linkedin_url": linkedin_url,
                "per_page": 1,
            })
            people = data.get("people") or []
            return people[0] if people else None
        except httpx.HTTPStatusError:
            return None

    def find_person_by_name(self, name: str, company: str) -> Optional[dict]:
        """
        Look up a person by name + company when LinkedIn URL lookup fails.
        Does NOT consume credits.
        """
        try:
            data = self._post("/mixed_people/api_search", {
                "person_names[]": name,
                "organization_names[]": company,
                "per_page": 1,
            })
            people = data.get("people") or []
            return people[0] if people else None
        except httpx.HTTPStatusError:
            return None

    def enrich_person(self, apollo_id: str) -> Optional[dict]:
        """
        Enrich a person by Apollo ID to get email/phone.
        Costs credits — use sparingly, only for high-scoring prospects.
        """
        try:
            response = self._client.post(
                "/people/match",
                params={"id": apollo_id, "reveal_personal_emails": "false"},
            )
            response.raise_for_status()
            return response.json().get("person")
        except httpx.HTTPStatusError:
            return None
