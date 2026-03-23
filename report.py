"""
Output formatting for referral finder results.

Supports:
- HTML: rich table matching the example layout (default for --generate mode)
- table: rich terminal table (quick view, no AI narratives required)
- json: full structured JSON
- csv: flat CSV for import into outreach tools
"""

from __future__ import annotations

import csv
import html
import io
import json
from typing import Optional

from rich.console import Console
from rich.table import Table
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

# ── HTML export (primary output for narrated results) ─────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 13px;
    color: #111;
    background: #fff;
    margin: 0;
    padding: 24px;
  }}
  h1 {{
    font-size: 18px;
    font-weight: 700;
    margin: 0 0 4px;
    color: #111;
  }}
  .subtitle {{
    font-size: 13px;
    color: #555;
    margin: 0 0 24px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }}
  col.col-num    {{ width: 36px; }}
  col.col-name   {{ width: 160px; }}
  col.col-li     {{ width: 60px; }}
  col.col-about  {{ width: 200px; }}
  col.col-co     {{ width: 200px; }}
  col.col-why    {{ width: 160px; }}
  col.col-how    {{ width: 200px; }}
  col.col-msg    {{ width: 260px; }}
  thead th {{
    background: #f5f5f5;
    border: 1px solid #e0e0e0;
    padding: 8px 10px;
    text-align: left;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #555;
    white-space: nowrap;
  }}
  tbody td {{
    border: 1px solid #e8e8e8;
    padding: 10px 10px;
    vertical-align: top;
    line-height: 1.5;
  }}
  tbody tr:nth-child(even) td {{ background: #fafafa; }}
  .num {{
    font-size: 18px;
    font-weight: 700;
    color: #bbb;
    text-align: center;
    padding-top: 12px;
  }}
  .name {{ font-weight: 600; font-size: 13px; }}
  .title-company {{ color: #555; font-size: 12px; margin-top: 2px; }}
  .li-link {{
    display: inline-block;
    padding: 3px 8px;
    background: #0077b5;
    color: #fff !important;
    border-radius: 4px;
    text-decoration: none;
    font-size: 11px;
    font-weight: 600;
  }}
  .tags {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 6px;
  }}
  .tag {{
    display: inline-block;
    padding: 2px 7px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.02em;
  }}
  .tag-person {{
    background: #e8f0fe;
    color: #1a56db;
  }}
  .tag-industry {{
    background: #fef3c7;
    color: #92400e;
  }}
  .body-text {{
    color: #333;
    font-size: 12px;
    line-height: 1.55;
  }}
  .msg-header {{
    font-weight: 700;
    font-size: 12px;
    margin-bottom: 6px;
    color: #111;
  }}
  .msg-body {{
    font-size: 12px;
    color: #333;
    line-height: 1.55;
    white-space: pre-wrap;
  }}
</style>
</head>
<body>
<h1>Referral List {source_name}{product_suffix}</h1>
<p class="subtitle">
  {job_count} companies searched &nbsp;·&nbsp;
  {candidate_count} candidates evaluated &nbsp;·&nbsp;
  <strong>{prospect_count} warm prospects</strong>
</p>
<table>
<colgroup>
  <col class="col-num">
  <col class="col-name">
  <col class="col-li">
  <col class="col-about">
  <col class="col-co">
  <col class="col-why">
  <col class="col-how">
  <col class="col-msg">
</colgroup>
<thead>
  <tr>
    <th>#</th>
    <th>Name</th>
    <th>LinkedIn</th>
    <th>About Them</th>
    <th>About the Company</th>
    <th>Why You / Why Them</th>
    <th>How {product_name} Helps</th>
    <th>Message to Send</th>
  </tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>
"""

_ROW_TEMPLATE = """\
<tr>
  <td class="num">{num:02d}</td>
  <td>
    <div class="name">{name}</div>
    <div class="title-company">{title}<br>{company}</div>
  </td>
  <td style="text-align:center; padding-top:12px;">
    {li_link}
  </td>
  <td>
    <div class="tags">{person_tags}</div>
    <div class="body-text">{about_them}</div>
  </td>
  <td>
    <div class="tags">{industry_tags}</div>
    <div class="body-text">{about_company}</div>
  </td>
  <td><div class="body-text">{why_connection}</div></td>
  <td><div class="body-text">{how_helps}</div></td>
  <td>
    <div class="msg-header">{msg_header}</div>
    <div class="msg-body">{msg_body}</div>
  </td>
</tr>"""


def _h(text: str) -> str:
    return html.escape(str(text))


def _tags_html(tags: list[str], css_class: str) -> str:
    return "".join(
        f'<span class="tag {css_class}">{_h(t)}</span>' for t in tags
    )


def _li_link(url: Optional[str]) -> str:
    if not url:
        return '<span style="color:#ccc; font-size:11px;">—</span>'
    return f'<a class="li-link" href="{_h(url)}" target="_blank">View</a>'


def _split_message(message: str) -> tuple[str, str]:
    """Split 'Source → Prospect\nMessage body' into (header, body)."""
    lines = message.strip().split("\n", 1)
    if len(lines) == 2:
        return lines[0].strip(), lines[1].strip()
    return "", message.strip()


def export_html(result: ReferralFinderResult) -> str:
    source = result.referral_source
    seller = result.seller

    product_name = seller.company if seller else "Product"
    product_suffix = f" / {seller.company}" if seller else ""

    rows_html = []
    for i, prospect in enumerate(result.prospects, 1):
        n = prospect.narrative

        if n:
            person_tags = _tags_html(n.about_them_tags, "tag-person")
            about_them = _h(n.about_them)
            industry_tags = _tags_html(n.about_company_tags, "tag-industry")
            about_company = _h(n.about_company)
            why_connection = _h(n.why_connection)
            how_helps = _h(n.how_product_helps)
            msg_header, msg_body = _split_message(n.message_to_send)
        else:
            # Fallback: show relationship signals when no narrative generated
            person_tags = ""
            about_them = _h(f"{prospect.title} at {prospect.company}")
            industry_tags = (
                _tags_html([prospect.industry], "tag-industry") if prospect.industry else ""
            )
            about_company = _h(f"{prospect.company} · {prospect.industry or ''} · {prospect.company_size or ''}")
            top = prospect.top_relationship
            why_connection = _h(top.detail if top else "—")
            how_helps = "—"
            msg_header = ""
            msg_body = "(Run with --generate to get AI-written messages)"

        rows_html.append(_ROW_TEMPLATE.format(
            num=i,
            name=_h(prospect.full_name),
            title=_h(prospect.title),
            company=_h(prospect.company),
            li_link=_li_link(prospect.linkedin_url),
            person_tags=person_tags,
            about_them=about_them,
            industry_tags=industry_tags,
            about_company=about_company,
            why_connection=why_connection,
            how_helps=how_helps,
            msg_header=_h(msg_header),
            msg_body=_h(msg_body),
        ))

    return _HTML_TEMPLATE.format(
        title=f"Referral List — {source.full_name}",
        source_name=_h(source.full_name),
        product_suffix=_h(product_suffix),
        job_count=len(result.companies_searched),
        candidate_count=result.total_candidates_evaluated,
        prospect_count=len(result.prospects),
        product_name=_h(product_name),
        rows="\n".join(rows_html),
    )


# ── Terminal table (quick view) ───────────────────────────────────────────────

def print_result(result: ReferralFinderResult, limit: int = 20) -> None:
    source = result.referral_source

    console.print()
    console.print(
        f"[bold]{source.full_name}[/]  [dim]{source.current_title} @ {source.current_company}[/]"
    )
    console.print(
        f"[dim]Searched {len(result.companies_searched)} companies · "
        f"{result.total_candidates_evaluated} candidates → "
        f"[bold]{len(result.prospects)}[/] warm prospects[/]"
    )
    console.print()

    if not result.prospects:
        console.print("[yellow]No prospects found.[/]")
        return

    table = Table(box=box.ROUNDED, border_style="dim", header_style="bold", padding=(0, 1))
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Name", min_width=20)
    table.add_column("Title / Company", min_width=28)
    table.add_column("Scores", width=18)
    table.add_column("How They Know Each Other", min_width=42)

    for i, prospect in enumerate(result.prospects[:limit], 1):
        top = prospect.top_relationship
        how = "\n".join(
            f"{RELATIONSHIP_EMOJI.get(s.relationship_type, '·')} {s.detail}"
            for s in prospect.relationship_signals[:3]
        ) or "[dim]No direct signals[/]"

        scores = (
            f"[cyan]Rel {prospect.relationship_score:.0f}[/]\n"
            f"[green]ICP {prospect.icp_score:.0f}[/]\n"
            f"[yellow]Tot {prospect.combined_score:.0f}[/]"
        )
        name = (
            f"[link={prospect.linkedin_url}]{prospect.full_name}[/link]"
            if prospect.linkedin_url else prospect.full_name
        )
        table.add_row(
            str(i),
            name,
            f"[bold]{prospect.title}[/]\n[dim]{prospect.company}[/]",
            scores,
            how,
        )

    console.print(table)

    if result.errors:
        console.print()
        for err in result.errors:
            console.print(f"  [yellow]⚠ {err}[/]")


# ── JSON / CSV ────────────────────────────────────────────────────────────────

def export_json(result: ReferralFinderResult) -> str:
    return result.model_dump_json(indent=2)


def export_csv(result: ReferralFinderResult) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "rank", "name", "title", "company", "industry", "location",
        "linkedin_url", "email",
        "relationship_score", "icp_score", "combined_score",
        "relationship_type", "relationship_detail",
        "about_them", "about_company", "why_connection", "how_product_helps", "message",
    ])
    for i, p in enumerate(result.prospects, 1):
        top = p.top_relationship
        n = p.narrative
        writer.writerow([
            i, p.full_name, p.title, p.company, p.industry or "",
            p.location or "", p.linkedin_url or "", p.email or "",
            f"{p.relationship_score:.1f}", f"{p.icp_score:.1f}", f"{p.combined_score:.1f}",
            top.relationship_type.value if top else "",
            top.detail if top else "",
            n.about_them if n else "",
            n.about_company if n else "",
            n.why_connection if n else "",
            n.how_product_helps if n else "",
            n.message_to_send if n else "",
        ])
    return out.getvalue()
