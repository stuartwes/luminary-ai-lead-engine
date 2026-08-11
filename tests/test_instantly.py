from luminary_leads.instantly import InstantlyClient
from luminary_leads.models import ApprovedLead
from luminary_leads.sync_cli import campaign_config


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

    def get(self, url, **kwargs):
        self.last_request = (url, kwargs)
        return FakeResponse(self.payload)

    def patch(self, url, **kwargs):
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


def test_weak_site_audit_fields_are_sent_as_custom_variables():
    lead = approved_lead()
    lead.lead_type = "web_design_weak_site"
    lead.website_platform = "Wix"
    lead.opportunity_score = 75
    lead.primary_issue = "No project portfolio detected"
    lead.google_rating = "4.8"
    lead.google_review_count = 65
    lead.google_maps_url = "https://maps.google.com/example"
    session = FakeSession({"leads_uploaded": 1, "created_leads": [{"id": "lead-1"}]})
    client = InstantlyClient("secret", "campaign-1", {}, session=session)

    client.add_lead(lead)

    variables = session.last_request[1]["json"]["leads"][0]["custom_variables"]
    assert variables["primary_issue"] == "No project portfolio detected"
    assert variables["opportunity_score"] == 75
    assert variables["website_platform"] == "Wix"
    assert variables["google_review_count"] == 65


def test_blocklisted_lead_is_reported_as_suppressed():
    assert InstantlyClient.outcome({"leads_uploaded": 0, "in_blocklist": 1}) == (
        "suppressed by Instantly blocklist"
    )


def test_campaign_config_routes_each_lead_type_separately():
    config = {
        "instantly": {
            "campaign_id": "ai-campaign",
            "lead_type": "ai_business_lab",
        },
        "instantly_web_design": {
            "campaign_id": "web-campaign",
            "lead_type": "web_design",
        },
        "instantly_weak_sites": {
            "campaign_id": "weak-site-campaign",
            "lead_type": "web_design_weak_site",
        },
    }

    assert campaign_config(config, "ai_business_lab")["campaign_id"] == "ai-campaign"
    assert campaign_config(config, "web_design")["campaign_id"] == "web-campaign"
    assert (
        campaign_config(config, "web_design_weak_site")["campaign_id"]
        == "weak-site-campaign"
    )


def test_registry_domain_is_blocked_before_instantly_upload():
    lead = approved_lead()
    lead.website = "https://jars.lt/en/company/uk/12345678-bright-agency"
    lead.email = "info@jars.lt"
    client = InstantlyClient(
        "secret",
        "campaign-1",
        {"blocked_lead_domains": ["jars.lt"]},
        session=FakeSession({"leads_uploaded": 1}),
    )

    assert client.blocked_lead_domain(lead) == "jars.lt"
    try:
        client.add_lead(lead)
    except ValueError as exc:
        assert "jars.lt" in str(exc)
    else:
        raise AssertionError("Expected blocked registry-domain lead")


def test_five_step_campaign_update_preserves_deliverability_controls():
    sequences = [{"steps": [{"type": "email"} for _ in range(5)]}]
    session = FakeSession({"sequences": sequences})
    client = InstantlyClient("secret", "campaign-1", {}, session=session)

    result = client.update_sequence(sequences)

    url, request = session.last_request
    assert url.endswith("/api/v2/campaigns/campaign-1")
    assert request["json"]["sequences"] == sequences
    assert request["json"]["stop_on_reply"] is True
    assert request["json"]["link_tracking"] is False
    assert request["json"]["text_only"] is True
    assert len(result["sequences"][0]["steps"]) == 5


def test_campaign_update_rejects_non_five_step_sequence():
    client = InstantlyClient("secret", "campaign-1", {}, session=FakeSession({}))

    try:
        client.update_sequence([{"steps": [{"type": "email"}]}])
    except ValueError as exc:
        assert "exactly five" in str(exc)
    else:
        raise AssertionError("Expected five-step validation error")
