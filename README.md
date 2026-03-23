# LinkedIn Referral Finder

Find warm ICP prospects through a referral source's **actual** relationships — powered by career history and public engagement signals.

Works like Commsor / Swarm / Orbb: instead of guessing who someone knows, it maps their career timeline to surface co-workers, alumni, and people they publicly engage with on LinkedIn.

## How it works

1. **Fetch the referral source's LinkedIn profile** (work history, education)
2. **For each company they've worked at**, search for employees matching your ICP via Apollo.io
3. **Compute relationship strength** based on:
   - Direct co-worker (same company, dates overlap) → strongest signal
   - Public engagement (commented on their LinkedIn posts) → strong
   - Alumni (same school) → moderate
   - Past company (same employer, different years) → weak-moderate
4. **Score and rank** all prospects by relationship strength × ICP fit
5. Output as a rich terminal table, JSON, or CSV

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your API keys
```

### API Keys

> **Note:** Proxycurl shut down in mid-2025 after a LinkedIn federal lawsuit. Use one of the alternatives below.

#### LinkedIn profile data (pick one)

| Provider | Key | Cost | Notes |
|----------|-----|------|-------|
| **Netrows** | `NETROWS_API_KEY` | ~$0.01–0.05/call | Recommended — Proxycurl-compatible API structure |
| **People Data Labs** | `PDL_API_KEY` | ~$0.08/record | 1.5B person records, strong work history data |
| **Bright Data** | `BRIGHTDATA_API_KEY` + `BRIGHTDATA_DATASET_ID` | Enterprise | Most legally defensible (won US scraping cases) |

Set `LINKEDIN_PROVIDER=netrows` (or `pdl` / `brightdata`) in your `.env`.

#### Prospect search

| Provider | Key | Cost | Notes |
|----------|-----|------|-------|
| **Apollo.io** | `APOLLO_API_KEY` | **Free** for search | 210M contacts; people search costs 0 credits |

Apollo's `mixed_people/api_search` endpoint is **free** — credits are only consumed by enrichment (emails/phones), which this tool does not do by default.

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
  --keyword "fintech" \
  --location "San Francisco"

# Export to JSON
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
  -s, --company-size TEXT   1-10 | 11-50 | 51-200 | 201-500 | 501-1000 | 1001-5000 | 5001+
  -l, --location TEXT       Target location — city, state, or country (repeatable)
  -k, --keyword TEXT        Keyword to match in title/company (repeatable)
  --exclude-title TEXT      Exclude prospects with this title (repeatable)
  -o, --output FORMAT       table | json | csv  (default: table)
  -n, --limit INT           Max rows in table output (default: 20)
  --min-score FLOAT         Override minimum relationship score
```

## Scoring

### Relationship score (0–100)

| Signal | Base points | Overlap bonus |
|--------|-------------|---------------|
| Co-worker (overlapping tenure) | 50 | +2/month, max +40 |
| Public engagement (commented on posts) | 30 | — |
| Alumni (same school) | 25 | — |
| Past company (different time) | 15 | — |
| Industry peer | 5 | — |

Multiple signals stack. A co-worker of 2 years who also comments on posts can score 90+.

### ICP score (0–100)

Points awarded for matching: title (40 pts), industry (25 pts), company size (20 pts), location (15 pts), keywords (up to 15 pts).

### Combined score

`combined = relationship_score × 0.6 + icp_score × 0.4`

Results are sorted by combined score descending.

## Architecture

```
main.py                   CLI entry point (typer)
├── finder.py             Orchestration: fetches data, builds prospects, scores
├── linkedin_fetcher.py   Provider-agnostic LinkedIn profile fetcher
│   ├── _NetrowsFetcher   Netrows API backend
│   ├── _PDLFetcher       People Data Labs backend
│   └── _BrightDataFetcher Bright Data backend
├── apollo_fetcher.py     Apollo.io people search (free) + enrichment
├── relationship_analyzer.py  Career overlap + engagement signal scoring
├── models.py             Pydantic data models
├── config.py             Settings (env vars via pydantic-settings)
└── report.py             Rich terminal table + JSON/CSV export
```
