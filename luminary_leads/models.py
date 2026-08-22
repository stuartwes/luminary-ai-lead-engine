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
    lead_type: str = ""
    google_place_id: str = ""
    google_maps_url: str = ""
    google_rating: float | None = None
    google_review_count: int = 0
    website_platform: str = ""
    opportunity_score: int = 0
    primary_issue: str = ""
    audit_signals: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PlaceBusiness:
    place_id: str
    name: str
    formatted_address: str
    website: str = ""
    google_maps_url: str = ""
    phone: str = ""
    rating: float | None = None
    review_count: int = 0
    business_status: str = ""
    types: list[str] = field(default_factory=list)

    @property
    def postcode(self) -> str:
        import re

        match = re.search(
            r"\b(?:GIR\s?0AA|(?:[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]?|[A-PR-UWYZ]\d[A-HJKSTUW])\s?\d[ABD-HJLNP-UW-Z]{2})\b",
            self.formatted_address.upper(),
        )
        return match.group(0).upper().strip() if match else ""


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
    lead_type: str = "ai_business_lab"
    website_platform: str = ""
    opportunity_score: int = 0
    primary_issue: str = ""
    google_rating: str = ""
    google_review_count: int = 0
    google_maps_url: str = ""
    lead_score: int = 0
    lead_class: str = ""
    website_status: str = ""
    sales_angle: str = ""
    primary_opportunity: str = ""
    personalised_observation: str = ""
    high_value_service: str = ""
    research_mode: str = ""
    business_summary: str = ""
    ideal_customers: str = ""
    specialist_services: str = ""
    differentiators: str = ""
    recent_activity: str = ""
    research_evidence: str = ""
    evidence_url: str = ""
    research_confidence: int = 0
    alternative_outreach_angle: str = ""
    personalised_subject_line: str = ""
    icebreaker: str = ""
    relevance_bridge: str = ""
    personalised_value_proposition: str = ""
    personalised_cta: str = ""
    target_customer_angle: str = ""
    personalisation_evidence: str = ""
    personalisation_evidence_url: str = ""
    personalisation_confidence: int = 0
    personalisation_rejection_reason: str = ""
