import json

from luminary_leads.deep_research import OpenAIDeepResearchClient, select_research_urls


def test_url_selection_prioritises_commercial_pages_and_excludes_legal():
    base = "https://example.co.uk"
    result = select_research_urls(base, [
        base + "/privacy-policy", base + "/services/garden-design",
        base + "/projects/courtyard", base + "/about-us", base + "/contact",
        "https://other.co.uk/services",
    ], 4)
    assert result[0] == base
    assert base + "/services/garden-design" in result
    assert base + "/projects/courtyard" in result
    assert base + "/privacy-policy" not in result


class Response:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): return None
    def json(self): return self.payload


class Session:
    def __init__(self, output): self.output = output; self.request = None
    def post(self, *args, **kwargs): self.request = kwargs; return Response({"output_text": json.dumps(self.output)})


def result(evidence="Award-winning courtyard gardens"):
    return {
        "business_summary": "Design-led landscaper", "ideal_customers": ["Homeowners"],
        "specialist_services": ["Courtyard gardens"], "differentiators": ["Award-winning"],
        "recent_activity": "", "primary_opportunity": "Showcase specialist courtyard projects",
        "personalised_observation": "I noticed your award-winning courtyard work, which could make a strong starting point for reaching homeowners planning design-led garden projects.",
        "alternative_angle": "Project portfolio", "evidence_text": evidence,
        "evidence_url": "https://example.co.uk/projects", "confidence": 90,
    }


def test_research_accepts_only_exact_evidence_and_uses_structured_outputs():
    session = Session(result())
    client = OpenAIDeepResearchClient("secret", {"minimum_confidence": 75}, session)
    found = client.research("Example", "https://example.co.uk", [("https://example.co.uk/projects", "Award-winning courtyard gardens in Birmingham")])
    assert found and found.confidence == 90
    assert session.request["json"]["store"] is False
    assert session.request["json"]["text"]["format"]["type"] == "json_schema"


def test_research_rejects_unsupported_evidence():
    client = OpenAIDeepResearchClient("secret", {"minimum_confidence": 75}, Session(result("Invented claim")))
    assert client.research("Example", "https://example.co.uk", [("https://example.co.uk/projects", "Award-winning courtyard gardens")]) is None
