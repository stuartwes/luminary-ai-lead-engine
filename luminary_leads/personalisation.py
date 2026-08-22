from __future__ import annotations

import json
import re
from dataclasses import dataclass

import requests

from .deep_research import DeepResearchResult, _normalise, _output_text


@dataclass(slots=True)
class PersonalisationResult:
    subject_line: str
    icebreaker: str
    relevance_bridge: str
    value_proposition: str
    call_to_action: str
    target_customer_angle: str
    supporting_evidence: str
    evidence_url: str
    confidence: int
    rejection_reason: str


class OpenAIPersonalisationClient:
    ENDPOINT = "https://api.openai.com/v1/responses"
    BANNED_CLAIMS = (
        "29 qualified", "60 days", "free of charge", "no strings attached",
        "guaranteed", "beleaf designs", "resolutesvs",
    )
    GENERIC_PHRASES = ("love your website", "impressive website", "great website")

    def __init__(self, api_key: str, config: dict, session: requests.Session | None = None) -> None:
        self.api_key = api_key
        self.config = config
        self.session = session or requests.Session()

    def compose(
        self,
        business_name: str,
        research: DeepResearchResult,
        pages: list[tuple[str, str]],
    ) -> PersonalisationResult | None:
        evidence_by_url = {
            url: re.sub(r"\s+", " ", text).strip()
            for url, text in pages if text.strip()
        }
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "subject_line": {"type": "string"},
                "icebreaker": {"type": "string"},
                "relevance_bridge": {"type": "string"},
                "value_proposition": {"type": "string"},
                "call_to_action": {"type": "string"},
                "target_customer_angle": {"type": "string"},
                "supporting_evidence": {"type": "string"},
                "evidence_url": {"type": "string"},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                "rejection_reason": {"type": "string"},
            },
            "required": [
                "subject_line", "icebreaker", "relevance_bridge", "value_proposition",
                "call_to_action", "target_customer_angle", "supporting_evidence",
                "evidence_url", "confidence", "rejection_reason",
            ],
        }
        prompt = {
            "business_name": business_name,
            "business_summary": research.business_summary,
            "ideal_customers": research.ideal_customers,
            "specialist_services": research.specialist_services,
            "differentiators": research.differentiators,
            "recent_activity": research.recent_activity,
            "primary_opportunity": research.primary_opportunity,
            "verified_observation": research.personalised_observation,
            "verified_evidence": research.evidence_text,
            "verified_evidence_url": research.evidence_url,
        }
        payload = {
            "model": self.config.get("model", "gpt-5.6-sol"),
            "store": False,
            "reasoning": {"effort": self.config.get("reasoning_effort", "low")},
            "instructions": (
                "Compose evidence-backed UK cold-email components for a landscaping prospect. "
                "Use only supplied research. Be human, specific, respectful and laconic. "
                "Subject maximum 9 words; icebreaker maximum 35 words; bridge maximum 35 words; "
                "value proposition maximum 45 words; CTA maximum 18 words. Do not claim results, "
                "customers, guarantees or free work. Do not flatter or criticise. supporting_evidence "
                "must be an exact website excerpt and evidence_url its supplied source. If safe, "
                "rejection_reason must be empty; otherwise explain why and leave outreach fields empty."
            ),
            "input": json.dumps(prompt, ensure_ascii=False),
            "text": {
                "verbosity": "low",
                "format": {"type": "json_schema", "name": "prospect_personalisation", "strict": True, "schema": schema},
            },
        }
        response = self.session.post(
            self.ENDPOINT,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=int(self.config.get("request_timeout_seconds", 90)),
        )
        response.raise_for_status()
        raw = response.json()
        result = PersonalisationResult(**json.loads(raw.get("output_text") or _output_text(raw)))
        source = evidence_by_url.get(result.evidence_url)
        combined = " ".join((result.subject_line, result.icebreaker, result.relevance_bridge, result.value_proposition, result.call_to_action)).casefold()
        if result.rejection_reason or not source:
            return None
        if _normalise(result.supporting_evidence) not in _normalise(source):
            return None
        if any(claim in combined for claim in self.BANNED_CLAIMS + self.GENERIC_PHRASES):
            return None
        limits = ((result.subject_line, 9), (result.icebreaker, 35), (result.relevance_bridge, 35), (result.value_proposition, 45), (result.call_to_action, 18))
        if any(not value.strip() or len(value.split()) > limit for value, limit in limits):
            return None
        if result.confidence < int(self.config.get("minimum_confidence", 80)):
            return None
        return result
