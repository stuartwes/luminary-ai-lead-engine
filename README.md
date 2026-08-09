# Luminary AI New Business Lead Engine

This project finds recently incorporated UK corporate businesses, enriches them from public company websites, and creates human-review tasks in ClickUp. It does **not** send email.

## Safety model

- Companies House is the authoritative company source.
- Only configured sectors and postcode areas are processed.
- Firecrawl results must pass a company/website match threshold.
- Only public role-based email addresses on the matched company domain are retained.
- Personal webmail domains and named mailboxes are rejected by default.
- The source page is stored in ClickUp.
- Every lead task is visibly prefixed `[REVIEW REQUIRED]`.
- Existing ClickUp company numbers are skipped.
- Email sending is deliberately absent from this release.

## Accounts and identifiers required

1. Companies House API key: create an application and REST API key in the Companies House Developer Hub.
2. Firecrawl API key.
3. ClickUp personal API token.
4. ClickUp List ID for the lead-review list.

### Find the ClickUp List ID

Open the target list in ClickUp. Its URL normally contains the list identifier, or retrieve it using ClickUp's API. Create the list before enabling the live schedule. Suggested statuses are:

- New / Review required
- Approved for campaign
- Rejected
- Contacted
- Replied
- Do not contact

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
cp .env.example .env
```

Export the four secret values from `.env` in your shell. Do not commit `.env`.

Run tests:

```bash
pytest
```

Run a safe test:

```bash
DRY_RUN=true luminary-leads --dry-run
```

Run live ClickUp creation:

```bash
DRY_RUN=false luminary-leads
```

Each run writes `output/leads.csv` as an audit export.

## GitHub setup

1. Create a new private GitHub repository.
2. Add this project and push it to the default branch.
3. In **Settings → Secrets and variables → Actions**, create:
   - `COMPANIES_HOUSE_API_KEY`
   - `FIRECRAWL_API_KEY`
   - `CLICKUP_API_TOKEN`
   - `CLICKUP_LIST_ID`
4. Open **Actions → Daily Luminary AI leads → Run workflow**.
5. Keep `dry_run` selected for the first test.
6. Check the run log and downloaded CSV.
7. Run manually again with `dry_run` cleared to create ClickUp tasks.

The workflow is scheduled at 07:00 Europe/London. GitHub schedules both possible UTC offsets and the application permits only the correct GMT/BST run.

## Targeting controls

Edit `config/targeting.yaml` to change:

- Incorporation age (14 days by default)
- Daily lead maximum
- SIC code groups
- Postcode areas
- Company-name and SIC exclusions
- Allowed role-address prefixes
- Blocked domains
- Scheduled UK hour

The supplied configuration starts with London, South East England, Essex and Hertfordshire and limits output to 50 review-ready leads per run.

## Before connecting an email sender

Do not enable outreach until all of the following exist:

- Published privacy notice
- Working unsubscribe process
- Central suppression list
- Confirmed corporate-subscriber checks
- Documented legitimate-interests assessment where personal data is involved
- Verified sending domain with SPF, DKIM and DMARC
- Final sender address aligned with the Luminary AI domain
- Approved campaign copy and follow-up limits

`PRIVACY_NOTICE_TEMPLATE.md` provides a starting draft. The sender integration should be a separate, approval-gated workflow that only imports ClickUp tasks in the “Approved for campaign” status.

## Recommended sender identity

Use a real display name and a Luminary AI mailbox, for example:

```text
Display name: Stuart Wesselby
From address: stuart@luminaryai.so
Reply-to: stuart@luminaryai.so
```

The supplied `stuart@stuartwesselby.com` address does not align with the stated `luminaryai.so` sending domain. Resolve that before campaign activation.

## Known limitations

- Companies may not have launched a website 14–30 days after incorporation.
- Registered-office postcodes can point to accountants or formation agents.
- SIC codes are self-reported and can be broad.
- Website matching is deliberately conservative, so some valid companies will be skipped.
- GitHub scheduled jobs can start several minutes late.
- Firecrawl usage depends on account credits and rate limits.
