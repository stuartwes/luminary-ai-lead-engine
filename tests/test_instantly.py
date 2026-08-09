from luminary_leads.instantly import InstantlyClient
from luminary_leads.models import ApprovedLead


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

    def post(self, url, **kwargs):
        self.last_request = (url, kwargs)
        return FakeResponse(self.payload)


def approved_lead():
    return ApprovedLead(
        task_id="task-1",
        task_description="description",
        company_number="12345678",
        company_name="Bright Agency Ltd",
        incorporated_on="2026-07-20",
        industry="marketing",
        postcode="SE1 2AA",
        website="https://brightagency.co.uk",
        email="hello@brightagency.co.uk",
        email_source_url="https://brightagency.co.uk/contact",
        privacy_notice_url="https://luminaryaibusiness.com/luminaryaibusiness-privacy.html",
    )


def test_add_lead_uses_campaign_dedupe_and_audit_variables():
    session = FakeSession({"leads_uploaded": 1, "created_leads": [{"id": "lead-1"}]})
    client = InstantlyClient(
        "secret",
        "campaign-1",
        {"skip_if_in_workspace": True, "verify_leads_on_import": False},
        session=session,
    )

    result = client.add_lead(approved_lead())

    url, request = session.last_request
    assert url.endswith("/api/v2/leads/add")
    assert request["headers"]["Authorization"] == "Bearer secret"
    assert request["json"]["campaign_id"] == "campaign-1"
    assert request["json"]["skip_if_in_workspace"] is True
    assert request["json"]["leads"][0]["custom_variables"]["company_number"] == "12345678"
    assert InstantlyClient.outcome(result) == "uploaded (lead ID: lead-1)"


def test_blocklisted_lead_is_reported_as_suppressed():
    assert InstantlyClient.outcome({"leads_uploaded": 0, "in_blocklist": 1}) == (
        "suppressed by Instantly blocklist"
    )
