"""
LinkedIn profile data fetching.

Proxycurl shut down in mid-2025 after a LinkedIn lawsuit. This module
supports multiple alternative providers:

  - "netrows"  — Netrows LinkedIn API (https://netrows.com)
  - "pdl"      — People Data Labs (https://peopledatalabs.com)
  - "brightdata" — Bright Data (https://brightdata.com)

Set LINKEDIN_PROVIDER in your .env to select one.
All providers return a normalized ReferralSource object.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_settings
from models import DateRange, Education, ReferralSource, WorkExperience


# ── Date helpers ──────────────────────────────────────────────────────────────

def _parse_date(d: Optional[dict | str]) -> Optional[date]:
    """Parse various date formats into a date object."""
    if not d:
        return None
    # Dict format: {'year': 2020, 'month': 3, 'day': 1}
    if isinstance(d, dict):
        year = d.get("year")
        if not year:
            return None
        month = d.get("month") or 1
        day = d.get("day") or 1
        try:
            return date(int(year), int(month), int(day))
        except (ValueError, TypeError):
            return None
    # ISO string: "2020-03" or "2020-03-01"
    if isinstance(d, str) and d:
        parts = d.split("-")
        try:
            year = int(parts[0])
            month = int(parts[1]) if len(parts) > 1 else 1
            day = int(parts[2]) if len(parts) > 2 else 1
            return date(year, month, day)
        except (ValueError, IndexError):
            return None
    return None


def _normalize_linkedin_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    return url


# ── Normalized work/education parsers (shared across providers) ───────────────

def _parse_work_history(experiences: list[dict], provider: str = "") -> list[WorkExperience]:
    results = []
    for exp in experiences or []:
        # Field names vary by provider
        company = (
            exp.get("company")
            or exp.get("company_name")
            or exp.get("organization")
            or exp.get("organization_name")
            or ""
        )
        title = exp.get("title") or exp.get("job_title") or ""
        if not company or not title:
            continue

        # PDL uses "start_date"/"end_date" strings; others use dict "starts_at"/"ends_at"
        starts_at = _parse_date(exp.get("starts_at") or exp.get("start_date"))
        ends_at = _parse_date(exp.get("ends_at") or exp.get("end_date"))

        # current=True in PDL means still employed
        if exp.get("current") is True:
            ends_at = None

        results.append(WorkExperience(
            company_name=company,
            company_linkedin_id=exp.get("company_linkedin_profile_url") or exp.get("company_linkedin_url"),
            title=title,
            date_range=DateRange(start=starts_at, end=ends_at),
            description=exp.get("description"),
            location=exp.get("location"),
        ))
    return results


def _parse_education(educations: list[dict]) -> list[Education]:
    results = []
    for edu in educations or []:
        school = edu.get("school") or edu.get("school_name") or edu.get("name") or ""
        if not school:
            continue
        results.append(Education(
            school=school,
            degree=edu.get("degree_name") or edu.get("degree") or edu.get("degrees", [None])[0],
            field_of_study=edu.get("field_of_study") or edu.get("majors", [None])[0],
            date_range=DateRange(
                start=_parse_date(edu.get("starts_at") or edu.get("start_date")),
                end=_parse_date(edu.get("ends_at") or edu.get("end_date")),
            ),
        ))
    return results


def _build_source(url: str, data: dict, provider: str) -> ReferralSource:
    """Convert a raw provider response dict into a ReferralSource."""
    work_history = _parse_work_history(data.get("experiences") or data.get("work_history") or [], provider)
    education = _parse_education(data.get("education") or [])
    current_exp = next((e for e in work_history if e.date_range.end is None), None)

    return ReferralSource(
        linkedin_url=url,
        full_name=(
            data.get("full_name")
            or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        ),
        headline=data.get("headline"),
        current_company=current_exp.company_name if current_exp else None,
        current_title=current_exp.title if current_exp else None,
        location=data.get("city") or data.get("location_name") or data.get("country_full_name"),
        profile_pic_url=data.get("profile_pic_url") or data.get("profile_picture_url"),
        work_history=work_history,
        education=education,
        follower_count=data.get("follower_count"),
        connections_count=data.get("connections"),
    )


# ── Provider implementations ──────────────────────────────────────────────────

class _NetrowsFetcher:
    """
    Netrows LinkedIn API — https://netrows.com
    Proxycurl-compatible endpoint structure.
    Env var: NETROWS_API_KEY
    """
    BASE = "https://api.netrows.com"

    def __init__(self, api_key: str):
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def fetch_profile(self, url: str) -> ReferralSource:
        resp = self._client.get(
            f"{self.BASE}/api/v2/linkedin",
            params={"url": url, "use_cache": "if-present"},
        )
        resp.raise_for_status()
        data = resp.json()
        return _build_source(url, data, "netrows")

    def resolve_company_url(self, company_name: str) -> Optional[str]:
        try:
            resp = self._client.get(
                f"{self.BASE}/linkedin/company/resolve",
                params={"company_name": company_name},
            )
            resp.raise_for_status()
            return resp.json().get("url")
        except httpx.HTTPStatusError:
            return None

    def search_company_employees(
        self, company_linkedin_url: str, keyword_regex: Optional[str] = None, page_size: int = 25
    ) -> list[dict]:
        params: dict[str, Any] = {
            "linkedin_company_profile_url": company_linkedin_url,
            "page_size": min(page_size, 100),
            "enrich_profiles": "enrich",
        }
        if keyword_regex:
            params["keyword_regex"] = keyword_regex
        try:
            resp = self._client.get(f"{self.BASE}/linkedin/company/employees/", params=params)
            resp.raise_for_status()
            return resp.json().get("employees") or []
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise

    def fetch_person_posts(self, linkedin_url: str) -> list[dict]:
        try:
            resp = self._client.get(
                f"{self.BASE}/v2/linkedin/person/posts",
                params={"linkedin_profile_url": linkedin_url, "post_count": 10},
            )
            resp.raise_for_status()
            return resp.json().get("posts") or []
        except httpx.HTTPStatusError:
            return []

    def close(self):
        self._client.close()


class _PDLFetcher:
    """
    People Data Labs (PDL) — https://peopledatalabs.com
    Person enrichment by LinkedIn URL. No company employee search.
    Env var: PDL_API_KEY
    """
    BASE = "https://api.peopledatalabs.com/v5"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = httpx.Client(
            headers={"X-Api-Key": api_key},
            timeout=30.0,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def fetch_profile(self, url: str) -> ReferralSource:
        resp = self._client.get(
            f"{self.BASE}/person/enrich",
            params={"profile": url, "pretty": False},
        )
        resp.raise_for_status()
        data = resp.json()
        return _build_source(url, data, "pdl")

    def resolve_company_url(self, company_name: str) -> Optional[str]:
        return None  # PDL does not provide LinkedIn company URL resolution

    def search_company_employees(
        self,
        company_name: str,
        titles: list[str],
        per_page: int = 25,
    ) -> list[dict]:
        """
        Search PDL for people at a company matching given titles.
        Free tier: 1 credit per record returned (1,000 credits/month free).
        """
        title_filters = [{"match": {"job_title": t}} for t in titles] if titles else []
        query: dict = {
            "bool": {
                "must": [{"term": {"job_company_name": company_name.lower()}}],
            }
        }
        if title_filters:
            query["bool"]["should"] = title_filters
            query["bool"]["minimum_should_match"] = 1

        try:
            resp = self._client.post(
                f"{self.BASE}/person/search",
                json={"query": query, "size": per_page, "pretty": False},
            )
            resp.raise_for_status()
            return resp.json().get("data") or []
        except httpx.HTTPStatusError:
            return []

    def fetch_person_posts(self, linkedin_url: str) -> list[dict]:
        return []  # PDL does not provide post data

    def close(self):
        self._client.close()


class _BrightDataFetcher:
    """
    Bright Data LinkedIn scraper — https://brightdata.com
    Uses their Web Scraper API for LinkedIn profiles.
    Env var: BRIGHTDATA_API_KEY, BRIGHTDATA_DATASET_ID
    """
    BASE = "https://api.brightdata.com"

    def __init__(self, api_key: str, dataset_id: str):
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,
        )
        self._dataset_id = dataset_id

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
    def fetch_profile(self, url: str) -> ReferralSource:
        # Trigger collection
        resp = self._client.post(
            f"{self.BASE}/datasets/v3/trigger",
            params={"dataset_id": self._dataset_id, "include_errors": True},
            json=[{"url": url}],
        )
        resp.raise_for_status()
        snapshot_id = resp.json().get("snapshot_id")
        if not snapshot_id:
            raise RuntimeError("Bright Data did not return a snapshot_id")

        # Poll for results
        import time
        for _ in range(20):
            time.sleep(3)
            snap = self._client.get(
                f"{self.BASE}/datasets/v3/snapshot/{snapshot_id}",
                params={"format": "json"},
            )
            if snap.status_code == 200:
                records = snap.json()
                if records:
                    return _build_source(url, records[0], "brightdata")
        raise RuntimeError("Bright Data snapshot timed out")

    def resolve_company_url(self, company_name: str) -> Optional[str]:
        return None

    def search_company_employees(self, *args, **kwargs) -> list[dict]:
        return []

    def fetch_person_posts(self, linkedin_url: str) -> list[dict]:
        return []

    def close(self):
        self._client.close()


class _ApolloProfileFetcher:
    """
    FREE LinkedIn profile lookup via Apollo's search endpoint.
    Uses employment_history from Apollo's person data to build a ReferralSource.
    No API credits consumed — uses the free mixed_people/api_search endpoint.
    """

    def __init__(self, api_key: str):
        # Import here to avoid circular dependency
        from apollo_fetcher import ApolloFetcher
        self._apollo = ApolloFetcher()

    def fetch_profile(self, url: str) -> ReferralSource:
        from apollo_fetcher import ApolloFetcher
        apollo = self._apollo

        person = apollo.find_person(url)
        if not person:
            # Try extracting the slug from the URL and search by name
            raise RuntimeError(
                f"Could not find this person on Apollo. "
                f"Try LINKEDIN_PROVIDER=netrows/pdl for direct profile lookup."
            )
        return self._parse(url, person)

    def resolve_company_url(self, company_name: str) -> Optional[str]:
        return None  # Apollo doesn't provide LinkedIn company URLs

    def search_company_employees(self, *args, **kwargs) -> list[dict]:
        return []  # Handled directly by ApolloFetcher in finder.py

    def fetch_person_posts(self, linkedin_url: str) -> list[dict]:
        return []  # Apollo doesn't provide post data

    def close(self):
        self._apollo.close()

    @staticmethod
    def _parse(url: str, person: dict) -> ReferralSource:
        """Convert an Apollo person dict into a ReferralSource."""
        org = person.get("organization") or {}

        work_history = []
        for emp in person.get("employment_history") or []:
            company = emp.get("organization_name") or ""
            title = emp.get("title") or ""
            if not company or not title:
                continue
            starts_at = _parse_date(emp.get("start_date"))
            ends_at = _parse_date(emp.get("end_date"))
            if emp.get("current"):
                ends_at = None
            work_history.append(WorkExperience(
                company_name=company,
                title=title,
                date_range=DateRange(start=starts_at, end=ends_at),
            ))

        education = []
        for edu in person.get("education_history") or []:
            school = edu.get("school_name") or ""
            if school:
                education.append(Education(
                    school=school,
                    degree=edu.get("degree"),
                    field_of_study=edu.get("field_of_study"),
                    date_range=DateRange(),
                ))

        current = next((e for e in work_history if e.date_range.end is None), None)

        return ReferralSource(
            linkedin_url=url,
            full_name=person.get("name") or f"{person.get('first_name','')} {person.get('last_name','')}".strip(),
            headline=person.get("headline"),
            current_company=current.company_name if current else (org.get("name") or person.get("organization_name")),
            current_title=current.title if current else person.get("title"),
            location=person.get("city") or person.get("state") or "",
            work_history=work_history,
            education=education,
        )


# ── Public interface ──────────────────────────────────────────────────────────

class LinkedInFetcher:
    """
    Provider-agnostic LinkedIn data fetcher.
    Selects the backend based on LINKEDIN_PROVIDER env var.

    Default (free): LINKEDIN_PROVIDER=apollo uses Apollo's free search tier.
    """

    def __init__(self):
        settings = get_settings()
        provider = settings.linkedin_provider.lower()

        if provider == "apollo":
            if not settings.apollo_api_key:
                raise ValueError("APOLLO_API_KEY is required (free at apollo.io)")
            self._backend = _ApolloProfileFetcher(settings.apollo_api_key)

        elif provider == "netrows":
            if not settings.netrows_api_key:
                raise ValueError("NETROWS_API_KEY is required when LINKEDIN_PROVIDER=netrows")
            self._backend = _NetrowsFetcher(settings.netrows_api_key)

        elif provider == "pdl":
            if not settings.pdl_api_key:
                raise ValueError("PDL_API_KEY is required when LINKEDIN_PROVIDER=pdl")
            self._backend = _PDLFetcher(settings.pdl_api_key)

        elif provider == "brightdata":
            if not settings.brightdata_api_key or not settings.brightdata_dataset_id:
                raise ValueError(
                    "BRIGHTDATA_API_KEY and BRIGHTDATA_DATASET_ID are required when LINKEDIN_PROVIDER=brightdata"
                )
            self._backend = _BrightDataFetcher(settings.brightdata_api_key, settings.brightdata_dataset_id)

        else:
            raise ValueError(
                f"Unknown LINKEDIN_PROVIDER '{provider}'. "
                "Valid values: netrows, pdl, brightdata"
            )

    def fetch_profile(self, url: str) -> ReferralSource:
        return self._backend.fetch_profile(_normalize_linkedin_url(url))

    def resolve_company_url(self, company_name: str) -> Optional[str]:
        return self._backend.resolve_company_url(company_name)

    def search_company_employees(
        self, company_linkedin_url: str, keyword_regex: Optional[str] = None, page_size: int = 25
    ) -> list[dict]:
        return self._backend.search_company_employees(company_linkedin_url, keyword_regex, page_size)

    def fetch_person_posts(self, linkedin_url: str) -> list[dict]:
        return self._backend.fetch_person_posts(linkedin_url)

    def close(self):
        self._backend.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
