#!/usr/bin/env python3
"""
LinkedIn Referral Finder

Usage:
  # Quick prospect scan (no AI generation)
  python main.py find https://linkedin.com/in/johndoe \
    --title "VP of Sales" --title "Head of Revenue" \
    --industry "SaaS" --company-size "51-200"

  # Full referral brief with AI-generated narratives → HTML output
  python main.py find https://linkedin.com/in/johndoe \
    --title "VP of Sales" \
    --seller-name "Jane Smith" \
    --seller-title "Head of SDR" \
    --seller-company "AskElephant" \
    --product "AskElephant analyzes sales conversations to surface what messaging, questions, and CTAs actually convert by persona and industry — so revenue teams build outbound around their real buyers, not a generic playbook." \
    --generate \
    --output html > referral-list.html
"""

from __future__ import annotations

import sys
from enum import Enum
from typing import Optional

import typer
from rich.console import Console

from config import get_settings
from finder import ReferralFinder
from generator import NarrativeGenerator
from models import ICPCriteria, SellerContext
from report import export_csv, export_html, export_json, print_result

app = typer.Typer(
    name="referral-finder",
    help="Find warm ICP prospects through a referral source's real relationships.",
    add_completion=False,
    rich_markup_mode="rich",
)
err = Console(stderr=True)


class OutputFormat(str, Enum):
    table = "table"
    html = "html"
    json = "json"
    csv = "csv"


@app.command()
def find(
    linkedin_url: str = typer.Argument(
        ..., help="LinkedIn profile URL of the referral source"
    ),
    # ICP filters
    title: list[str] = typer.Option([], "--title", "-t", help="Target title (repeatable, partial match)"),
    industry: list[str] = typer.Option([], "--industry", "-i", help="Target industry (repeatable)"),
    company_size: list[str] = typer.Option(
        [], "--company-size", "-s",
        help="1-10 | 11-50 | 51-200 | 201-500 | 501-1000 | 1001-5000 | 5001+"
    ),
    location: list[str] = typer.Option([], "--location", "-l", help="Target location (repeatable)"),
    keyword: list[str] = typer.Option([], "--keyword", "-k", help="Keyword to match in title/company"),
    exclude_title: list[str] = typer.Option([], "--exclude-title", help="Exclude this title"),
    # Seller context (for AI generation)
    seller_name: Optional[str] = typer.Option(None, "--seller-name", help="Name of the person being introduced (e.g. 'Adia Toll')"),
    seller_title: Optional[str] = typer.Option(None, "--seller-title", help="Their title (e.g. 'Head of SDR')"),
    seller_company: Optional[str] = typer.Option(None, "--seller-company", help="Their company (e.g. 'AskElephant')"),
    product: Optional[str] = typer.Option(
        None, "--product",
        help="What the product does — used to generate 'How Product Helps' and intro messages"
    ),
    # AI generation
    generate: bool = typer.Option(
        False, "--generate/--no-generate",
        help="Generate AI narratives (About Them, Why Them, message) using Claude. Requires ANTHROPIC_API_KEY."
    ),
    # Output
    output: OutputFormat = typer.Option(OutputFormat.table, "--output", "-o", help="table | html | json | csv"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max rows (table output)"),
    min_score: Optional[float] = typer.Option(None, "--min-score", help="Override minimum relationship score"),
):
    """
    [bold]Map a referral source's real network to surface warm ICP prospects.[/]

    Add [cyan]--generate[/] + seller flags to get AI-written briefs with intro messages.
    Add [cyan]--output html > out.html[/] to get a shareable table matching the example layout.
    """
    settings = get_settings()
    if min_score is not None:
        settings.min_relationship_score = min_score

    icp = ICPCriteria(
        titles=title,
        industries=industry,
        company_sizes=company_size,
        locations=location,
        keywords=keyword,
        exclude_titles=exclude_title,
    )

    # Build seller context if flags provided
    seller: Optional[SellerContext] = None
    if any([seller_name, seller_title, seller_company, product]):
        missing = [f for f, v in [
            ("--seller-name", seller_name),
            ("--seller-title", seller_title),
            ("--seller-company", seller_company),
            ("--product", product),
        ] if not v]
        if missing:
            err.print(f"[yellow]⚠ To use seller context, provide all flags: {', '.join(missing)}[/]")
        else:
            seller = SellerContext(
                name=seller_name,
                title=seller_title,
                company=seller_company,
                product_description=product,
            )

    if generate and not seller:
        err.print("[red]--generate requires --seller-name, --seller-title, --seller-company, and --product[/]")
        raise typer.Exit(1)

    if generate and not settings.anthropic_api_key:
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            err.print("[red]--generate requires ANTHROPIC_API_KEY to be set[/]")
            raise typer.Exit(1)

    # ── Find prospects ────────────────────────────────────────────────────────
    try:
        with ReferralFinder() as finder:
            result = finder.run(linkedin_url, icp, seller=seller)
    except ValueError as e:
        err.print(f"[red]Configuration error:[/] {e}")
        raise typer.Exit(1)
    except RuntimeError as e:
        err.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)

    if not result.prospects:
        err.print("[yellow]No prospects found. Try broader ICP criteria or --min-score 0[/]")
        raise typer.Exit(0)

    # ── Generate AI narratives ────────────────────────────────────────────────
    if generate and seller:
        err.print(
            f"\n[bold cyan]Generating briefs for {len(result.prospects)} prospects...[/]"
            " (uses Claude Opus 4.6)\n"
        )
        gen = NarrativeGenerator()
        result.prospects = gen.generate_batch(
            result.prospects, result.referral_source, seller
        )

    # ── Output ────────────────────────────────────────────────────────────────
    if output == OutputFormat.html:
        print(export_html(result))
    elif output == OutputFormat.json:
        print(export_json(result))
    elif output == OutputFormat.csv:
        print(export_csv(result))
    else:
        print_result(result, limit=limit)


@app.command()
def config_check():
    """Check that API keys are configured correctly."""
    settings = get_settings()
    import os

    if settings.netrows_api_key:
        err.print("[green]✓[/] NETROWS_API_KEY is set")
    elif settings.pdl_api_key:
        err.print("[green]✓[/] PDL_API_KEY is set")
    elif settings.brightdata_api_key:
        err.print("[green]✓[/] BRIGHTDATA_API_KEY is set")
    else:
        err.print("[red]✗[/] No LinkedIn provider key set (NETROWS_API_KEY, PDL_API_KEY, or BRIGHTDATA_API_KEY)")

    if settings.apollo_api_key:
        err.print("[green]✓[/] APOLLO_API_KEY is set (prospect search)")
    else:
        err.print("[yellow]·[/] APOLLO_API_KEY not set (optional but recommended)")

    if os.environ.get("ANTHROPIC_API_KEY"):
        err.print("[green]✓[/] ANTHROPIC_API_KEY is set (required for --generate)")
    else:
        err.print("[yellow]·[/] ANTHROPIC_API_KEY not set (required only for --generate)")


if __name__ == "__main__":
    app()
