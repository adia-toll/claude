"""
LinkedIn data fetching via Proxycurl API.

Proxycurl docs: https://nubela.co/proxycurl/docs
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_settings
from models import DateRange, Education, ReferralSource, WorkExperience


def _parse_date(d: Optional[dict]) -> Optional[date]:
    """Parse Proxycurl date dict {'year': 2020, 'month': 3, 'day': 15} → date."""
    if not d:
        return None
    year = d.get("year")
    if not year:
        return None
    month = d.get("month") or 1
    day = d.get("day") or 1
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, month, 1)


def _normalize_linkedin_url(url: str) -> str:
    """Ensure URL is a clean linkedin.com/in/... profile URL."""
    url = url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    return url


def _parse_work_history(experiences: list[dict]) -> list[WorkExperience]:
    results = []
    for exp in experiences or []:
        company = exp.get("company") or exp.get("company_name") or ""
        title = exp.get("title") or ""
        if not company or not title:
            continue

        starts_at = _parse_date(exp.get("starts_at"))
        ends_at = _parse_date(exp.get("ends_at"))

        results.append(
            WorkExperience(
                company_name=company,
                company_linkedin_id=exp.get("company_linkedin_profile_url"),
                title=title,
                date_range=DateRange(start=starts_at, end=ends_at),
                description=exp.get("description"),
                location=exp.get("location"),
            )
        )
    return results


def _parse_education(educations: list[dict]) -> list[Education]:
    results = []
    for edu in educations or []:
        school = edu.get("school") or ""
        if not school:
            continue
        results.append(
            Education(
                school=school,
                degree=edu.get("degree_name"),
                field_of_study=edu.get("field_of_study"),
                date_range=DateRange(
                    start=_parse_date(edu.get("starts_at")),
                    end=_parse_date(edu.get("ends_at")),
                ),
            )
        )
    return results


class LinkedInFetcher:
    def __init__(self):
        settings = get_settings()
        if not settings.proxycurl_api_key:
            raise ValueError(
                "PROXYCURL_API_KEY is not set. Get one at https://nubela.co/proxycurl"
            )
        self._api_key = settings.proxycurl_api_key
        self._base_url = settings.proxycurl_base_url
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=30.0,
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _get(self, path: str, params: dict) -> dict:
        url = f"{self._base_url}{path}"
        response = self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def fetch_profile(self, linkedin_url: str) -> ReferralSource:
        """Fetch and parse a LinkedIn profile."""
        url = _normalize_linkedin_url(linkedin_url)
        data = self._get(
            "/v2/linkedin",
            {
                "url": url,
                "extra": "include",
                "skills": "include",
                "use_cache": "if-present",
            },
        )
        return self._parse_profile(url, data)

    def _parse_profile(self, url: str, data: dict) -> ReferralSource:
        work_history = _parse_work_history(data.get("experiences") or [])
        education = _parse_education(data.get("education") or [])

        current_exp = next(
            (e for e in work_history if e.date_range.end is None), None
        )

        return ReferralSource(
            linkedin_url=url,
            full_name=f"{data.get('first_name', '')} {data.get('last_name', '')}".strip(),
            headline=data.get("headline"),
            current_company=current_exp.company_name if current_exp else None,
            current_title=current_exp.title if current_exp else None,
            location=data.get("city") or data.get("country_full_name"),
            profile_pic_url=data.get("profile_pic_url"),
            work_history=work_history,
            education=education,
            follower_count=data.get("follower_count"),
            connections_count=data.get("connections"),
        )

    def search_company_employees(
        self,
        company_linkedin_url: str,
        keyword_regex: Optional[str] = None,
        page_size: int = 25,
    ) -> list[dict]:
        """
        Search employees at a company using Proxycurl's employee search endpoint.
        Returns raw Proxycurl person objects.
        """
        params: dict[str, Any] = {
            "linkedin_company_profile_url": company_linkedin_url,
            "page_size": min(page_size, 100),
            "enrich_profiles": "enrich",  # Include full profile data
        }
        if keyword_regex:
            params["keyword_regex"] = keyword_regex

        try:
            data = self._get("/linkedin/company/employees/", params)
            return data.get("employees", []) or []
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise

    def resolve_company_url(self, company_name: str) -> Optional[str]:
        """
        Try to resolve a company name to a LinkedIn company URL.
        Uses Proxycurl's company search endpoint.
        """
        try:
            data = self._get(
                "/linkedin/company/resolve",
                {"company_name": company_name},
            )
            return data.get("url")
        except httpx.HTTPStatusError:
            return None

    def fetch_person_posts(self, linkedin_url: str) -> list[dict]:
        """
        Fetch recent posts/activity from a LinkedIn profile.
        Returns raw post objects with engagement data.
        """
        try:
            data = self._get(
                "/v2/linkedin/person/posts",
                {
                    "linkedin_profile_url": linkedin_url,
                    "post_count": 10,
                },
            )
            return data.get("posts") or []
        except httpx.HTTPStatusError:
            return []
