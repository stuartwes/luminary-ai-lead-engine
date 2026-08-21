from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urlparse

import requests


@dataclass(slots=True)
class DeepResearchResult:
    business_summary: str = ""
    ideal_customers: list[str] = field(default_factory=list)
    specialist_services: list[str] = field(default_factory=list)
    differentiators: list[str] = field(default_factory=list)
    recent_activity: str = ""
    primary_opportunity: str = ""
    personalised_observation: str = ""
    alternative_angle: str = ""
    evidence_text: str = ""
    evidence_url: str = ""
    confidence: int = 0


def select_research_urls(base_url: str, links: list[str], max_pages: int = 12) -> list[str]:
    base_domain = _domain(base_url)
    excluded = ("privacy", "terms", "cookie", "legal", "login", "account", "cart", "feed", "/tag/", "/category/")
    priorities = (
        (("service", "solution"), 100),
        (("project", "case-stud", "portfolio", "gallery", "our-work"), 95),
        (("about", "team", "why-us"), 85),
        (("blog", "news", "latest"), 75),
        (("testimonial", "review"), 70),
        (("contact", "quote", "consult"), 65),
    )
    candidates: dict[str, int] = {urldefrag(base_url)[0].rstrip("/"): 1000}
    for raw in links:
        url = urldefrag(raw)[0].rstrip("/")
        path = urlparse(url).path.casefold()
        if not url or _domain(url) != base_domain or any(term in path for term in excluded):
            continue
        score = next((score for cues, score in priorities if any(cue in path for cue in cues)), 10)
        candidates[url] = max(candidates.get(url, 0), score)
    return [url for url, _ in sorted(candidates.items(), key=lambda item: (-item[1], len(item[0])))[:max_pages]]


class OpenAIDeepResearchClient:
    ENDPOINT = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str, config: dict, session: requests.Session | None = None) -> None:
        self.api_key = api_key
        self.config = config
        self.session = session or requests.Session()

    def research(self, business_name: str, website: str, pages: list[tuple[str, str]]) -> DeepResearchResult | None:
        max_page = int(self.config.get("max_chars_per_page", 8000))
        max_total = int(self.config.get("max_total_chars", 60000))
        documents, total = [], 0
        evidence_by_url = {}
        for url, text in pages:
            cleaned = re.sub(r"\s+", " ", text).strip()[:max_page]
            if not cleaned or total >= max_total:
                continue
            cleaned = cleaned[: max_total - total]
            total += len(cleaned)
            evidence_by_url[url] = cleaned
            documents.append(f"SOURCE URL: {url}\nCONTENT: {cleaned}")
        if not documents:
            return None
        schema = {
            "type": "object", "additionalProperties": False,
            "properties": {
                "business_summary": {"type": "string"},
                "ideal_customers": {"type": "array", "items": {"type": "string"}},
                "specialist_services": {"type": "array", "items": {"type": "string"}},
                "differentiators": {"type": "array", "items": {"type": "string"}},
                "recent_activity": {"type": "string"},
                "primary_opportunity": {"type": "string"},
                "personalised_observation": {"type": "string"},
                "alternative_angle": {"type": "string"},
                "evidence_text": {"type": "string"},
                "evidence_url": {"type": "string"},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            "required": ["business_summary", "ideal_customers", "specialist_services", "differentiators", "recent_activity", "primary_opportunity", "personalised_observation", "alternative_angle", "evidence_text", "evidence_url", "confidence"],
        }
        payload = {
            "model": self.config.get("model", "gpt-5.6-sol"),
            "store": False,
            "instructions": (
                "Research this UK landscaping prospect using only the supplied website evidence. "
                "Find a specific, respectful outreach angle. Do not invent facts or infer private or sensitive information. "
                "The evidence_text must be a short exact excerpt copied from evidence_url. "
                "The personalised_observation must use UK English, be factual, non-critical and no more than 35 words."
            ),
            "input": f"BUSINESS: {business_name}\nWEBSITE: {website}\n\n" + "\n\n".join(documents),
            "text": {"format": {"type": "json_schema", "name": "prospect_research", "strict": True, "schema": schema}},
        }
        response = self.session.post(
            self.ENDPOINT,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=int(self.config.get("request_timeout_seconds", 90)),
        )
        response.raise_for_status()
        raw = response.json()
        output_text = raw.get("output_text") or _output_text(raw)
        result = DeepResearchResult(**json.loads(output_text))
        source = evidence_by_url.get(result.evidence_url)
        if not source or _normalise(result.evidence_text) not in _normalise(source):
            return None
        if len(result.personalised_observation.split()) > 35:
            return None
        if result.confidence < int(self.config.get("minimum_confidence", 75)):
            return None
        return result


def _output_text(response: dict) -> str:
    for item in response.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    raise ValueError("OpenAI response contained no output_text")


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _domain(url: str) -> str:
    host = urlparse(url).netloc.casefold().split(":")[0]
    return host.removeprefix("www.")
