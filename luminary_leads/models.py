from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Company:
    company_number: str
    name: str
    incorporated_on: str
    company_type: str
    status: str
    sic_codes: list[str] = field(default_factory=list)
    address: dict[str, Any] = field(default_factory=dict)

    @property
    def postcode(self) -> str:
        return str(self.address.get("postal_code") or "").upper().strip()


@dataclass(slots=True)
class EnrichedLead:
    company: Company
    website: str
    email: str
    email_source_url: str
    industry: str
    confidence: int
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ApprovedLead:
    task_id: str
    task_description: str
    company_number: str
    company_name: str
    incorporated_on: str
    industry: str
    postcode: str
    website: str
    email: str
    email_source_url: str
    privacy_notice_url: str
