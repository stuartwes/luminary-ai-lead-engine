from __future__ import annotations

from typing import Any

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
