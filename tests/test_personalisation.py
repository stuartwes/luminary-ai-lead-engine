import json

from luminary_leads.deep_research import DeepResearchResult
from luminary_leads.personalisation import OpenAIPersonalisationClient


class Response:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): return None
    def json(self): return self.payload


class Session:
    def __init__(self, output): self.output = output; self.request = None
    def post(self, *args, **kwargs):
        self.request = kwargs
        return Response({"output_text": json.dumps(self.output)})


def research():
    return DeepResearchResult(
        business_summary="Design-led landscaper",
        ideal_customers=["Homeowners planning premium gardens"],
        specialist_services=["Courtyard gardens"],
        differentiators=["Award-winning courtyard work"],
        primary_opportunity="Reach homeowners planning design-led gardens",
        personalised_observation="I noticed your award-winning courtyard projects.",
        evidence_text="Award-winning courtyard gardens",
        evidence_url="https://example.co.uk/projects",
        confidence=90,
    )


def output(**overrides):
    value = {
        "subject_line": "Your courtyard garden work",
        "icebreaker": "I noticed your award-winning courtyard projects, particularly the way you make compact spaces feel considered rather than compromised.",
        "relevance_bridge": "That specialist work gives a focused reason to approach homeowners planning premium garden redesigns.",
        "value_proposition": "A Lead Engine could identify suitable prospects and open relevant conversations around the courtyard and design-led projects you want more of.",
        "call_to_action": "Worth me sharing the outline?",
        "target_customer_angle": "Homeowners planning premium garden redesigns",
        "supporting_evidence": "Award-winning courtyard gardens",
        "evidence_url": "https://example.co.uk/projects",
        "confidence": 91,
        "rejection_reason": "",
    }
    value.update(overrides)
    return value


def test_v3_composer_uses_structured_output_and_accepts_exact_evidence():
    session = Session(output())
    client = OpenAIPersonalisationClient("secret", {"minimum_confidence": 80}, session)
    result = client.compose("Example", research(), [("https://example.co.uk/projects", "Award-winning courtyard gardens in Sheffield")])
    assert result and result.confidence == 91
    assert session.request["json"]["store"] is False
    assert session.request["json"]["text"]["format"]["type"] == "json_schema"


def test_v3_composer_rejects_fabricated_results_claim():
    client = OpenAIPersonalisationClient("secret", {"minimum_confidence": 80}, Session(output(value_proposition="We generated 29 qualified leads in 60 days.")))
    assert client.compose("Example", research(), [("https://example.co.uk/projects", "Award-winning courtyard gardens")]) is None


def test_v3_composer_rejects_unsupported_evidence():
    client = OpenAIPersonalisationClient("secret", {"minimum_confidence": 80}, Session(output(supporting_evidence="Invented evidence")))
    assert client.compose("Example", research(), [("https://example.co.uk/projects", "Award-winning courtyard gardens")]) is None
