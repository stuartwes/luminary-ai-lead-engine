from datetime import date

from luminary_leads.clickup import ClickUpClient
from luminary_leads.companies_house import CompaniesHouseClient
from luminary_leads.models import Company, EnrichedLead


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.last_request = None

    def get(self, url, **kwargs):
        self.last_request = (url, kwargs)
        return FakeResponse(self.payload)

    def put(self, url, **kwargs):
        self.last_request = (url, kwargs)
        return FakeResponse(self.payload)


def test_companies_house_contract_and_mapping():
    session = FakeSession({
        "items": [{
            "company_number": "12345678",
            "company_name": "BRIGHT AGENCY LTD",
            "date_of_creation": "2026-07-20",
            "company_type": "ltd",
            "company_status": "active",
            "sic_codes": ["73110"],
            "registered_office_address": {"postal_code": "SE1 2AA"},
        }]
    })
    client = CompaniesHouseClient("secret", session=session)
    result = client.advanced_search(date(2026, 7, 20), date(2026, 7, 20), ["73110"], ["ltd"], ["active"])
    assert result[0].company_number == "12345678"
    assert result[0].postcode == "SE1 2AA"
    _, request = session.last_request
    assert request["params"]["incorporated_from"] == "2026-07-20"
    assert request["auth"] == ("secret", "")


def test_clickup_dry_run_contains_audit_fields_and_no_secret():
    company = Company("12345678", "Bright Agency Ltd", "2026-07-20", "ltd", "active", ["73110"], {"postal_code": "SE1 2AA"})
    lead = EnrichedLead(company, "https://brightagency.co.uk", "hello@brightagency.co.uk", "https://brightagency.co.uk/contact", "marketing", 85)
    privacy_url = "https://luminaryaibusiness.com/luminaryaibusiness-privacy.html"
    client = ClickUpClient(
        "secret",
        "list-id",
        {
            "task_name_prefix": "[REVIEW REQUIRED] AI Lab lead",
            "privacy_notice_url": privacy_url,
        },
    )
    result = client.create_review_task(lead, dry_run=True)
    payload = result["payload"]
    assert "[REVIEW REQUIRED]" in payload["name"]
    assert "Company number: 12345678" in payload["description"]
    assert "Email source: https://brightagency.co.uk/contact" in payload["description"]
    assert f"Privacy notice: {privacy_url}" in payload["description"]
    assert "secret" not in str(payload)


def test_clickup_returns_only_completed_unsynced_leads():
    privacy_url = "https://luminaryaibusiness.com/luminaryaibusiness-privacy.html"
    description = f"""Company number: 12345678
Incorporated: 2026-07-20
Industry segment: marketing
Registered postcode: SE1 2AA
Website: https://brightagency.co.uk
Public corporate email: hello@brightagency.co.uk
Email source: https://brightagency.co.uk/contact
"""
    session = FakeSession({
        "tasks": [{
            "id": "task-1",
            "name": "[REVIEW REQUIRED] AI Lab lead: Bright Agency Ltd [12345678]",
            "description": description,
            "status": {"status": "completed"},
        }]
    })
    client = ClickUpClient(
        "secret",
        "list-id",
        {
            "task_name_prefix": "[REVIEW REQUIRED] AI Lab lead",
            "privacy_notice_url": privacy_url,
        },
        session=session,
    )

    leads = client.approved_leads("completed")

    assert len(leads) == 1
    assert leads[0].company_name == "Bright Agency Ltd"
    assert leads[0].email == "hello@brightagency.co.uk"
    assert leads[0].privacy_notice_url == privacy_url


def test_clickup_sync_marker_prevents_duplicate_processing():
    session = FakeSession({
        "tasks": [{
            "id": "task-1",
            "name": "lead",
            "description": "Instantly sync outcome: uploaded",
            "status": {"status": "completed"},
        }]
    })
    client = ClickUpClient(
        "secret",
        "list-id",
        {"task_name_prefix": "[REVIEW REQUIRED] AI Lab lead", "privacy_notice_url": "x"},
        session=session,
    )

    assert client.approved_leads("completed") == []


def test_web_design_lead_is_labelled_and_excluded_from_ai_campaign():
    company = Company(
        "87654321",
        "New Trade Ltd",
        "2026-07-20",
        "ltd",
        "active",
        ["43210"],
        {"postal_code": "SS1 1AA"},
    )
    lead = EnrichedLead(
        company,
        "",
        "info@newtrade.co.uk",
        "https://directory.example/new-trade",
        "trades",
        85,
    )
    client = ClickUpClient(
        "secret",
        "list-id",
        {
            "task_name_prefix": "[REVIEW REQUIRED] AI Lab lead",
            "web_design_task_name_prefix": "[REVIEW REQUIRED] Web Design lead",
            "privacy_notice_url": "https://example.com/privacy",
        },
    )

    payload = client.create_review_task(lead, dry_run=True)["payload"]

    assert payload["name"].startswith("[REVIEW REQUIRED] Web Design lead")
    assert "Lead type: web_design" in payload["description"]
    assert "Website: No website found" in payload["description"]
    assert "Luminary AI Web Design" in payload["description"]


