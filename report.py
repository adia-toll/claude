"""
Rich terminal output and JSON export for referral finder results.
"""

from __future__ import annotations

import json
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from models import ProspectMatch, ReferralFinderResult, RelationshipType


console = Console()

RELATIONSHIP_EMOJI = {
    RelationshipType.COWORKER: "🤝",
    RelationshipType.ALUMNI: "🎓",
    RelationshipType.PAST_COMPANY: "🏢",
    RelationshipType.ENGAGEMENT: "💬",
    RelationshipType.INDUSTRY_PEER: "🌐",
}

RELATIONSHIP_COLOR = {
    RelationshipType.COWORKER: "bold green",
    RelationshipType.ALUMNI: "bold blue",
    RelationshipType.PAST_COMPANY: "yellow",
    RelationshipType.ENGAGEMENT: "bold magenta",
    RelationshipType.INDUSTRY_PEER: "dim",
}


def _score_bar(score: float, width: int = 10) -> str:
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


def print_result(result: ReferralFinderResult, limit: int = 20) -> None:
    source = result.referral_source

    # Header
    console.print()
    console.print(
        Panel(
            f"[bold]{source.full_name}[/]\n"
            f"[dim]{source.current_title} @ {source.current_company}[/]\n"
            f"[link={source.linkedin_url}]{source.linkedin_url}[/link]",
            title="[cyan]Referral Source[/]",
            border_style="cyan",
        )
    )

    console.print(
        f"  [dim]Searched {len(result.companies_searched)} companies · "
        f"Evaluated {result.total_candidates_evaluated} candidates · "
        f"Found [bold]{len(result.prospects)}[/] warm prospects[/]"
    )
    console.print()

    if not result.prospects:
        console.print("[yellow]No prospects found matching ICP criteria.[/]")
        if result.errors:
            for err in result.errors:
                console.print(f"  [red]⚠ {err}[/]")
        return

    # Prospects table
    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        show_header=True,
        header_style="bold",
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Name", min_width=20)
    table.add_column("Title / Company", min_width=30)
    table.add_column("Rel.", min_width=12, justify="center")
    table.add_column("Scores", width=24)
    table.add_column("How They Know Each Other", min_width=40)

    for i, prospect in enumerate(result.prospects[:limit], 1):
        top_signal = prospect.top_relationship
        rel_type = top_signal.relationship_type if top_signal else None
        rel_emoji = RELATIONSHIP_EMOJI.get(rel_type, "·") if rel_type else "·"
        rel_color = RELATIONSHIP_COLOR.get(rel_type, "dim") if rel_type else "dim"
        rel_label = (rel_type.value.replace("_", " ").title() if rel_type else "Unknown")

        scores = (
            f"[cyan]Rel [bold]{prospect.relationship_score:.0f}[/][/]\n"
            f"[green]ICP [bold]{prospect.icp_score:.0f}[/][/]\n"
            f"[yellow]Tot [bold]{prospect.combined_score:.0f}[/][/]"
        )

        how = "\n".join(
            f"{RELATIONSHIP_EMOJI.get(s.relationship_type, '·')} {s.detail}"
            for s in prospect.relationship_signals[:3]
        )
        if not how:
            how = "[dim]No direct signals[/]"

        name_text = prospect.full_name
        if prospect.linkedin_url:
            name_text = f"[link={prospect.linkedin_url}]{prospect.full_name}[/link]"

        table.add_row(
            str(i),
            name_text,
            f"[bold]{prospect.title}[/]\n[dim]{prospect.company}[/]",
            f"[{rel_color}]{rel_emoji} {rel_label}[/]",
            scores,
            how,
        )

    console.print(table)

    if result.errors:
        console.print()
        console.print("[dim]Warnings:[/]")
        for err in result.errors:
            console.print(f"  [yellow]⚠ {err}[/]")


def export_json(result: ReferralFinderResult) -> str:
    """Export result as JSON string."""
    return result.model_dump_json(indent=2)


def export_csv(result: ReferralFinderResult) -> str:
    """Export prospects as CSV."""
    import csv
    import io

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "rank", "name", "title", "company", "industry", "location",
        "linkedin_url", "email",
        "relationship_score", "icp_score", "combined_score",
        "relationship_type", "relationship_detail",
    ])
    for i, p in enumerate(result.prospects, 1):
        top = p.top_relationship
        writer.writerow([
            i,
            p.full_name,
            p.title,
            p.company,
            p.industry or "",
            p.location or "",
            p.linkedin_url or "",
            p.email or "",
            f"{p.relationship_score:.1f}",
            f"{p.icp_score:.1f}",
            f"{p.combined_score:.1f}",
            top.relationship_type.value if top else "",
            top.detail if top else "",
        ])
    return out.getvalue()
