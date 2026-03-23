"""Data models for the LinkedIn Referral Finder."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DateRange(BaseModel):
    start: Optional[date] = None
    end: Optional[date] = None  # None = present

    def overlaps_with(self, other: "DateRange") -> bool:
        a_end = self.end or date.today()
        b_end = other.end or date.today()
        a_start = self.start or date(1970, 1, 1)
        b_start = other.start or date(1970, 1, 1)
        return a_start <= b_end and b_start <= a_end

    def overlap_months(self, other: "DateRange") -> int:
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

    @property
    def first_name(self) -> str:
        return self.full_name.split()[0] if self.full_name else ""


class RelationshipType(str, Enum):
    COWORKER = "coworker"
    ALUMNI = "alumni"
    PAST_COMPANY = "past_company"
    ENGAGEMENT = "engagement"
    INDUSTRY_PEER = "industry_peer"


class RelationshipSignal(BaseModel):
    relationship_type: RelationshipType
    company_or_school: str
    overlap_months: int = 0
    detail: str


class SellerContext(BaseModel):
    """Who is asking for the intro and what they're selling."""
    name: str
    title: str
    company: str
    product_description: str = Field(
        description="What the product does and who it's for — used to generate value prop copy"
    )


class ProspectNarrative(BaseModel):
    """AI-generated narrative content for the referral brief."""
    about_them_tags: list[str] = Field(description="1-2 short persona labels, e.g. '2nd-line Leader', 'RevOps / Sales Ops'")
    about_them: str = Field(description="2-3 sentence description of who they are and what they care about")
    about_company_tags: list[str] = Field(description="1 industry/category label, e.g. 'Event Tech', 'Intent Data'")
    about_company: str = Field(description="3-4 sentences with specific metrics: funding, growth, competitive position")
    why_connection: str = Field(description="1-2 sentences: the relationship thread + why they're a fit")
    how_product_helps: str = Field(description="3-4 sentences: specific value prop tied to their current situation")
    message_to_send: str = Field(description="Full intro message in the prescribed format")


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
    relationship_score: float = 0.0
    icp_score: float = 0.0

    # AI-generated narrative (populated after generation step)
    narrative: Optional[ProspectNarrative] = None

    @property
    def combined_score(self) -> float:
        return (self.relationship_score * 0.6) + (self.icp_score * 0.4)

    @property
    def top_relationship(self) -> Optional[RelationshipSignal]:
        if not self.relationship_signals:
            return None
        return max(self.relationship_signals, key=lambda s: s.overlap_months)


class ICPCriteria(BaseModel):
    """Ideal Customer Profile criteria."""
    titles: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    company_sizes: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    exclude_titles: list[str] = Field(default_factory=list)


class ReferralFinderResult(BaseModel):
    """Full output of analyzing a referral source."""
    referral_source: ReferralSource
    icp_criteria: ICPCriteria
    seller: Optional[SellerContext] = None
    prospects: list[ProspectMatch] = Field(default_factory=list)
    companies_searched: list[str] = Field(default_factory=list)
    total_candidates_evaluated: int = 0
    errors: list[str] = Field(default_factory=list)
