Find warm LinkedIn referral prospects through a referral source's real career network.

## Steps

Ask the user for the following, one message at a time if not already provided:

1. **LinkedIn URL** of the referral source (the person whose network you want to map)
2. **Target titles** — who are you trying to reach? (e.g. "VP of Sales", "Head of Revenue", "Director of Marketing")
3. **Your name, title, company, and a one-sentence product description** — used to generate personalized intro messages

Once you have all inputs, run the finder:

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

## Displaying results

Parse the JSON output and display each prospect as a clean card:

**Name — Title @ Company**
- Why they're warm: [relationship signals]
- About them: [narrative.about_them]
- Why them: [narrative.why_them]
- Suggested message:
  > [narrative.suggested_message]

Show all prospects, then ask: "Would you like the full HTML report or a CSV download?"

If yes, re-run with `--output html` or `--output csv` and save to a file, then provide the path.

## Error handling

- If the profile isn't found, tell the user and ask them to double-check the URL is a public LinkedIn profile.
- If no prospects are found, suggest broadening the target titles or trying `--min-score 0`.
