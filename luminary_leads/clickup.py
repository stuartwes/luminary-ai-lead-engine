from __future__ import annotations

import re

import requests

from .models import ApprovedLead, EnrichedLead


COMPANY_NUMBER_RE = re.compile(r"Company number:\s*([A-Z0-9]+)", re.IGNORECASE)
INSTANTLY_SYNC_MARKER = "Instantly sync outcome:"


class ClickUpClient:
    BASE_URL = "https://api.clickup.com/api/v2"

    def __init__(self, api_token: str, list_id: str, config: dict, session: requests.Session | None = None) -> None:
        self.list_id = list_id
        self.config = config
        self.session = session or requests.Session()
        self.headers = {"Authorization": api_token, "Content-Type": "application/json"}

    def existing_company_numbers(self) -> set[str]:
        page = 0
        numbers: set[str] = set()
        while True:
            response = self.session.get(
                f"{self.BASE_URL}/list/{self.list_id}/task",
                headers=self.headers,
                params={"page": page, "include_closed": "true", "subtasks": "true"},
                timeout=45,
            )
            response.raise_for_status()
            tasks = response.json().get("tasks", [])
            for task in tasks:
                text = "\n".join((str(task.get("name") or ""), str(task.get("description") or "")))
                match = COMPANY_NUMBER_RE.search(text)
                if match:
                    numbers.add(match.group(1).upper())
            if len(tasks) < 100:
                break
            page += 1
        return numbers

    def create_review_task(self, lead: EnrichedLead, *, dry_run: bool = False) -> dict:
        description = self._description(lead)
        prefix = (
            self.config.get("web_design_task_name_prefix", "[REVIEW REQUIRED] Web Design lead")
            if not lead.website or lead.lead_type in {"web_design", "web_design_weak_site"}
            else self.config["task_name_prefix"]
        )
        payload = {
            "name": f"{prefix}: {lead.company.name} [{lead.company.company_number}]",
            "description": description,
            "notify_all": False,
        }
        if dry_run:
            return {"dry_run": True, "payload": payload}
        response = self.session.post(
            f"{self.BASE_URL}/list/{self.list_id}/task",
            headers=self.headers,
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        return response.json()

    def approved_leads(
        self, status: str, required_lead_type: str | None = None
    ) -> list[ApprovedLead]:
        page = 0
        leads: list[ApprovedLead] = []
        while True:
            response = self.session.get(
                f"{self.BASE_URL}/list/{self.list_id}/task",
                headers=self.headers,
                params={
                    "page": page,
                    "include_closed": "true",
                    "subtasks": "true",
                    "statuses[]": status,
                },
                timeout=45,
            )
            response.raise_for_status()
            tasks = response.json().get("tasks", [])
            for task in tasks:
                task_status = str((task.get("status") or {}).get("status") or "")
                description = str(task.get("description") or "")
                if task_status.casefold() != status.casefold() or INSTANTLY_SYNC_MARKER in description:
                    continue
                lead_type = (
                    self._field(description, "Lead type", required=False)
                    or "ai_business_lab"
                )
                if required_lead_type and lead_type.casefold() != required_lead_type.casefold():
                    continue
                leads.append(self._approved_lead(task))
            if len(tasks) < 100:
                break
            page += 1
        return leads

    def mark_instantly_synced(self, lead: ApprovedLead, outcome: str, campaign_id: str) -> None:
        marker = (
            f"\n\n{INSTANTLY_SYNC_MARKER} {outcome}\n"
            f"Instantly campaign ID: {campaign_id}\n"
        )
        response = self.session.put(
            f"{self.BASE_URL}/task/{lead.task_id}",
            headers=self.headers,
            json={"description": lead.task_description.rstrip() + marker},
            timeout=45,
        )
        response.raise_for_status()

    def _approved_lead(self, task: dict) -> ApprovedLead:
        description = str(task.get("description") or "")
        company_number = self._field(description, "Company number")
        prefixes = (
            self.config["task_name_prefix"],
            self.config.get("web_design_task_name_prefix", "[REVIEW REQUIRED] Web Design lead"),
        )
        company_name = str(task.get("name") or "").strip()
        for task_prefix in prefixes:
            company_name = company_name.removeprefix(f"{task_prefix}:").strip()
        company_name = re.sub(
            rf"\s*\[{re.escape(company_number)}\]\s*$", "", company_name
        ).strip()
        return ApprovedLead(
            task_id=str(task["id"]),
            task_description=description,
            company_number=company_number,
            company_name=company_name,
            incorporated_on=self._field(description, "Incorporated"),
            industry=self._field(description, "Industry segment"),
            postcode=self._field(description, "Registered postcode"),
            website=(
                ""
                if self._field(description, "Website").casefold() == "no website found"
                else self._field(description, "Website")
            ),
            email=self._field(description, "Public corporate email").lower(),
            email_source_url=self._field(description, "Email source"),
            privacy_notice_url=(
                self._field(description, "Privacy notice", required=False)
                or str(self.config["privacy_notice_url"])
            ),
            lead_type=(
                self._field(description, "Lead type", required=False)
                or "ai_business_lab"
            ),
            website_platform=self._field(
                description, "Website platform", required=False
            ),
            opportunity_score=self._integer_field(
                description, "Opportunity score"
            ),
            primary_issue=self._field(
                description, "Primary website issue", required=False
            ),
            google_rating=self._field(
                description, "Google rating", required=False
            ),
            google_review_count=self._integer_field(
                description, "Google review count"
            ),
            google_maps_url=self._field(
                description, "Google Maps URL", required=False
            ),
        )

    @staticmethod
    def _field(description: str, label: str, *, required: bool = True) -> str:
        match = re.search(rf"^{re.escape(label)}:\s*(.+?)\s*$", description, re.MULTILINE)
        if not match:
            if required:
                raise ValueError(f"ClickUp task is missing required field: {label}")
            return ""
        return match.group(1).strip()

    @classmethod
    def _integer_field(cls, description: str, label: str) -> int:
        value = cls._field(description, label, required=False)
        match = re.search(r"\d+", value)
        return int(match.group(0)) if match else 0

    def _description(self, lead: EnrichedLead) -> str:
        company = lead.company
        privacy_notice_url = self.config["privacy_notice_url"]
        lead_type = lead.lead_type or (
            self.config.get("website_lead_type", "ai_business_lab")
            if lead.website
            else self.config.get("no_website_lead_type", "web_design")
        )
        website = lead.website or "No website found"
        suggested_offer = (
            self.config.get(
                "website_suggested_offer",
                "Free New Business AI Launch Plan leading to the Luminary AI Business Lab",
            )
            if lead.website
            else self.config.get(
                "no_website_suggested_offer",
                "Luminary AI Web Design — new-business website design",
            )
        )
        market = self.config.get("market", "UK")
        source = self.config.get("company_source", "Companies House")
        offer_link = (
            self.config.get(
                "website_offer_link",
                "Community: https://www.skool.com/luminaryai-business-lab-3937/about",
            )
            if lead.website
            else self.config.get(
                "no_website_offer_link",
                "Web design: https://luminaryaiwebdesign.co.uk/",
            )
        )
        return f"""## Review before outreach

Company number: {company.company_number}
Incorporated: {company.incorporated_on}
Market: {market}
Company source: {source}
Industry segment: {lead.industry}
SIC codes: {', '.join(company.sic_codes) or 'Not supplied by source'}
Registered postcode: {company.postcode}
Lead type: {lead_type}

Website: {website}
Public corporate email: {lead.email}
Email source: {lead.email_source_url}
Match confidence: {lead.confidence}/100

Compliance controls:
- Public role-based address only
- Source page retained
- Corporate body must be confirmed before sending
- Check the suppression list
- Do not contact until this task is manually approved
{('- US outreach must include an accurate sender identity, physical postal address and working opt-out' if market.startswith('US') else '')}

Privacy notice: {privacy_notice_url}

Suggested offer: {suggested_offer}
{offer_link}
{self._website_audit_description(lead)}
"""

    @staticmethod
    def _website_audit_description(lead: EnrichedLead) -> str:
        if not (
            lead.google_place_id
            or lead.opportunity_score
            or lead.primary_issue
            or lead.audit_signals
        ):
            return ""
        rating = (
            f"{lead.google_rating:.1f}"
            if lead.google_rating is not None
            else "Not supplied"
        )
        signals = "\n".join(f"- {item}" for item in lead.audit_signals) or "- None"
        return f"""
Website opportunity audit:
Google Place ID: {lead.google_place_id}
Google Maps URL: {lead.google_maps_url or 'Not supplied'}
Google rating: {rating}
Google review count: {lead.google_review_count}
Website platform: {lead.website_platform or 'Unknown'}
Opportunity score: {lead.opportunity_score}/100
Primary website issue: {lead.primary_issue or 'Not supplied'}
Audit signals:
{signals}
"""
