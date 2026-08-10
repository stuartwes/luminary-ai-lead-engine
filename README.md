# Luminary AI New Business Lead Engine

This project finds recently incorporated UK corporate businesses, enriches them from public web sources, and creates human-review tasks in ClickUp. Leads with a matched company website are offered the AI Business Lab; companies with a verified public business email but no official website found are separated as Luminary AI Web Design opportunities. A separate approval-gated workflow can add completed AI Business Lab tasks to Instantly; campaign activation and email sending remain controlled in Instantly.

## Safety model

- Companies House is the authoritative company source.
- Only configured sectors and postcode areas are processed.
- Firecrawl results must pass a company/website match threshold.
- Only public role-based corporate email addresses are retained.
- Email-only leads require strong company/source evidence and are labelled `web_design`.
- Registry aggregators such as JARS, OpenCorporates and Endole are rejected as websites, email sources and campaign leads.
- No-website email leads require the corporate email domain to match the target company's identifying name tokens.
- Personal webmail domains and named mailboxes are rejected by default.
- The source page is stored in ClickUp.
- The published privacy-notice URL is stored with every ClickUp review task.
- Every lead task is visibly prefixed `[REVIEW REQUIRED]`.
- Existing ClickUp company numbers are skipped.
- Only manually approved (`completed`) ClickUp tasks with the configured lead type can enter an Instantly campaign.

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
DRY_RUN=false luminary-leads --max-leads 2
```

Each run writes `output/leads.csv` inside its temporary runner. The public GitHub workflow deliberately does not upload that file as an artifact because it can contain business contact addresses. The ClickUp task remains the private audit record.

## GitHub setup

1. In **Settings → Secrets and variables → Actions**, create:
   - `COMPANIES_HOUSE_API_KEY`
   - `FIRECRAWL_API_KEY`
   - `CLICKUP_API_TOKEN`
   - `CLICKUP_LIST_ID`
2. Open **Actions → Daily Luminary AI leads → Run workflow**.
3. Keep `dry_run` selected for the first test. Manual runs default to a two-lead cap.
4. Check the run log. A dry run does not create ClickUp tasks.
5. Run manually again with `dry_run` cleared to create up to two pilot ClickUp tasks.

This repository is public. Never commit API keys, `.env`, generated lead CSV files or exported ClickUp data.

The workflow is scheduled for 07:00 Europe/London. GitHub schedules both possible UTC offsets, and the application accepts delayed delivery between 07:00 and 10:00 while ClickUp company-number deduplication prevents duplicate tasks.

## Targeting controls

Edit `config/targeting.yaml` to change:

- Incorporation age (14 days by default)
- Daily lead maximum
- SIC code groups
- Postcode areas
- Company-name and SIC exclusions
- Allowed role-address prefixes
- Blocked domains
- Email-search depth for businesses without an official website
- Firecrawl retry attempts and backoff
- Privacy-notice URL included in each ClickUp task
- Scheduled UK hour

The supplied configuration starts with London, South East England, Essex and Hertfordshire and limits output to 50 review-ready leads per run.

## Approved-lead sync to Instantly

Completed ClickUp tasks can be transferred to the configured Instantly campaign with:

```bash
DRY_RUN=true luminary-sync-approved --dry-run
```

The sync uses Instantly API v2, the workspace blocklist and workspace-wide duplicate checking. A final outcome marker is appended to each processed ClickUp task so it cannot be imported repeatedly.

The AI Business Lab campaign is restricted to `lead_type: ai_business_lab`. The separate Luminary AI Web Design campaign is restricted to `lead_type: web_design`. The hourly workflow processes both routes independently, so approving one type cannot place it into the other campaign.

Run either route locally with:

```bash
luminary-sync-approved --lead-type ai_business_lab
luminary-sync-approved --lead-type web_design
```

The `Sync approved leads to Instantly` workflow runs manually in dry-run mode by default. Its hourly schedule remains disabled until the repository variable `INSTANTLY_SYNC_ENABLED` is set to `true`. Enable that variable only after the campaign copy, sender accounts, schedule and unsubscribe handling are ready.

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

- Companies may not have launched a website 14 days after incorporation; the secondary public-email search can still create a separately labelled web-design opportunity.
- Registered-office postcodes can point to accountants or formation agents.
- SIC codes are self-reported and can be broad.
- Website matching is deliberately conservative, so some valid companies will be skipped.
- GitHub scheduled jobs can start several minutes late.
- Firecrawl usage depends on account credits and rate limits.
