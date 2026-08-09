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
    client = ClickUpClient("secret", "list-id", {"task_name_prefix": "[REVIEW REQUIRED] AI Lab lead"})
    result = client.create_review_task(lead, dry_run=True)
    payload = result["payload"]
    assert "[REVIEW REQUIRED]" in payload["name"]
    assert "Company number: 12345678" in payload["description"]
    assert "Email source: https://brightagency.co.uk/contact" in payload["description"]
    assert "secret" not in str(payload)

