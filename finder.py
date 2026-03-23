"""
Main orchestration logic: given a referral source + ICP, find warm prospects.

Pipeline:
1. Fetch referral source's LinkedIn profile (career history, education)
2. For each company in their career history, search for ICP-matching employees
3. For each candidate, compute relationship signals (coworker? alumni? engaged?)
4. Score and rank all prospects
5. Return top results
"""

from __future__ import annotations

import re
from typing import Optional

from rich.console import Console

from config import get_settings
from linkedin_fetcher import LinkedInFetcher
from models import (
    DateRange,
    ICPCriteria,
    ProspectMatch,
    ReferralFinderResult,
    ReferralSource,
    SellerContext,
    WorkExperience,
)
from relationship_analyzer import (
    find_alumni_signals,
    find_coworker_signals,
    score_icp_fit,
    score_relationship,
    signals_from_post_engagement,
)

console = Console(stderr=True)


class ReferralFinder:
    def __init__(self):
        self._settings = get_settings()
        self._linkedin = LinkedInFetcher()

    def close(self):
        self._linkedin.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def run(
        self,
        linkedin_url: str,
        icp: ICPCriteria,
        seller: Optional[SellerContext] = None,
    ) -> ReferralFinderResult:
        errors: list[str] = []

        # ── Step 1: Fetch referral source profile ──────────────────────────
        console.log(f"[bold cyan]Fetching LinkedIn profile:[/] {linkedin_url}")
        try:
            source = self._linkedin.fetch_profile(linkedin_url)
        except Exception as e:
            raise RuntimeError(f"Could not fetch LinkedIn profile: {e}") from e

        console.log(
            f"[green]Got profile:[/] {source.full_name} | "
            f"{len(source.work_history)} jobs | {len(source.education)} schools"
        )

        result = ReferralFinderResult(
            referral_source=source,
            icp_criteria=icp,
            seller=seller,
        )

        # ── Step 2: Fetch public posts for engagement signals ──────────────
        posts = []
        try:
            posts = self._linkedin.fetch_person_posts(linkedin_url)
            console.log(f"[dim]Found {len(posts)} recent posts for engagement signals[/]")
        except Exception as e:
            errors.append(f"Could not fetch posts: {e}")

        # ── Step 3: Search each company in work history ────────────────────
        all_prospects: dict[str, ProspectMatch] = {}  # linkedin_url → ProspectMatch

        companies_to_search = source.work_history[: self._settings.max_companies_to_search]

        for job in companies_to_search:
            console.log(f"[yellow]Searching:[/] {job.company_name} ({job.title})")

            candidates = self._search_company(job, icp, errors)
            result.companies_searched.append(job.company_name)
            result.total_candidates_evaluated += len(candidates)

            for candidate in candidates:
                key = candidate.get("linkedin_url") or candidate.get("full_name") or ""
                if not key:
                    continue
                if key in all_prospects:
                    # Merge additional signals into existing prospect
                    existing = all_prospects[key]
                    new_signals = self._build_signals(source, candidate, posts)
                    existing.relationship_signals.extend(new_signals)
                    existing.relationship_score = score_relationship(existing.relationship_signals)
                    continue

                prospect = self._build_prospect(source, candidate, icp, posts)
                if prospect and prospect.relationship_score >= self._settings.min_relationship_score:
                    all_prospects[key] = prospect

        # ── Step 4: Sort by combined score ────────────────────────────────
        result.prospects = sorted(
            all_prospects.values(),
            key=lambda p: p.combined_score,
            reverse=True,
        )
        result.errors = errors

        console.log(
            f"[bold green]Done.[/] {len(result.prospects)} warm prospects found "
            f"from {result.total_candidates_evaluated} candidates evaluated."
        )
        return result

    def _search_company(
        self, job: WorkExperience, icp: ICPCriteria, errors: list[str]
    ) -> list[dict]:
        """Search for ICP prospects at a given company using PDL (free)."""
        candidates: list[dict] = []
        try:
            results = self._linkedin.search_company_employees(
                company_name=job.company_name,
                titles=icp.titles,
                per_page=self._settings.max_prospects_per_company,
            )
            for r in results:
                candidates.append(self._normalize_pdl_person(r))
            console.log(f"  [dim]PDL: {len(results)} candidates[/]")
        except Exception as e:
            errors.append(f"PDL search failed for {job.company_name}: {e}")
        return candidates

    def _build_signals(
        self,
        source: ReferralSource,
        candidate: dict,
        posts: list[dict],
    ):
        """Build all relationship signals between source and candidate."""
        signals = []

        # Coworker + alumni signals
        signals.extend(find_coworker_signals(source, candidate.get("work_history") or []))
        signals.extend(find_alumni_signals(source, candidate.get("education") or []))

        # Engagement signals
        name = candidate.get("full_name") or ""
        url = candidate.get("linkedin_url") or ""
        for post in posts:
            sig = signals_from_post_engagement(post, name, url)
            if sig:
                signals.append(sig)

        return signals

    def _build_prospect(
        self,
        source: ReferralSource,
        candidate: dict,
        icp: ICPCriteria,
        posts: list[dict],
    ) -> Optional[ProspectMatch]:
        name = candidate.get("full_name") or ""
        title = candidate.get("title") or ""
        company = candidate.get("company") or ""

        if not name or not title:
            return None

        signals = self._build_signals(source, candidate, posts)
        rel_score = score_relationship(signals)

        prospect = ProspectMatch(
            linkedin_url=candidate.get("linkedin_url"),
            full_name=name,
            title=title,
            company=company,
            company_size=candidate.get("company_size"),
            industry=candidate.get("industry"),
            location=candidate.get("location"),
            email=candidate.get("email"),
            relationship_signals=signals,
            relationship_score=rel_score,
        )
        prospect.icp_score = score_icp_fit(prospect, icp)
        return prospect

    @staticmethod
    def _normalize_apollo_person(p: dict) -> dict:
        """Normalize Apollo.io person object to our internal format."""
        org = p.get("organization") or {}
        emp_count = org.get("num_employees") or 0
        company_size = _bucket_employees(emp_count)

        return {
            "full_name": p.get("name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "title": p.get("title") or "",
            "company": p.get("organization_name") or org.get("name") or "",
            "company_size": company_size,
            "industry": org.get("industry") or p.get("industry") or "",
            "location": p.get("city") or p.get("state") or "",
            "email": p.get("email"),
            "linkedin_url": p.get("linkedin_url") or "",
            "work_history": [
                {
                    "company_name": emp.get("organization_name") or "",
                    "title": emp.get("title") or "",
                    "start_year": emp.get("start_date", "")[:4] if emp.get("start_date") else None,
                    "end_year": emp.get("end_date", "")[:4] if emp.get("end_date") else None,
                }
                for emp in (p.get("employment_history") or [])
            ],
            "education": [
                {"school": edu.get("school_name") or ""}
                for edu in (p.get("education_history") or [])
            ],
        }

    @staticmethod
    def _normalize_proxycurl_person(p: dict) -> dict:
        """Normalize Proxycurl profile object to our internal format."""
        experiences = p.get("experiences") or []
        current = next((e for e in experiences if not e.get("ends_at")), None)

        return {
            "full_name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "title": (current or {}).get("title") or p.get("headline") or "",
            "company": (current or {}).get("company") or "",
            "company_size": None,
            "industry": p.get("industry") or "",
            "location": p.get("city") or p.get("country_full_name") or "",
            "email": None,
            "linkedin_url": p.get("public_identifier")
                and f"https://linkedin.com/in/{p['public_identifier']}",
            "work_history": [
                {
                    "company_name": e.get("company") or "",
                    "title": e.get("title") or "",
                    "starts_at": e.get("starts_at"),
                    "ends_at": e.get("ends_at"),
                }
                for e in experiences
            ],
            "education": [
                {"school": e.get("school") or ""}
                for e in (p.get("education") or [])
            ],
        }

    @staticmethod
    def _normalize_pdl_person(p: dict) -> dict:
        """Normalize PDL person search result to our internal format."""
        exp = p.get("experience") or []
        current = next((e for e in exp if e.get("is_primary")), None)
        company_size = _bucket_employees(
            int(p.get("job_company_employee_count") or 0)
        )
        profiles = p.get("profiles") or []
        linkedin_url = next(
            (pr.get("url") for pr in profiles if "linkedin.com" in (pr.get("url") or "")),
            None,
        )
        return {
            "full_name": p.get("full_name") or "",
            "title": p.get("job_title") or (current or {}).get("title") or p.get("headline") or "",
            "company": p.get("job_company_name") or (current or {}).get("company", {}).get("name") or "",
            "company_size": company_size,
            "industry": p.get("industry") or "",
            "location": p.get("location_name") or "",
            "email": p.get("work_email") or p.get("personal_emails", [None])[0],
            "linkedin_url": linkedin_url or "",
            "work_history": [
                {
                    "company_name": (e.get("company") or {}).get("name") or "",
                    "title": e.get("title") or "",
                    "start_year": str(e["start_date"]["year"]) if e.get("start_date", {}).get("year") else None,
                    "end_year": str(e["end_date"]["year"]) if e.get("end_date", {}).get("year") else None,
                }
                for e in exp
            ],
            "education": [
                {"school": (e.get("school") or {}).get("name") or ""}
                for e in (p.get("education") or [])
            ],
        }

    @staticmethod
    def _build_title_regex(titles: list[str]) -> Optional[str]:
        if not titles:
            return None
        escaped = [re.escape(t) for t in titles]
        return "|".join(escaped)


def _bucket_employees(count: int) -> str:
    if count <= 10:
        return "1-10"
    elif count <= 50:
        return "11-50"
    elif count <= 200:
        return "51-200"
    elif count <= 500:
        return "201-500"
    elif count <= 1000:
        return "501-1000"
    elif count <= 5000:
        return "1001-5000"
    else:
        return "5001+"
