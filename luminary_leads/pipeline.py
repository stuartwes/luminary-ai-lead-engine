from __future__ import annotations

import csv
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .clickup import ClickUpClient
from .companies_house import CompaniesHouseClient
from .firecrawl import FirecrawlClient
from .models import EnrichedLead
from .targeting import flatten_industries, qualify_company


LOGGER = logging.getLogger(__name__)


class LeadPipeline:
    def __init__(
        self,
        config: dict[str, Any],
        companies_house: CompaniesHouseClient,
        firecrawl: FirecrawlClient,
        clickup: ClickUpClient,
    ) -> None:
        self.config = config
        self.companies_house = companies_house
        self.firecrawl = firecrawl
        self.clickup = clickup

    def run(self, *, today: date | None = None, dry_run: bool = True) -> list[EnrichedLead]:
        today = today or date.today()
        collection = self.config["collection"]
        incorporation_date = today - timedelta(days=int(collection["days_after_incorporation"]))
        sic_map = flatten_industries(self.config)
        companies = self.companies_house.advanced_search(
            incorporated_from=incorporation_date,
            incorporated_to=incorporation_date,
            sic_codes=sic_map.keys(),
            company_types=collection["company_types"],
            company_statuses=collection["company_statuses"],
        )
        existing = set() if dry_run else self.clickup.existing_company_numbers()
        qualified = []
        for company in companies:
            accepted, industry = qualify_company(company, self.config)
            if accepted and company.company_number.upper() not in existing:
                qualified.append((company, industry))
        qualified = qualified[: int(collection["max_candidates_per_run"])]

        approved: list[EnrichedLead] = []
        for company, industry in qualified:
            if len(approved) >= int(collection["max_approved_leads_per_run"]):
                break
            try:
                lead = self.firecrawl.enrich(company, industry)
                if not lead:
                    continue
                self.clickup.create_review_task(lead, dry_run=dry_run)
                approved.append(lead)
                LOGGER.info("Accepted %s (%s)", company.name, company.company_number)
            except Exception:
                LOGGER.exception("Failed to enrich %s (%s)", company.name, company.company_number)
        return approved


def write_csv(leads: list[EnrichedLead], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "company_number", "company_name", "incorporated_on", "industry", "sic_codes",
        "postcode", "website", "email", "email_source_url", "confidence",
    ]
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for lead in leads:
            writer.writerow({
                "company_number": lead.company.company_number,
                "company_name": lead.company.name,
                "incorporated_on": lead.company.incorporated_on,
                "industry": lead.industry,
                "sic_codes": ",".join(lead.company.sic_codes),
                "postcode": lead.company.postcode,
                "website": lead.website,
                "email": lead.email,
                "email_source_url": lead.email_source_url,
                "confidence": lead.confidence,
            })
