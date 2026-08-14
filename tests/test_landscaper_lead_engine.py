from luminary_leads.landscaper_lead_engine import LandscaperLeadEvaluator
from luminary_leads.models import PlaceBusiness


class FakeFirecrawl:
    def __init__(self, content):
        self.content = content

    def scrape(self, url):
        return {"markdown": self.content, "links": []}

    @staticmethod
    def email_allowed_on_official_website(email, website):
        return email.endswith("@examplelandscapes.co.uk")

    @staticmethod
    def discover_role_email_on_website(website, business_name, postcode):
        return None

    @staticmethod
    def email_priority(email):
        return (0, email)

    @staticmethod
    def enrich(company, industry):
        return None


CONFIG = {
    "collection": {"minimum_campaign_score": 65},
    "scoring": {
        "valid_business_email": 20,
        "relevant_service": 15,
        "active_business": 10,
        "target_geography": 5,
        "website_exists": 5,
        "website_improvement_opportunity": 10,
        "high_value_services": 10,
        "good_reputation": 5,
        "established_business": 5,
        "decision_maker_identified": 5,
        "underdeveloped_lead_generation": 10,
        "high_value_terms": ["garden design", "paving"],
        "conversion_terms": ["get a quote"],
        "portfolio_terms": ["our projects"],
    },
}


def place():
    return PlaceBusiness(
        "place-1", "Example Landscapes", "Birmingham B1 1AA, UK",
        "https://examplelandscapes.co.uk", rating=4.8, review_count=35,
        business_status="OPERATIONAL",
    )


def test_campaign_requires_a_public_business_email():
    evaluator = LandscaperLeadEvaluator(FakeFirecrawl("garden design and paving"), CONFIG)
    assert evaluator.qualify(place(), "landscape_and_garden_design") is None


def test_campaign_scores_and_generates_observation_for_approved_prospect():
    content = "garden design and paving info@examplelandscapes.co.uk"
    lead = LandscaperLeadEvaluator(FakeFirecrawl(content), CONFIG).qualify(
        place(), "landscape_and_garden_design"
    )
    assert lead is not None
    assert lead.lead_type == "landscaper_lead_engine_v1"
    assert lead.lead_score >= 65
    assert lead.lead_class in {"A", "B"}
    assert "quote" in lead.personalised_observation.casefold()
    assert len(lead.personalised_observation.split()) <= 30
