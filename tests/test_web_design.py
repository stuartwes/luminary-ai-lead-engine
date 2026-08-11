from luminary_leads.companies_house import CompaniesHouseClient
from luminary_leads.models import Company, PlaceBusiness
from luminary_leads.places import GooglePlacesClient
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


def test_companies_house_business_match_accepts_exact_name_without_postcode_match():
    score = CompaniesHouseClient._business_match_score(
        "Sevenoaks Garden Design",
        "TN13 1AA",
        "Sevenoaks Garden Design Limited",
        "EC1A 1BB",
    )

    assert score >= 70


def test_companies_house_business_match_accepts_strong_name_without_postcode_match():
    score = CompaniesHouseClient._business_match_score(
        "Sevenoaks Garden Design",
        "TN13 1AA",
        "Sevenoaks Gardens Design Ltd",
        "EC1A 1BB",
    )

    assert score >= 70


def test_companies_house_business_match_rejects_unrelated_name_at_same_postcode():
    mismatch = CompaniesHouseClient._business_match_score(
        "Unrelated Landscapes",
        "TN13 1AA",
        "Chris Wild Limited",
        "TN13 1AA",
    )
    assert mismatch < 70


class CompaniesHouseSession:
    def __init__(self, items):
        self.items = items

    def get(self, *_args, **_kwargs):
        return FakeResponse({"items": self.items})


def test_find_corporate_match_allows_active_ltd_with_exact_name_at_other_postcode():
    client = CompaniesHouseClient(
        "secret",
        session=CompaniesHouseSession(
            [
                {
                    "title": "Sevenoaks Garden Design Ltd",
                    "company_number": "12345678",
                    "company_status": "active",
                    "company_type": "ltd",
                    "address": {"postal_code": "EC1A 1BB"},
                }
            ]
        ),
    )

    result = client.find_corporate_match("Sevenoaks Garden Design", "TN13 1AA")

    assert result is not None
    assert result[0].company_number == "12345678"
    assert result[1] >= 70


def test_find_corporate_match_still_rejects_inactive_and_non_ltd_llp_candidates():
    client = CompaniesHouseClient(
        "secret",
        session=CompaniesHouseSession(
            [
                {
                    "title": "Sevenoaks Garden Design Ltd",
                    "company_number": "11111111",
                    "company_status": "dissolved",
                    "company_type": "ltd",
                    "address": {"postal_code": "TN13 1AA"},
                },
                {
                    "title": "Sevenoaks Garden Design",
                    "company_number": "22222222",
                    "company_status": "active",
                    "company_type": "private-unlimited",
                    "address": {"postal_code": "TN13 1AA"},
                },
            ]
        ),
    )

    assert client.find_corporate_match("Sevenoaks Garden Design", "TN13 1AA") is None


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


def test_modern_content_rich_site_is_not_selected_merely_for_good_reviews():
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
