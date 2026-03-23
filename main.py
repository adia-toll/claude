#!/usr/bin/env python3
"""
LinkedIn Referral Finder CLI

Usage:
  python main.py find <linkedin_url> [options]

Examples:
  # Find referral prospects with a specific ICP
  python main.py find https://linkedin.com/in/johndoe \
    --title "VP of Sales" --title "Head of Revenue" \
    --industry "SaaS" \
    --company-size "51-200" --company-size "201-500"

  # Export to JSON
  python main.py find https://linkedin.com/in/janedoe \
    --title "CTO" --title "VP Engineering" \
    --output json > prospects.json

  # Export to CSV
  python main.py find https://linkedin.com/in/janedoe \
    --title "CEO" \
    --output csv > prospects.csv
"""

from __future__ import annotations

import sys
from enum import Enum
from typing import Optional

import typer
from rich.console import Console

from config import get_settings
from finder import ReferralFinder
from models import ICPCriteria
from report import export_csv, export_json, print_result

app = typer.Typer(
    name="referral-finder",
    help="Find warm ICP prospects through a referral source's real relationships.",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console(stderr=True)


class OutputFormat(str, Enum):
    table = "table"
    json = "json"
    csv = "csv"


@app.command()
def find(
    linkedin_url: str = typer.Argument(
        ...,
        help="LinkedIn profile URL of the person whose network you want to map",
    ),
    title: list[str] = typer.Option(
        [],
        "--title", "-t",
        help="Target job title (can be used multiple times). Partial match.",
    ),
    industry: list[str] = typer.Option(
        [],
        "--industry", "-i",
        help="Target industry (can be used multiple times).",
    ),
    company_size: list[str] = typer.Option(
        [],
        "--company-size", "-s",
        help="Target company size: '1-10', '11-50', '51-200', '201-500', '501-1000', '1001-5000', '5001+'",
    ),
    location: list[str] = typer.Option(
        [],
        "--location", "-l",
        help="Target location (city, state, or country). Can be used multiple times.",
    ),
    keyword: list[str] = typer.Option(
        [],
        "--keyword", "-k",
        help="Keyword to match in title or company (can be used multiple times).",
    ),
    exclude_title: list[str] = typer.Option(
        [],
        "--exclude-title",
        help="Exclude prospects with this title (can be used multiple times).",
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.table,
        "--output", "-o",
        help="Output format: table | json | csv",
    ),
    limit: int = typer.Option(
        20,
        "--limit", "-n",
        help="Max prospects to show in table output",
    ),
    min_score: Optional[float] = typer.Option(
        None,
        "--min-score",
        help="Override minimum relationship score (default from config)",
    ),
):
    """
    [bold]Map a person's real network to find warm ICP prospects.[/]

    Analyzes their career history and public engagement to surface people they
    actually know — like Commsor/Swarm, but powered by LinkedIn data.
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

    if not icp.titles and not icp.industries and not icp.keywords:
        console.print(
            "[yellow]⚠ No ICP criteria specified. Results will include all prospects "
            "with relationship signals. Use --title, --industry, or --keyword to narrow down.[/]"
        )

    try:
        with ReferralFinder() as finder:
            result = finder.run(linkedin_url, icp)
    except ValueError as e:
        console.print(f"[red]Configuration error:[/] {e}")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)

    if output == OutputFormat.json:
        print(export_json(result))
    elif output == OutputFormat.csv:
        print(export_csv(result))
    else:
        print_result(result, limit=limit)


@app.command()
def config_check():
    """Check that API keys are configured correctly."""
    settings = get_settings()
    if settings.proxycurl_api_key:
        console.print("[green]✓[/] PROXYCURL_API_KEY is set")
    else:
        console.print("[red]✗[/] PROXYCURL_API_KEY is not set (required)")

    if settings.apollo_api_key:
        console.print("[green]✓[/] APOLLO_API_KEY is set (optional, enables richer search)")
    else:
        console.print("[yellow]·[/] APOLLO_API_KEY is not set (optional)")


if __name__ == "__main__":
    app()
