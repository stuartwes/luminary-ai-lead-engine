from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests

from .models import ApprovedLead


class InstantlyClient:
    BASE_URL = "https://api.instantly.ai/api/v2"

    def __init__(
        self,
        api_key: str,
        campaign_id: str,
        config: dict[str, Any],
        session: requests.Session | None = None,
    ) -> None:
        self.campaign_id = campaign_id
        self.config = config
        self.session = session or requests.Session()
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def add_lead(self, lead: ApprovedLead) -> dict:
        blocked_domain = self.blocked_lead_domain(lead)
        if blocked_domain:
            raise ValueError(f"Blocked registry/source domain: {blocked_domain}")
        payload = {
            "campaign_id": self.campaign_id,
            "verify_leads_on_import": bool(self.config.get("verify_leads_on_import", False)),
            "skip_if_in_workspace": bool(self.config.get("skip_if_in_workspace", True)),
            "leads": [
                {
                    "email": lead.email,
                    "company_name": lead.company_name,
                    "website": lead.website,
                    "custom_variables": {
                        "company_number": lead.company_number,
                        "incorporated_on": lead.incorporated_on,
                        "industry": lead.industry,
                        "registered_postcode": lead.postcode,
                        "email_source_url": lead.email_source_url,
                        "privacy_notice_url": lead.privacy_notice_url,
                        "lead_type": lead.lead_type,
                        "website_platform": lead.website_platform,
                        "opportunity_score": lead.opportunity_score,
                        "primary_issue": lead.primary_issue,
                        "google_rating": lead.google_rating,
                        "google_review_count": lead.google_review_count,
                        "google_maps_url": lead.google_maps_url,
                        "lead_score": lead.lead_score,
                        "lead_class": lead.lead_class,
                        "website_status": lead.website_status,
                        "sales_angle": lead.sales_angle,
                        "primary_opportunity": lead.primary_opportunity,
                        "personalised_observation": lead.personalised_observation,
                        "high_value_service": lead.high_value_service,
                    },
                }
            ],
        }
        response = self.session.post(
            f"{self.BASE_URL}/leads/add",
            headers=self.headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def get_campaign(self) -> dict:
        response = self.session.get(
            f"{self.BASE_URL}/campaigns/{self.campaign_id}",
            headers=self.headers,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def update_sequence(self, sequences: list[dict]) -> dict:
        if len(sequences) != 1 or len(sequences[0].get("steps") or []) != 5:
            raise ValueError("The weak-site campaign must contain exactly five email steps")
        response = self.session.patch(
            f"{self.BASE_URL}/campaigns/{self.campaign_id}",
            headers=self.headers,
            json={
                "sequences": sequences,
                "stop_on_reply": True,
                "stop_on_auto_reply": True,
                "link_tracking": False,
                "text_only": True,
                "first_email_text_only": True,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def blocked_lead_domain(self, lead: ApprovedLead) -> str | None:
        blocked = {
            str(domain).casefold().removeprefix("www.")
            for domain in self.config.get("blocked_lead_domains", [])
        }
        email_domain = lead.email.rpartition("@")[2].casefold().removeprefix("www.")
        candidates = [email_domain]
        for url in (lead.website, lead.email_source_url):
            if url:
                candidates.append(urlparse(url).netloc.casefold().removeprefix("www."))
        for candidate in candidates:
            for blocked_domain in blocked:
                if candidate == blocked_domain or candidate.endswith("." + blocked_domain):
                    return blocked_domain
        return None

    @staticmethod
    def outcome(result: dict) -> str:
        if int(result.get("leads_uploaded", 0)) == 1:
            created = result.get("created_leads") or []
            lead_id = str(created[0].get("id") or "") if created else ""
            return f"uploaded (lead ID: {lead_id})" if lead_id else "uploaded"
        if int(result.get("in_blocklist", 0)):
            return "suppressed by Instantly blocklist"
        if int(result.get("duplicated_leads", 0)) or int(result.get("skipped_count", 0)):
            return "already present; skipped"
        if int(result.get("invalid_email_count", 0)):
            return "invalid email; skipped"
        return "not uploaded; review Instantly import result"
