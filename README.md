# Luminary AI New Business Lead Engine

This project finds recently incorporated UK corporate businesses, enriches them from public web sources, and creates human-review tasks in ClickUp. It also contains a separate Florida pilot sourced from the official Sunbiz daily corporate file and a Google Places pilot that identifies established local businesses with demonstrably weak websites. Leads with a matched company website are offered the AI Business Lab; companies with a verified public business email but no official website found are separated as Luminary AI Web Design opportunities. Separate approval-gated workflows can add completed UK tasks to Instantly; campaign activation and email sending remain controlled in Instantly.

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
- Florida tasks use distinct `us_fl_*` lead types and cannot enter either UK Instantly campaign.
- Weak-website tasks use `web_design_weak_site`, a separate ClickUp List and a separate Instantly campaign.
- The weak-website workflow accepts both incorporated businesses and sole traders. A stable Google Place ID, Google-listed website, same-domain role email and manual ClickUp approval provide its identity controls.
- A DIY platform is an audit signal, not automatic proof of a poor website. A site must meet the configured evidence score and expose a public role-based address on its own domain.

## Accounts and identifiers required

1. Companies House API key: create an application and REST API key in the Companies House Developer Hub.
2. Firecrawl API key.
3. ClickUp personal API token.
4. ClickUp List ID for the lead-review list.
5. Google Places API key for the weak-website workflow.
6. A separate ClickUp List and Instantly campaign for weak-site prospects.

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

## Daily local weak-website search

The `Daily local weak-website search` workflow uses Google Places Text Search to find established gardening, landscaping and garden-design businesses. It requests the Google-listed website directly, audits the site with Firecrawl and creates only evidence-backed ClickUp review tasks. Companies House is not used by this workflow, so suitable sole traders are not excluded.

The supplied configuration requires a 4.2+ Google rating, at least 5 reviews, a public business-domain email from the official site and a website opportunity score of at least 40. Wix, Squarespace and other DIY platforms contribute to the score but never qualify a business by themselves.

Add this GitHub Actions secret before running the pilot:

- `GOOGLE_PLACES_API`

The ClickUp board from `90121956512/v/b/6-901220291430-2` is configured with List ID `901220291430`, and Instantly campaign `2869b5e3-746b-4694-9433-9cd076472fe8` is configured for `web_design_weak_site` leads. The workflow uses the existing `FIRECRAWL_API` and `CLICK_UP_TOKEN` secrets. It is manual-only and defaults to dry-run mode with a two-lead cap. The location field has no default and must be entered for every run, preventing a previous town from being reused accidentally. It accepts a town, city or London suburb:

```bash
DRY_RUN=true luminary-web-design-leads --location Clapham --max-leads 2
```

To change sectors or qualification thresholds, edit `config/web_design.yaml`. Dry runs audit real public data but do not create ClickUp tasks. The campaign copy deliberately does not use a location merge field.

### Five-email weak-site sequence

The `Configure weak-site Instantly sequence` workflow previews the proposed sequence by default. Run it with `apply` selected to replace the campaign copy with the five-email sequence in `config/instantly_weak_site_sequence.yaml`. The sequence leads with the visible contrast between a conventional site and a motion-led Luminary site, then explains the AI-readable and SEO-ready structure beneath it. The free website audit is the conversational first step, with a separate book-a-call option.

Applying the sequence does not activate the campaign or send email. ClickUp tasks still require manual approval, and the Instantly sync remains separately gated.

## Florida pilot

The `Florida new-business pilot` workflow downloads Florida Division of Corporations daily corporate data from the state's public Sunbiz file service. It accepts newly formed active Florida LLCs (`FLAL`) and domestic profit corporations (`DOMP`), applies business-name signals for the configured target sectors, then uses the same conservative Firecrawl website/email matching and ClickUp review process.

Sunbiz does not provide NAICS industry codes in this daily file, so Florida targeting is based on explicit terms in the legal business name. The run caps output at 50 email-qualified tasks and may produce fewer rather than admitting weak matches. Registry, filing-service and directory domains are blocked. Sunbiz document numbers are stored with a `USFL` prefix to prevent collisions with UK company numbers.

The scheduled pilot runs at 16:00 UTC Monday-Friday and falls back through the last 10 days for the latest available Florida work-day file. Manual runs default to dry-run mode and two leads:

```bash
DRY_RUN=true luminary-florida-leads --dry-run --max-leads 2
```

Florida leads remain ClickUp-review-only. Before any US sending is enabled, create separate US Instantly campaigns and confirm CAN-SPAM controls, including accurate sender details, a valid physical postal address, and a working opt-out. Do not reuse the UK campaign IDs for Florida leads.

Florida Firecrawl requests are deliberately paced. HTTP 429 responses honour
Firecrawl's `Retry-After` header and otherwise use a longer exponential backoff,
jitter and a maximum wait. This prevents a temporary plan limit from causing the
pipeline to skip through hundreds of otherwise suitable companies.

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

The AI Business Lab campaign is restricted to `lead_type: ai_business_lab`. The new-business web-design campaign is restricted to `lead_type: web_design`, while the weak-site campaign is restricted to `lead_type: web_design_weak_site`. The hourly workflow processes all routes independently, so approving one type cannot place it into another campaign.

Run either route locally with:

```bash
luminary-sync-approved --lead-type ai_business_lab
luminary-sync-approved --lead-type web_design
luminary-sync-approved --lead-type web_design_weak_site
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
