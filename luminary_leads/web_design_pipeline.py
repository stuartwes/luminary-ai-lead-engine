from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from .clickup import ClickUpClient
from .companies_house import CompaniesHouseClient
from .models import EnrichedLead, PlaceBusiness
from .places import GooglePlacesClient
from .website_audit import WebsiteAuditClient


LOGGER = logging.getLogger(__name__)


class WebDesignLeadPipeline:
    def __init__(
        self,
        config: dict[str, Any],
        places: GooglePlacesClient,
        companies_house: CompaniesHouseClient,
        website_audit: WebsiteAuditClient,
        clickup: ClickUpClient,
    ) -> None:
        self.config = config
        self.places = places
        self.companies_house = companies_house
        self.website_audit = website_audit
        self.clickup = clickup

    def run(self, *, dry_run: bool = True) -> list[EnrichedLead]:
        collection = self.config["collection"]
        town = str(self.config["target"]["town"])
        queries = [
            template.format(town=town)
            for template in self.config["target"]["query_templates"]
        ]
        places = self.places.search_queries(
            queries,
            page_size=int(collection.get("places_page_size", 20)),
            max_pages_per_query=int(collection.get("max_pages_per_query", 1)),
        )
        places = [place for place in places if self._place_qualifies(place)]
        places = places[: int(collection.get("max_candidates_per_run", 25))]
        existing = set() if dry_run else self.clickup.existing_company_numbers()
        accepted: list[EnrichedLead] = []

        for place in places:
            if len(accepted) >= int(collection.get("max_approved_leads_per_run", 10)):
                break
            try:
                corporate = self.companies_house.find_corporate_match(
                    place.name,
                    place.postcode,
                    allowed_types=tuple(collection.get("company_types", ("ltd", "llp"))),
                    minimum_score=int(collection.get("minimum_corporate_match_score", 70)),
                )
                if not corporate:
                    LOGGER.info("Skipped %s: no strong corporate match", place.name)
                    continue
                company, match_score = corporate
                if company.company_number.upper() in existing:
                    continue
                lead = self.website_audit.qualify(
                    company,
                    place,
                    str(self.config["target"]["industry"]),
                    match_score,
                )
                if not lead:
                    continue
                self.clickup.create_review_task(lead, dry_run=dry_run)
                accepted.append(lead)
                existing.add(company.company_number.upper())
                LOGGER.info(
                    "Accepted %s (%s), opportunity score %d",
                    company.name,
                    company.company_number,
                    lead.opportunity_score,
                )
            except Exception:
                LOGGER.exception("Failed to process Google Place %s", place.name)
        return accepted

    def _place_qualifies(self, place: PlaceBusiness) -> bool:
        collection = self.config["collection"]
        if not place.place_id or not place.name or not place.postcode:
            return False
        if place.business_status and place.business_status != "OPERATIONAL":
            return False
        if place.rating is None or place.rating < float(collection.get("minimum_rating", 4.2)):
            return False
        if place.review_count < int(collection.get("minimum_review_count", 10)):
            return False
        town = str(self.config["target"]["town"]).casefold()
        return town in place.formatted_address.casefold()


def write_web_design_csv(leads: list[EnrichedLead], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "company_number",
        "company_name",
        "postcode",
        "website",
        "email",
        "email_source_url",
        "google_place_id",
        "google_rating",
        "google_review_count",
        "website_platform",
        "opportunity_score",
        "primary_issue",
    )
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for lead in leads:
            writer.writerow(
                {
                    "company_number": lead.company.company_number,
                    "company_name": lead.company.name,
                    "postcode": lead.company.postcode,
                    "website": lead.website,
                    "email": lead.email,
                    "email_source_url": lead.email_source_url,
                    "google_place_id": lead.google_place_id,
                    "google_rating": lead.google_rating,
                    "google_review_count": lead.google_review_count,
                    "website_platform": lead.website_platform,
                    "opportunity_score": lead.opportunity_score,
                    "primary_issue": lead.primary_issue,
                }
            )
