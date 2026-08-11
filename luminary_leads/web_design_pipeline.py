from __future__ import annotations

import csv
import hashlib
import logging
from pathlib import Path
from typing import Any

from .clickup import ClickUpClient
from .models import Company, EnrichedLead, PlaceBusiness
from .places import GooglePlacesClient
from .website_audit import WebsiteAuditClient


LOGGER = logging.getLogger(__name__)


class WebDesignLeadPipeline:
    def __init__(
        self,
        config: dict[str, Any],
        places: GooglePlacesClient,
        website_audit: WebsiteAuditClient,
        clickup: ClickUpClient,
    ) -> None:
        self.config = config
        self.places = places
        self.website_audit = website_audit
        self.clickup = clickup

    def run(self, *, dry_run: bool = True) -> list[EnrichedLead]:
        collection = self.config["collection"]
        town = str(self.config["target"]["town"])
        queries = [
            template.format(town=town)
            for template in self.config["target"]["query_templates"]
        ]
        discovered_places = self.places.search_queries(
            queries,
            page_size=int(collection.get("places_page_size", 20)),
            max_pages_per_query=int(collection.get("max_pages_per_query", 1)),
        )
        places: list[PlaceBusiness] = []
        for place in discovered_places:
            rejection = self._place_rejection_reason(place)
            if rejection:
                LOGGER.info("Skipped Google Place %s: %s", place.name or place.place_id, rejection)
            else:
                places.append(place)
        LOGGER.info(
            "Google Places returned %d unique prospects; %d passed listing filters",
            len(discovered_places),
            len(places),
        )
        places = places[: int(collection.get("max_candidates_per_run", 25))]
        existing = set() if dry_run else self.clickup.existing_company_numbers()
        accepted: list[EnrichedLead] = []

        for place in places:
            if len(accepted) >= int(collection.get("max_approved_leads_per_run", 10)):
                break
            try:
                company = self._business_record(place)
                if company.company_number.upper() in existing:
                    continue
                lead = self.website_audit.qualify(
                    company,
                    place,
                    str(self.config["target"]["industry"]),
                    85,
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
        return self._place_rejection_reason(place) == ""

    def _place_rejection_reason(self, place: PlaceBusiness) -> str:
        collection = self.config["collection"]
        if not place.place_id or not place.name or not place.postcode:
            return "missing Google Place ID, business name or postcode"
        if place.business_status and place.business_status != "OPERATIONAL":
            return f"business status is {place.business_status}"
        if place.rating is None or place.rating < float(collection.get("minimum_rating", 4.2)):
            return "Google rating is missing or below the configured minimum"
        if place.review_count < int(collection.get("minimum_review_count", 10)):
            return "Google review count is below the configured minimum"
        town = str(self.config["target"]["town"]).casefold()
        if town not in place.formatted_address.casefold():
            return f"formatted address is outside {self.config['target']['town']}"
        return ""

    @staticmethod
    def _business_record(place: PlaceBusiness) -> Company:
        """Create a stable Google Places identity without requiring incorporation."""
        identifier = hashlib.sha256(place.place_id.encode("utf-8")).hexdigest()[:16].upper()
        return Company(
            company_number=f"GMB{identifier}",
            name=place.name,
            incorporated_on="Not supplied",
            company_type="google_business_profile",
            status=place.business_status or "OPERATIONAL",
            address={"postal_code": place.postcode},
        )


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
