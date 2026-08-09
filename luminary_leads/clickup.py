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

    def approved_leads(self, status: str) -> list[ApprovedLead]:
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
        prefix = f'{self.config["task_name_prefix"]}:'
        company_name = str(task.get("name") or "").removeprefix(prefix).strip()
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
            website=self._field(description, "Website"),
            email=self._field(description, "Public corporate email").lower(),
            email_source_url=self._field(description, "Email source"),
            privacy_notice_url=(
                self._field(description, "Privacy notice", required=False)
                or str(self.config["privacy_notice_url"])
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

    def _description(self, lead: EnrichedLead) -> str:
        company = lead.company
        privacy_notice_url = self.config["privacy_notice_url"]
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
- Check the suppression list
- Do not contact until this task is manually approved

Privacy notice: {privacy_notice_url}

Suggested offer: Free New Business AI Launch Plan leading to the Luminary AI Business Lab
Community: https://www.skool.com/luminaryai-business-lab-3937/about
"""
