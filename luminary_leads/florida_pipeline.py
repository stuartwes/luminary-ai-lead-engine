from __future__ import annotations

import logging
from datetime import date
from typing import Any

from .clickup import ClickUpClient
from .firecrawl import FirecrawlClient
from .florida import FloridaSunbizClient
from .models import Company, EnrichedLead


LOGGER = logging.getLogger(__name__)


def classify_florida_company(company: Company, config: dict[str, Any]) -> str:
    name = company.name.casefold()
    for blocked in config.get("company_name_terms", []):
        if str(blocked).casefold() in name:
            return ""
    for industry, terms in config["industry_name_terms"].items():
        if any(str(term).casefold() in name for term in terms):
            return industry
    return ""


class FloridaLeadPipeline:
    def __init__(
        self,
        config: dict[str, Any],
        sunbiz: FloridaSunbizClient,
        firecrawl: FirecrawlClient,
        clickup: ClickUpClient,
    ) -> None:
        self.config = config
        self.sunbiz = sunbiz
        self.firecrawl = firecrawl
        self.clickup = clickup

    def run(self, *, today: date | None = None, dry_run: bool = True) -> list[EnrichedLead]:
        daily = self.sunbiz.latest(today=today)
        collection = self.config["collection"]
        allowed_types = {str(item).upper() for item in collection["filing_types"]}
        max_age = int(collection.get("new_company_max_age_days", 10))
        existing = set() if dry_run else self.clickup.existing_company_numbers()

        qualified: list[tuple[Company, str]] = []
        for company in daily.records:
            if company.status.upper() != "A" or company.company_type.upper() not in allowed_types:
                continue
            incorporated = date.fromisoformat(company.incorporated_on)
            age = (daily.file_date - incorporated).days
            if age < 0 or age > max_age:
                continue
            industry = classify_florida_company(company, self.config["targeting"])
            if not industry or company.company_number.upper() in existing:
                continue
            qualified.append((company, industry))
            if len(qualified) >= int(collection["max_candidates_per_run"]):
                break

        LOGGER.info(
            "Florida source %s (%s): %d targeted new-company candidates",
            daily.file_date, daily.transport, len(qualified),
        )
        accepted: list[EnrichedLead] = []
        for company, industry in qualified:
            if len(accepted) >= int(collection["max_review_leads_per_run"]):
                break
            try:
                lead = self.firecrawl.enrich(company, industry)
                if not lead:
                    continue
                self.clickup.create_review_task(lead, dry_run=dry_run)
                accepted.append(lead)
                LOGGER.info("Accepted Florida lead %s (%s)", company.name, company.company_number)
            except Exception:
                LOGGER.exception("Failed to enrich Florida company %s (%s)", company.name, company.company_number)
        return accepted
