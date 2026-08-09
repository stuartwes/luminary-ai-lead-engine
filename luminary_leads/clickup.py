from __future__ import annotations

import re

import requests

from .models import EnrichedLead


COMPANY_NUMBER_RE = re.compile(r"Company number:\s*([A-Z0-9]+)", re.IGNORECASE)


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
        payload = {
            "name": f'{self.config["task_name_prefix"]}: {lead.company.name} [{lead.company.company_number}]',
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

    @staticmethod
    def _description(lead: EnrichedLead) -> str:
        company = lead.company
        return f"""## Review before outreach

Company number: {company.company_number}
Incorporated: {company.incorporated_on}
Industry segment: {lead.industry}
SIC codes: {', '.join(company.sic_codes)}
Registered postcode: {company.postcode}

Website: {lead.website}
Public corporate email: {lead.email}
Email source: {lead.email_source_url}
Match confidence: {lead.confidence}/100

Compliance controls:
- Public role-based address only
- Source page retained
- Corporate body must be confirmed before sending
- Check the suppression list and privacy notice
- Do not contact until this task is manually approved

Suggested offer: Free New Business AI Launch Plan leading to the Luminary AI Business Lab
Community: https://www.skool.com/luminaryai-business-lab-3937/about
"""
