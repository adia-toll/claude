"""
AI narrative generation for referral briefs.

Uses Claude Opus 4.6 to generate the "About Them", "About the Company",
"Why You / Why Them", "How Product Helps", and "Message to Send" fields
for each prospect — matching the format shown in the example output.
"""

from __future__ import annotations

import json
from typing import Optional

import anthropic
from rich.console import Console

from models import (
    ProspectMatch,
    ProspectNarrative,
    ReferralSource,
    RelationshipSignal,
    RelationshipType,
    SellerContext,
)

console = Console(stderr=True)

SYSTEM_PROMPT = """You are a B2B sales intelligence analyst preparing a referral dossier FOR the referral source.

This document is designed to make it effortless for the referral source to make warm intros. Every field is written for them, not about them. The "Message to Send" is the exact text they copy and paste — addressed to the prospect, in the referral source's voice, introducing the seller.

Rules:
- About the company: use specific metrics (funding round + amount, growth %, headcount, customer count, ARR if known, analyst recognition like Gartner/Forrester). Use your knowledge of these companies.
- Relationship context: state it precisely and from the referral source's perspective (e.g., "You two were both at Klaviyo, his RVP tenure overlaps your rep tenure" or "Fellow Babson alum, 90 days into a new CRO role, he's actively building the stack right now")
- How product helps: tie it to the prospect's specific role + company situation RIGHT NOW. What's their actual challenge?
- Message: written in the referral source's voice, addressed TO the prospect (starts with the prospect's first name), introducing the seller. Warm, direct, not salesy.
- Always respond with valid JSON only — no markdown fences, no extra text."""


def _format_relationship_context(
    source: ReferralSource, signals: list[RelationshipSignal]
) -> str:
    if not signals:
        return "No direct relationship signals found."
    parts = []
    for s in signals:
        parts.append(f"- {s.detail}")
    return "\n".join(parts)


def _format_career_summary(source: ReferralSource) -> str:
    jobs = []
    for job in source.work_history[:6]:
        tenure = ""
        if job.date_range.start:
            start = job.date_range.start.strftime("%Y")
            end = job.date_range.end.strftime("%Y") if job.date_range.end else "present"
            tenure = f" ({start}–{end})"
        jobs.append(f"{job.title} at {job.company_name}{tenure}")
    schools = [edu.school for edu in source.education[:2]]
    result = "; ".join(jobs)
    if schools:
        result += f". Education: {', '.join(schools)}"
    return result


def _build_prompt(
    prospect: ProspectMatch,
    source: ReferralSource,
    seller: SellerContext,
) -> str:
    rel_context = _format_relationship_context(source, prospect.relationship_signals)
    career_summary = _format_career_summary(source)

    return f"""Create a referral brief for this warm introduction opportunity.

## Referral Source (the person making the intro)
Name: {source.full_name}
Current: {source.current_title} at {source.current_company}
Career: {career_summary}

## Prospect (who we want to intro the seller to)
Name: {prospect.full_name}
Title: {prospect.title}
Company: {prospect.company}
Industry: {prospect.industry or 'unknown'}
Location: {prospect.location or 'unknown'}
Company Size: {prospect.company_size or 'unknown'}
LinkedIn: {prospect.linkedin_url or 'unknown'}

## How the Referral Source Knows This Prospect
{rel_context}

## The Seller Being Introduced
Name: {seller.name}
Title: {seller.title}
Company: {seller.company}

## Product
{seller.product_description}

## Generate a referral brief as JSON with exactly these 7 fields:

{{
  "about_them_tags": ["<1-2 short persona labels>"],
  "about_them": "<2-3 sentences: role scope, what they own, what they care about>",
  "about_company_tags": ["<1 industry/category label>"],
  "about_company": "<3-4 sentences: what they do, specific metrics (funding, growth, ARR, customers, analysts), competitive position>",
  "why_connection": "<1-2 sentences: the specific relationship thread PLUS why they're a fit for the product>",
  "how_product_helps": "<3-4 sentences: their specific challenge right now + exactly how {seller.company} solves it>",
  "message_to_send": "{source.first_name} → {prospect.full_name}\\n[prospect first name]! <message body ending with 'You two should talk. ✌'>"
}}

For persona tags use labels like: "2nd-line Leader", "RevOps / Sales Ops", "CRO", "Founder", "6x Exits", "Podcaster", "MarTech", "VP of Sales", "Sales Ops", "GTM Leader", "Enterprise AE", "SDR Leader", "CS Leader"

For industry tags use labels like: "Event Tech", "Intent Data", "Vertical SaaS", "eCommerce / Logistics", "AI / AEO", "HR Tech", "Sales Tech", "RevOps", "FinTech", "MarTech", "Dev Tools"

The message_to_send must:
- Header line: "{source.first_name} → {prospect.full_name}" (shows who is sending to whom)
- Body starts with "[prospect's first name]!" — addressing the PROSPECT, not the referral source
- Written in the REFERRAL SOURCE's voice (they are the one sending it)
- Reference the relationship naturally (don't say "I noticed you worked together" — just state it)
- Introduce {seller.name} as {seller.title} at {seller.company} with a compelling one-line description
- Tie it to something specific about the prospect's role or company situation right now
- End with exactly: "You two should talk. ✌"
- Be ~4-5 sentences total, warm and direct"""


