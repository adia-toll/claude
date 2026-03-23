"""
Core relationship intelligence engine.

This is what makes the tool work like Commsor/Swarm/Orbb:
given a referral source's career history and network signals,
score how well they actually know each prospect.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from models import (
    DateRange,
    ICPCriteria,
    ProspectMatch,
    ReferralSource,
    RelationshipSignal,
    RelationshipType,
    WorkExperience,
)


# ── Relationship scoring weights ──────────────────────────────────────────────
# These mirror how Commsor/Swarm think about relationship strength.
# Co-workers who overlapped for 12+ months are the warmest intros.

SCORE_WEIGHTS = {
    RelationshipType.COWORKER: 50,        # Same company, same time → warmest
    RelationshipType.ALUMNI: 25,          # Same school
    RelationshipType.PAST_COMPANY: 15,    # Same company, different time
    RelationshipType.ENGAGEMENT: 30,      # Actively liked/commented on posts
    RelationshipType.INDUSTRY_PEER: 5,
}

# Bonus months of overlap → additional score
OVERLAP_SCORE_PER_MONTH = 2.0
MAX_OVERLAP_BONUS = 40.0


def score_relationship(signals: list[RelationshipSignal]) -> float:
    """
    Convert a list of relationship signals into a 0-100 score.
    Multiple signals stack (e.g., co-worker AND engaged on posts).
    """
    if not signals:
        return 0.0

    total = 0.0
    for signal in signals:
        base = SCORE_WEIGHTS.get(signal.relationship_type, 0)
        overlap_bonus = min(signal.overlap_months * OVERLAP_SCORE_PER_MONTH, MAX_OVERLAP_BONUS)
        total += base + overlap_bonus

    return min(total, 100.0)


def score_icp_fit(prospect: ProspectMatch, icp: ICPCriteria) -> float:
    """Score how well a prospect matches the ICP criteria (0-100)."""
    if not icp.titles and not icp.industries and not icp.company_sizes:
        return 50.0  # No criteria defined → neutral score

    score = 0.0
    checks = 0

    if icp.titles:
        checks += 1
        title_lower = (prospect.title or "").lower()
        matched = any(t.lower() in title_lower or title_lower in t.lower() for t in icp.titles)
        # Exclude titles
        excluded = any(e.lower() in title_lower for e in icp.exclude_titles)
        if matched and not excluded:
            score += 40
        elif excluded:
            return 0.0  # Hard exclusion

    if icp.industries and prospect.industry:
        checks += 1
        ind_lower = prospect.industry.lower()
        if any(i.lower() in ind_lower or ind_lower in i.lower() for i in icp.industries):
            score += 25

    if icp.company_sizes and prospect.company_size:
        checks += 1
        if prospect.company_size in icp.company_sizes:
            score += 20

    if icp.locations and prospect.location:
        loc_lower = prospect.location.lower()
        if any(l.lower() in loc_lower or loc_lower in l.lower() for l in icp.locations):
            score += 15

    if icp.keywords:
        title_lower = (prospect.title or "").lower()
        company_lower = (prospect.company or "").lower()
        keyword_hits = sum(
            1 for kw in icp.keywords
            if kw.lower() in title_lower or kw.lower() in company_lower
        )
        if keyword_hits:
            score += min(keyword_hits * 5, 15)

    return min(score, 100.0)


# ── Career overlap detection ──────────────────────────────────────────────────

def find_coworker_signals(
    referral_source: ReferralSource,
    prospect_work_history: list[dict],
) -> list[RelationshipSignal]:
    """
    Compare the referral source's work history with a prospect's work history.
    Returns signals for each company overlap found.
    """
    signals = []

    # Build prospect work history
    prospect_jobs: list[tuple[str, DateRange]] = []
    for exp in prospect_work_history or []:
        company = exp.get("company_name") or exp.get("company") or exp.get("organization_name") or ""
        if not company:
            continue
        from linkedin_fetcher import _parse_date
        starts_at = _parse_date(exp.get("starts_at")) or _parse_date({"year": exp.get("start_year"), "month": exp.get("start_month")})
        ends_at = _parse_date(exp.get("ends_at")) or _parse_date({"year": exp.get("end_year"), "month": exp.get("end_month")})
        prospect_jobs.append((company.lower().strip(), DateRange(start=starts_at, end=ends_at)))

    if not prospect_jobs:
        return signals

    for source_job in referral_source.work_history:
        source_company = source_job.company_name.lower().strip()

        for prospect_company, prospect_range in prospect_jobs:
            # Fuzzy company name match
            if not _companies_match(source_company, prospect_company):
                continue

            overlap = source_job.date_range.overlap_months(prospect_range)
            if overlap > 0:
                signals.append(RelationshipSignal(
                    relationship_type=RelationshipType.COWORKER,
                    company_or_school=source_job.company_name,
                    overlap_months=overlap,
                    detail=f"Both worked at {source_job.company_name} with ~{overlap} months overlap",
                ))
            else:
                signals.append(RelationshipSignal(
                    relationship_type=RelationshipType.PAST_COMPANY,
                    company_or_school=source_job.company_name,
                    overlap_months=0,
                    detail=f"Both worked at {source_job.company_name} at different times",
                ))

    return signals


def find_alumni_signals(
    referral_source: ReferralSource,
    prospect_education: list[dict],
) -> list[RelationshipSignal]:
    """Find shared educational institutions."""
    signals = []
    source_schools = {edu.school.lower().strip() for edu in referral_source.education}

    for edu in prospect_education or []:
        school = (edu.get("school") or edu.get("school_name") or "").lower().strip()
        if school and school in source_schools:
            signals.append(RelationshipSignal(
                relationship_type=RelationshipType.ALUMNI,
                company_or_school=school.title(),
                overlap_months=0,
                detail=f"Both attended {school.title()}",
            ))

    return signals


def signals_from_post_engagement(
    post: dict,
    prospect_name: str,
    prospect_linkedin_url: Optional[str],
) -> Optional[RelationshipSignal]:
    """
    Check if a prospect appeared as a commenter/reactor on the referral source's posts.
    """
    commenters = post.get("comments") or []
    for comment in commenters:
        author_url = comment.get("commenter_profile_url") or ""
        author_name = comment.get("commenter_name") or ""
        if (prospect_linkedin_url and author_url and prospect_linkedin_url in author_url) or (
            prospect_name.lower() in author_name.lower()
        ):
            return RelationshipSignal(
                relationship_type=RelationshipType.ENGAGEMENT,
                company_or_school="LinkedIn",
                overlap_months=1,
                detail=f"Commented on {prospect_name}'s post",
            )
    return None


def _companies_match(a: str, b: str) -> bool:
    """Fuzzy match two company names."""
    a = _clean_company(a)
    b = _clean_company(b)
    if a == b:
        return True
    # Check if one is a substring of the other (handles "Acme" vs "Acme Corp")
    if len(a) >= 4 and len(b) >= 4:
        return a in b or b in a
    return False


def _clean_company(name: str) -> str:
    """Strip common legal suffixes for comparison."""
    suffixes = [" inc", " llc", " ltd", " corp", " corporation", " co", ", inc", ", llc"]
    name = name.lower().strip()
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    return name
