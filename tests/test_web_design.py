from luminary_leads.clickup import ClickUpClient
from luminary_leads.models import Company, EnrichedLead, PlaceBusiness
from luminary_leads.places import GooglePlacesClient
from luminary_leads.web_design_pipeline import WebDesignLeadPipeline
from luminary_leads.website_audit import WebsiteAuditClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class PlacesSession:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return FakeResponse(self.payload)


def test_places_text_search_requests_website_and_maps_fields():
    session = PlacesSession(
        {
            "places": [
                {
                    "id": "place-1",
                    "displayName": {"text": "Sevenoaks Garden Design"},
                    "formattedAddress": "1 High Street, Sevenoaks TN13 1AA, UK",
                    "websiteUri": "https://sevenoaksgardens.co.uk",
                    "googleMapsUri": "https://maps.google.com/example",
                    "rating": 4.8,
                    "userRatingCount": 42,
                    "businessStatus": "OPERATIONAL",
                }
            ]
        }
    )
    client = GooglePlacesClient("places-secret", session=session)

    result = client.search("garden designer in Sevenoaks")

    assert result[0].place_id == "place-1"
    assert result[0].postcode == "TN13 1AA"
    _, request = session.request
    assert request["json"]["textQuery"] == "garden designer in Sevenoaks"
    assert "places.websiteUri" in request["headers"]["X-Goog-FieldMask"]
    assert "places.userRatingCount" in request["headers"]["X-Goog-FieldMask"]


def test_google_place_creates_stable_business_record_without_companies_house():
    first = WebDesignLeadPipeline._business_record(_place())
    second = WebDesignLeadPipeline._business_record(_place())

    assert first.company_number == second.company_number
    assert first.company_number.startswith("GMB")
    assert first.name == "Sevenoaks Garden Design"
    assert first.postcode == "TN13 1AA"
    assert first.company_type == "google_business_profile"


def test_google_business_review_task_does_not_claim_companies_house_verification():
    company = WebDesignLeadPipeline._business_record(_place())
    lead = EnrichedLead(
        company,
        _place().website,
        "hello@sevenoaksgardens.co.uk",
        "https://sevenoaksgardens.co.uk/contact",
        "landscape_and_garden_design",
        85,
        lead_type="web_design_weak_site",
    )
    client = ClickUpClient(
        "secret",
        "list-id",
        {
            "task_name_prefix": "[REVIEW REQUIRED] Web Design Audit",
            "web_design_task_name_prefix": "[REVIEW REQUIRED] Web Design Audit",
            "privacy_notice_url": "https://example.com/privacy",
            "company_source": "Google Places and verified business website",
        },
    )

    description = client.create_review_task(lead, dry_run=True)["payload"]["description"]

    assert f"Lead record ID: {company.company_number}" in description
    assert "Business postcode: TN13 1AA" in description
    assert "Business identity and website ownership must be checked" in description
    assert "Corporate body must be confirmed" not in description


class AuditFirecrawl:
    def __init__(self, homepage):
        self.homepage = homepage

    def scrape(self, url):
        return self.homepage

    @staticmethod
    def email_allowed(email, website):
        return email in {"hello@sevenoaksgardens.co.uk", "info@sevenoaksgardens.co.uk"}

    @staticmethod
    def email_priority(email):
        return (0 if email.startswith("hello@") else 1, email)

    @staticmethod
    def enrich(company, industry):
        return None

    @staticmethod
    def discover_role_email_on_website(website, business_name, postcode):
        return None


AUDIT_CONFIG = {
    "pages_per_site": 1,
    "minimum_opportunity_score": 50,
    "thin_homepage_word_count": 120,
    "premium_visual_sector": True,
    "diy_platforms": ["Wix", "Squarespace", "Weebly", "GoDaddy", "IONOS"],
    "cta_terms": ["get a quote", "contact us"],
    "portfolio_terms": ["portfolio", "our projects"],
    "service_terms": ["our services", "garden design"],
}


def _company():
    return Company(
        "12345678",
        "Sevenoaks Garden Design Ltd",
        "2018-01-01",
        "ltd",
        "active",
        ["71112"],
        {"postal_code": "TN13 1AA"},
    )


def _place():
    return PlaceBusiness(
        "place-1",
        "Sevenoaks Garden Design",
        "1 High Street, Sevenoaks TN13 1AA, UK",
        "https://sevenoaksgardens.co.uk",
        "https://maps.google.com/example",
        rating=4.8,
        review_count=65,
        business_status="OPERATIONAL",
    )


def test_wix_site_with_thin_content_and_no_conversion_structure_qualifies():
    homepage = {
        "markdown": "Beautiful gardens. hello@sevenoaksgardens.co.uk",
        "html": '<script src="https://static.wixstatic.com/app.js"></script>',
        "links": [],
    }
    audit = WebsiteAuditClient(AuditFirecrawl(homepage), AUDIT_CONFIG)

    lead = audit.qualify(_company(), _place(), "landscape_and_garden_design", 92)

    assert lead is not None
    assert lead.lead_type == "web_design_weak_site"
    assert lead.website_platform == "Wix"
    assert lead.opportunity_score >= 70
    assert lead.email == "hello@sevenoaksgardens.co.uk"
    assert "crawlable" in lead.primary_issue


def test_modern_content_rich_site_is_not_selected_merely_for_good_reviews(caplog):
    caplog.set_level("INFO")
    content = " ".join(["garden"] * 130)
    homepage = {
        "markdown": (
            f"{content} Our services include garden design. View our projects. "
            "Contact us to get a quote. hello@sevenoaksgardens.co.uk"
        ),
        "html": '<script type="application/ld+json">{"@type":"LocalBusiness"}</script>',
        "links": [],
    }
    audit = WebsiteAuditClient(AuditFirecrawl(homepage), AUDIT_CONFIG)

    assert audit.qualify(_company(), _place(), "landscape_and_garden_design", 92) is None
    assert "website opportunity score" in caplog.text


def test_missing_same_domain_role_email_logs_clear_rejection(caplog):
    caplog.set_level("INFO")
    homepage = {
        "markdown": "Beautiful gardens and landscape services.",
        "html": '<script src="https://static.wixstatic.com/app.js"></script>',
        "links": [],
    }
    audit = WebsiteAuditClient(AuditFirecrawl(homepage), AUDIT_CONFIG)

    assert audit.qualify(_company(), _place(), "landscape_and_garden_design", 85) is None
    assert "no public role-based email found on the website domain" in caplog.text