class GeminiGenerator:
    """
    FREE narrative generator using Google Gemini Flash.
    Free tier: 1,500 requests/day, 15 RPM.
    Get a key at https://aistudio.google.com/apikey
    """

    def __init__(self):
        from google import genai
        from google.genai import types as gtypes
        settings = get_settings()
        if not settings.google_api_key:
            import os
            key = os.environ.get("GOOGLE_API_KEY")
            if not key:
                raise ValueError(
                    "GOOGLE_API_KEY is required for --generate. "
                    "Get a free key at https://aistudio.google.com/apikey"
                )
        else:
            key = settings.google_api_key
        self._client = genai.Client(api_key=key)
        self._gtypes = gtypes

    def generate(
        self,
        prospect: ProspectMatch,
        source: ReferralSource,
        seller: SellerContext,
    ) -> Optional[ProspectNarrative]:
        prompt = SYSTEM_PROMPT + "\n\n" + _build_prompt(prospect, source, seller)
        try:
            response = self._client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=self._gtypes.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            data = json.loads(response.text.strip())
            return ProspectNarrative(**data)
        except (json.JSONDecodeError, Exception) as e:
            console.log(f"[yellow]Generation failed for {prospect.full_name}: {e}[/]")
            return None

    def generate_batch(
        self,
        prospects: list[ProspectMatch],
        source: ReferralSource,
        seller: SellerContext,
    ) -> list[ProspectMatch]:
        updated = []
        for i, prospect in enumerate(prospects, 1):
            console.log(
                f"[cyan]Generating brief {i}/{len(prospects)}:[/] {prospect.full_name} "
                f"@ {prospect.company}"
            )
            narrative = self.generate(prospect, source, seller)
            if narrative:
                prospect = prospect.model_copy(update={"narrative": narrative})
            updated.append(prospect)
        return updated


class NarrativeGenerator:
    def __init__(self):
        self._client = anthropic.Anthropic()
        self._model = "claude-opus-4-6"

    def generate(
        self,
        prospect: ProspectMatch,
        source: ReferralSource,
        seller: SellerContext,
    ) -> Optional[ProspectNarrative]:
        """Generate AI narrative for a single prospect. Returns None on failure."""
        prompt = _build_prompt(prospect, source, seller)

        try:
            with self._client.messages.stream(
                model=self._model,
                max_tokens=1500,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                response = stream.get_final_message()

            text = next(
                (b.text for b in response.content if b.type == "text"), None
            )
            if not text:
                return None

            data = json.loads(text.strip())
            return ProspectNarrative(**data)

        except (json.JSONDecodeError, Exception) as e:
            console.log(f"[yellow]Generation failed for {prospect.full_name}: {e}[/]")
            return None

    def generate_batch(
        self,
        prospects: list[ProspectMatch],
        source: ReferralSource,
        seller: SellerContext,
    ) -> list[ProspectMatch]:
        """Generate narratives for all prospects, returning updated list."""
        updated = []
        for i, prospect in enumerate(prospects, 1):
            console.log(
                f"[cyan]Generating brief {i}/{len(prospects)}:[/] {prospect.full_name} "
                f"@ {prospect.company}"
            )
            narrative = self.generate(prospect, source, seller)
            if narrative:
                prospect = prospect.model_copy(update={"narrative": narrative})
            updated.append(prospect)
        return updated


def create_generator():
    """
    Return the right generator based on AI_PROVIDER setting.
    Defaults to Gemini (free). Set AI_PROVIDER=anthropic for Claude.
    """
    settings = get_settings()
    if settings.ai_provider == "anthropic":
        return NarrativeGenerator()
    return GeminiGenerator()