def test_ai_campaign_filter_skips_completed_web_design_lead():
    session = FakeSession({
        "tasks": [{
            "id": "task-web",
            "name": "[REVIEW REQUIRED] Web Design lead: New Trade Ltd [87654321]",
            "description": """Company number: 87654321
Lead type: web_design
""",
            "status": {"status": "completed"},
        }]
    })
    client = ClickUpClient(
        "secret",
        "list-id",
        {"task_name_prefix": "[REVIEW REQUIRED] AI Lab lead", "privacy_notice_url": "x"},
        session=session,
    )

    assert client.approved_leads(
        "completed", required_lead_type="ai_business_lab"
    ) == []


def test_florida_task_uses_isolated_us_lead_type_and_compliance_note():
    company = Company(
        "USFLL26000123456",
        "Bright Marketing LLC",
        "2026-08-07",
        "FLAL",
        "A",
        address={"postal_code": "33101"},
    )
    lead = EnrichedLead(
        company,
        "https://brightmarketing.com",
        "hello@brightmarketing.com",
        "https://brightmarketing.com/contact",
        "marketing",
        85,
    )
    client = ClickUpClient(
        "secret",
        "list-id",
        {
            "task_name_prefix": "[REVIEW REQUIRED] Florida AI Lab lead",
            "privacy_notice_url": "https://example.com/privacy",
            "market": "US-FL",
            "company_source": "Florida Sunbiz",
            "website_lead_type": "us_fl_ai_business_lab",
        },
    )

    payload = client.create_review_task(lead, dry_run=True)["payload"]

    assert "Lead type: us_fl_ai_business_lab" in payload["description"]
    assert "Market: US-FL" in payload["description"]
    assert "physical postal address and working opt-out" in payload["description"]


def test_weak_website_task_contains_specific_audit_evidence():
    company = Company(
        "12345678",
        "Sevenoaks Garden Design Ltd",
        "2018-01-01",
        "ltd",
        "active",
        ["71112"],
        {"postal_code": "TN13 1AA"},
    )
    lead = EnrichedLead(
        company,
        "https://sevenoaksgardens.co.uk",
        "hello@sevenoaksgardens.co.uk",
        "https://sevenoaksgardens.co.uk/contact",
        "landscape_and_garden_design",
        90,
        lead_type="web_design_weak_site",
        google_place_id="place-1",
        google_maps_url="https://maps.google.com/example",
        google_rating=4.8,
        google_review_count=65,
        website_platform="Wix",
        opportunity_score=75,
        primary_issue="No project portfolio detected",
        audit_signals=["No project gallery detected"],
    )
    client = ClickUpClient(
        "secret",
        "list-id",
        {
            "task_name_prefix": "[REVIEW REQUIRED] Web Design Audit",
            "web_design_task_name_prefix": "[REVIEW REQUIRED] Web Design Audit",
            "privacy_notice_url": "https://example.com/privacy",
        },
    )

    payload = client.create_review_task(lead, dry_run=True)["payload"]

    assert payload["name"].startswith("[REVIEW REQUIRED] Web Design Audit")
    assert "Lead type: web_design_weak_site" in payload["description"]
    assert "Opportunity score: 75/100" in payload["description"]
    assert "Website platform: Wix" in payload["description"]
    assert "Google review count: 65" in payload["description"]


def test_clickup_parses_weak_site_fields_for_instantly_personalisation():
    session = FakeSession(
        {
            "tasks": [
                {
                    "id": "task-weak",
                    "name": "[REVIEW REQUIRED] Web Design Audit: Sevenoaks Garden Design Ltd [12345678]",
                    "description": """Company number: 12345678
Incorporated: 2018-01-01
Industry segment: landscape_and_garden_design
Registered postcode: TN13 1AA
Lead type: web_design_weak_site
Website: https://sevenoaksgardens.co.uk
Public corporate email: hello@sevenoaksgardens.co.uk
Email source: https://sevenoaksgardens.co.uk/contact
Privacy notice: https://example.com/privacy
Google Maps URL: https://maps.google.com/example
Google rating: 4.8
Google review count: 65
Website platform: Wix
Opportunity score: 75/100
Primary website issue: No project portfolio detected
""",
                    "status": {"status": "completed"},
                }
            ]
        }
    )
    client = ClickUpClient(
        "secret",
        "list-id",
        {
            "task_name_prefix": "[REVIEW REQUIRED] Web Design Audit",
            "web_design_task_name_prefix": "[REVIEW REQUIRED] Web Design Audit",
            "privacy_notice_url": "https://example.com/privacy",
        },
        session=session,
    )

    lead = client.approved_leads(
        "completed", required_lead_type="web_design_weak_site"
    )[0]

    assert lead.primary_issue == "No project portfolio detected"
    assert lead.opportunity_score == 75
    assert lead.website_platform == "Wix"
    assert lead.google_review_count == 65
