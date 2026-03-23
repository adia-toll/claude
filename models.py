"""Data models for the LinkedIn Referral Finder."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class DateRange(BaseModel):
    start: Optional[date] = None
    end: Optional[date] = None  # None = present

    def overlaps_with(self, other: "DateRange") -> bool:
        """Check if two date ranges overlap (i.e., two people worked somewhere at the same time)."""
        # If either end is None, treat as today
        a_end = self.end or date.today()
        b_end = other.end or date.today()
        a_start = self.start or date(1970, 1, 1)
        b_start = other.start or date(1970, 1, 1)
        return a_start <= b_end and b_start <= a_end

    def overlap_months(self, other: "DateRange") -> int:
        """Return approximate months of overlap between two ranges."""
        a_end = self.end or date.today()
        b_end = other.end or date.today()
        a_start = self.start or date(1970, 1, 1)
        b_start = other.start or date(1970, 1, 1)

        overlap_start = max(a_start, b_start)
        overlap_end = min(a_end, b_end)
        if overlap_start >= overlap_end:
            return 0
        delta = overlap_end - overlap_start
        return max(1, delta.days // 30)


class WorkExperience(BaseModel):
    company_name: str
    company_linkedin_id: Optional[str] = None
    title: str
    date_range: DateRange
    description: Optional[str] = None
    location: Optional[str] = None


class Education(BaseModel):
    school: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    date_range: DateRange


class ReferralSource(BaseModel):
    """The person whose network we are mapping."""
    linkedin_url: str
    full_name: str
    headline: Optional[str] = None
    current_company: Optional[str] = None
    current_title: Optional[str] = None
    location: Optional[str] = None
    profile_pic_url: Optional[str] = None
    work_history: list[WorkExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    follower_count: Optional[int] = None
    connections_count: Optional[int] = None


class RelationshipType(str, Enum):
    COWORKER = "coworker"          # Worked at the same company at the same time
    ALUMNI = "alumni"              # Went to the same school
    PAST_COMPANY = "past_company"  # Same company but different time period
    ENGAGEMENT = "engagement"      # Public LinkedIn activity (liked/commented)
    INDUSTRY_PEER = "industry_peer"


class RelationshipSignal(BaseModel):
    """Evidence that the referral source knows a prospect."""
    relationship_type: RelationshipType
    company_or_school: str
    overlap_months: int = 0
    detail: str  # Human-readable explanation


class ProspectMatch(BaseModel):
    """An ICP prospect that the referral source likely knows."""
    linkedin_url: Optional[str] = None
    full_name: str
    title: str
    company: str
    company_size: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None

    # Relationship intelligence
    relationship_signals: list[RelationshipSignal] = Field(default_factory=list)
    relationship_score: float = 0.0  # 0-100, higher = stronger relationship
    icp_score: float = 0.0           # 0-100, how well they fit the ICP

    @property
    def combined_score(self) -> float:
        return (self.relationship_score * 0.6) + (self.icp_score * 0.4)

    @property
    def top_relationship(self) -> Optional[RelationshipSignal]:
        if not self.relationship_signals:
            return None
        return max(self.relationship_signals, key=lambda s: s.overlap_months)


class ICPCriteria(BaseModel):
    """Ideal Customer Profile criteria to match prospects against."""
    titles: list[str] = Field(default_factory=list, description="Job titles to target (supports partial match)")
    industries: list[str] = Field(default_factory=list, description="Target industries")
    company_sizes: list[str] = Field(
        default_factory=list,
        description="Employee count ranges: '1-10', '11-50', '51-200', '201-500', '501-1000', '1001-5000', '5001+'"
    )
    locations: list[str] = Field(default_factory=list, description="Cities, states, or countries")
    keywords: list[str] = Field(default_factory=list, description="Keywords to match in title or description")
    exclude_titles: list[str] = Field(default_factory=list, description="Titles to exclude")


class ReferralFinderResult(BaseModel):
    """Full output of analyzing a referral source."""
    referral_source: ReferralSource
    icp_criteria: ICPCriteria
    prospects: list[ProspectMatch] = Field(default_factory=list)
    companies_searched: list[str] = Field(default_factory=list)
    total_candidates_evaluated: int = 0
    errors: list[str] = Field(default_factory=list)
