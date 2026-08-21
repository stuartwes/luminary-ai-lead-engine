from __future__ import annotations

import logging

from .clickup import ClickUpClient
from .landscaper_lead_engine import LandscaperLead, LandscaperLeadEvaluator
from .places import GooglePlacesClient


LOGGER = logging.getLogger(__name__)


class LandscaperLeadPipeline:
    def __init__(self, config: dict, places: GooglePlacesClient, evaluator: LandscaperLeadEvaluator, clickup: ClickUpClient) -> None:
        self.config = config
        self.places = places
        self.evaluator = evaluator
        self.clickup = clickup

    def run(self, *, dry_run: bool = True) -> list[LandscaperLead]:
        town = str(self.config["target"]["town"])
        collection = self.config["collection"]
        queries = [item.format(town=town) for item in self.config["target"]["query_templates"]]
        discovered = self.places.search_queries(
            queries,
            page_size=int(collection.get("places_page_size", 20)),
            max_pages_per_query=int(collection.get("max_pages_per_query", 1)),
        )
        existing = set() if dry_run else self.clickup.existing_company_numbers()
        accepted: list[LandscaperLead] = []
        for place in discovered[: int(collection.get("max_candidates_per_run", 30))]:
            if len(accepted) >= int(collection.get("max_approved_leads_per_run", 30)):
                break
            if not place.place_id or not place.name or not place.postcode:
                continue
            if place.business_status and place.business_status != "OPERATIONAL":
                continue
            requested = [part.strip().casefold() for part in town.split(",") if part.strip()]
            if not any(part in place.formatted_address.casefold() for part in requested):
                continue
            record_id = LandscaperLeadEvaluator._business_record(place).company_number
            if record_id in existing:
                continue
            try:
                lead = self.evaluator.qualify(place, str(self.config["target"]["industry"]))
                if not lead:
                    continue
                self._create_task(lead, dry_run=dry_run)
                accepted.append(lead)
                existing.add(record_id)
            except Exception:
                LOGGER.exception("Failed to process landscaper %s", place.name)
        return accepted

    def _create_task(self, lead: LandscaperLead, *, dry_run: bool) -> dict:
        cfg = self.config["clickup"]
        task_name = f'{cfg["task_name_prefix"]}: {lead.company.name} [{lead.company.company_number}]'
        services = ", ".join(lead.high_value_services) or "Not detected"
        ideal_customers = ", ".join(lead.ideal_customers or []) or "Not established"
        differentiators = ", ".join(lead.differentiators or []) or "Not established"
        description = f"""## Review before outreach

Lead record ID: {lead.company.company_number}
Campaign ID: {self.config['workflow']['campaign_id']}
Lead type: {lead.lead_type}
Industry segment: {lead.industry}
Business postcode: {lead.company.postcode}

Website: {lead.website or 'No website found'}
Public corporate email: {lead.email}
Email source: {lead.email_source_url}
Email verified: Yes — public business source
Match confidence: {lead.confidence}/100

Lead Score: {lead.lead_score}/100
Lead Class: {lead.lead_class}
Website Status: {lead.website_status}
Sales Angle: {lead.sales_angle}
Primary Opportunity: {lead.primary_opportunity}
Personalised Observation: {lead.personalised_observation}
High Value Service: {services}
AI Confidence: {lead.confidence}/100
Research Mode: {lead.research_mode}
Business Summary: {lead.business_summary or 'Not available'}
Ideal Customers: {ideal_customers}
Specialist Services: {services}
Differentiators: {differentiators}
Recent Activity: {lead.recent_activity or 'Not established'}
Research Evidence: {lead.research_evidence or 'Not available'}
Evidence URL: {lead.evidence_url or 'Not available'}
Research Confidence: {lead.research_confidence}/100
Alternative Outreach Angle: {lead.alternative_angle or 'Not available'}
Approval Status: Pending
Campaign Status: Ready

Compliance controls:
- Public business address only
- Source page retained
- Business identity and website ownership must be checked
- Check the suppression list
- Do not contact until this task is manually approved

Privacy notice: {cfg['privacy_notice_url']}
"""
        payload = {"name": task_name, "description": description, "notify_all": False}
        if dry_run:
            return {"dry_run": True, "payload": payload}
        response = self.clickup.session.post(
            f"{self.clickup.BASE_URL}/list/{self.clickup.list_id}/task",
            headers=self.clickup.headers,
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        return response.json()
