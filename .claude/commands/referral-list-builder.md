Find warm LinkedIn referral prospects and push them to a Notion database.

## Step 1 — Collect inputs

Ask the user for the following (one message at a time if not already provided):

1. **LinkedIn URL** of the referral source
2. **Target titles** — who are you trying to reach? (e.g. "VP of Sales", "Head of Revenue")
3. **Your name, title, company, and a one-sentence product description**
4. **Notion parent page URL or ID** — where to create the database (or ask if they want it at workspace root)

## Step 2 — Run the finder

```bash
cd /home/user/claude && python main.py find "[LINKEDIN_URL]" \
  [TITLE_FLAGS] \
  --seller-name "[NAME]" \
  --seller-title "[TITLE]" \
  --seller-company "[COMPANY]" \
  --product "[PRODUCT]" \
  --generate \
  --output json
```

Where `[TITLE_FLAGS]` is one `--title "..."` flag per target title.

## Step 3 — Create the Notion database

Use `notion-create-database` to create a database named **"[Referral Source Name] — Referral Prospects"** under the parent page (or workspace root if none given).

Schema:

```sql
CREATE TABLE (
  "Name" TITLE,
  "Title" RICH_TEXT,
  "Company" RICH_TEXT,
  "LinkedIn" URL,
  "Relationship" RICH_TEXT,
  "Rel. Type" SELECT('Coworker':blue, 'Alumni':purple, 'Past Company':orange, 'Industry Peer':gray, 'Engagement':green),
  "Rel. Score" NUMBER,
  "ICP Score" NUMBER,
  "About Them" MULTI_SELECT,
  "Company Tags" MULTI_SELECT,
  "Status" SELECT('To Contact':yellow, 'Contacted':blue, 'Replied':green, 'Passed':gray)
)
```

## Step 4 — Create one page per prospect

Use `notion-create-pages` with `parent.data_source_id` set to the database's data source ID.

For each prospect, set **properties**:

| Property | Value |
|---|---|
| `Name` | `prospect.full_name` |
| `Title` | `prospect.title` |
| `Company` | `prospect.company` |
| `userDefined:LinkedIn` | `prospect.linkedin_url` |
| `Relationship` | `top_relationship.detail` (first signal's detail field) |
| `Rel. Type` | `top_relationship.relationship_type` capitalized (e.g. "Coworker") |
| `Rel. Score` | `prospect.relationship_score` (number) |
| `ICP Score` | `prospect.icp_score` (number) |
| `About Them` | `narrative.about_them_tags` joined as multi-select values |
| `Company Tags` | `narrative.about_company_tags` joined as multi-select values |
| `Status` | `"To Contact"` |

Set **content** (Notion Markdown) to:

```
## About Them
[narrative.about_them]

## About [Company]
[narrative.about_company]

## Why Them
[narrative.why_connection]

## How [Seller Company] Helps
[narrative.how_product_helps]

## Suggested Message
[narrative.message_to_send]
```

Batch prospects into groups of up to 20 pages per `notion-create-pages` call.

## Step 5 — Confirm

After all pages are created, reply with:
- The Notion database URL
- Count of prospects added
- A quick summary of the top 3 prospects (Name, Title, Company, top relationship signal)

Then add these reminders:

> **Before you go:**
> - The database is private — open it in Notion and click **Share** to invite teammates or publish it.
> - Review each **Suggested Message** before sending. The AI writes a strong first draft, but personalize it with anything you know about the person that isn't in their LinkedIn profile.

## Error handling

- If the profile isn't found, tell the user and ask them to double-check the URL.
- If a prospect has no narrative (--generate wasn't used or generation failed), skip the content body and only set the database properties.
- If no prospects are found, suggest broadening target titles or adding `--min-score 0`.
