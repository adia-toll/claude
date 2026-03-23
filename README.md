# LinkedIn Referral Finder

Find warm ICP prospects through a referral source's **actual** relationships — powered by career history and public engagement signals.

Works like Commsor / Swarm / Orbb: instead of guessing who someone knows, it maps their career timeline to surface co-workers, alumni, and people they publicly engage with on LinkedIn.

## How it works

1. **Fetch the referral source's LinkedIn profile** via Proxycurl
2. **For each company they've worked at**, search for current/recent employees matching your ICP
3. **Compute relationship strength** based on:
   - Direct co-worker (same company, dates overlap) → strongest signal
   - Public engagement (commented on their LinkedIn posts) → strong
   - Alumni (same school) → moderate
   - Past company (same employer, different years) → weak-moderate
4. **Score and rank** all prospects by relationship strength × ICP fit
5. Output as a rich terminal table, JSON, or CSV

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env and add your API keys
```

### API Keys

| Key | Where to get it | Required? |
|-----|----------------|-----------|
| `PROXYCURL_API_KEY` | [nubela.co/proxycurl](https://nubela.co/proxycurl) | **Required** — fetches LinkedIn profiles and employee lists |
| `APOLLO_API_KEY` | [app.apollo.io](https://app.apollo.io/#/settings/integrations/api) | Optional — enables richer prospect search with more filters |

> **Proxycurl pricing**: ~$0.01–0.10 per API call. A typical run costs $1–5.
> **Apollo**: Has a free tier (50 exports/month). Paid plans from $49/mo.

## Usage

```bash
# Check config
python main.py config-check

# Find warm prospects for a referral source
python main.py find https://linkedin.com/in/johndoe \
  --title "VP of Sales" \
  --title "Head of Revenue" \
  --industry "SaaS" \
  --company-size "51-200" \
  --company-size "201-500"

# Multiple ICP signals
python main.py find https://linkedin.com/in/janedoe \
  --title "CTO" \
  --title "VP Engineering" \
  --title "Head of Engineering" \
  --keyword "fintech" \
  --location "San Francisco"

# Export to JSON for further processing
python main.py find https://linkedin.com/in/johndoe \
  --title "CEO" \
  --output json > prospects.json

# Export to CSV for outreach tools
python main.py find https://linkedin.com/in/johndoe \
  --title "VP Sales" \
  --output csv > prospects.csv
```

### All options

```
Arguments:
  LINKEDIN_URL    LinkedIn profile URL of the referral source

Options:
  -t, --title TEXT          Target job title (repeatable, partial match)
  -i, --industry TEXT       Target industry (repeatable)
  -s, --company-size TEXT   Company size bucket: 1-10, 11-50, 51-200, 201-500, 501-1000, 1001-5000, 5001+
  -l, --location TEXT       Target location (repeatable)
  -k, --keyword TEXT        Keyword to match in title/company (repeatable)
  --exclude-title TEXT      Exclude prospects with this title (repeatable)
  -o, --output FORMAT       Output: table | json | csv (default: table)
  -n, --limit INT           Max rows in table output (default: 20)
  --min-score FLOAT         Override minimum relationship score
```

## Scoring

### Relationship score (0–100)

| Signal | Base points | Overlap bonus |
|--------|-------------|---------------|
| Co-worker (overlapping tenure) | 50 | +2 per month (max +40) |
| Public engagement (commented on posts) | 30 | — |
| Alumni (same school) | 25 | — |
| Past company (different time) | 15 | — |
| Industry peer | 5 | — |

Multiple signals stack. A co-worker of 2 years who also comments on posts can score 90+.

### ICP score (0–100)

Points awarded for matching: title (40), industry (25), company size (20), location (15), keywords (up to 15).

### Combined score

`combined = relationship_score × 0.6 + icp_score × 0.4`

Results are sorted by combined score descending.

## Architecture

```
main.py               CLI entry point (typer)
├── finder.py         Orchestration: fetches data, builds prospects, scores
├── linkedin_fetcher.py   Proxycurl API: profiles, employees, posts
├── apollo_fetcher.py     Apollo.io API: people search, enrichment
├── relationship_analyzer.py  Career overlap + engagement signal logic
├── models.py         Pydantic data models
├── config.py         Settings (env vars)
└── report.py         Rich terminal table + JSON/CSV export
```

## Output example

```
╭─────────────────────────────────────────────────╮
│ Referral Source                                 │
│ Jane Smith                                      │
│ VP Sales @ Acme Corp                            │
╰─────────────────────────────────────────────────╯
  Searched 6 companies · Evaluated 89 candidates · Found 12 warm prospects

┌────┬──────────────────────┬──────────────────────────────┬─────────────┬────────────────────┬────────────────────────────────────────┐
│  # │ Name                 │ Title / Company              │ Rel.        │ Scores             │ How They Know Each Other               │
├────┼──────────────────────┼──────────────────────────────┼─────────────┼────────────────────┼────────────────────────────────────────┤
│  1 │ John Doe             │ VP of Sales                  │ 🤝 Coworker │ Rel 90             │ 🤝 Both worked at Acme Corp with ~18   │
│    │                      │ TechCo                       │             │ ICP 85             │   months overlap                       │
│    │                      │                              │             │ Tot 88             │ 💬 Commented on Jane's post            │
├────┼──────────────────────┼──────────────────────────────┼─────────────┼────────────────────┼────────────────────────────────────────┤
│  2 │ Sarah Lee            │ Head of Revenue              │ 🎓 Alumni   │ Rel 65             │ 🎓 Both attended Stanford University   │
│    │                      │ StartupXYZ                   │             │ ICP 80             │ 🏢 Both worked at BigCo at diff times  │
│    │                      │                              │             │ Tot 71             │                                        │
└────┴──────────────────────┴──────────────────────────────┴─────────────┴────────────────────┴────────────────────────────────────────┘
```
