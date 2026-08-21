from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from .firecrawl import EMAIL_RE, FirecrawlClient
from .deep_research import OpenAIDeepResearchClient, select_research_urls
from .models import Company, PlaceBusiness

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class LandscaperLead:
    company: Company
    website: str
    email: str
    email_source_url: str
    industry: str
    confidence: int
    google_place_id: str
    google_maps_url: str
    google_rating: float | None
    google_review_count: int
    lead_score: int
    lead_class: str
    website_status: str
    sales_angle: str
    primary_opportunity: str
    personalised_observation: str
    high_value_services: list[str]
    research_mode: str = "standard"
    business_summary: str = ""
    ideal_customers: list[str] = field(default_factory=list)
    differentiators: list[str] = field(default_factory=list)
    recent_activity: str = ""
    research_evidence: str = ""
    evidence_url: str = ""
    research_confidence: int = 0
    alternative_angle: str = ""
    lead_type: str = "landscaper_lead_engine_v1"


class LandscaperLeadEvaluator:
    def __init__(self, firecrawl: FirecrawlClient, config: dict, deep_research: OpenAIDeepResearchClient | None = None) -> None:
        self.firecrawl = firecrawl
        self.config = config
        self.deep_research = deep_research

    def qualify(self, place: PlaceBusiness, industry: str) -> LandscaperLead | None:
        company = self._business_record(place)
        pages: list[tuple[str, dict]] = []
        website = place.website
        if website:
            homepage = self.firecrawl.scrape(website)
            pages.append((website, homepage))
            links = homepage.get("links") or []
            if self.deep_research:
                links = self.firecrawl.map_site(website, int(self.config["deep_research"].get("map_limit", 100)))
                selected = select_research_urls(website, links, int(self.config["deep_research"].get("max_pages", 12)))
                pages = [(website, homepage)] + [(url, self.firecrawl.scrape(url)) for url in selected if url.rstrip("/") != website.rstrip("/")]
            for link in ([] if self.deep_research else links):
                if not isinstance(link, str):
                    continue
                absolute = urljoin(website, link)
                if self._same_domain(website, absolute) and any(
                    cue in urlparse(absolute).path.casefold()
                    for cue in ("contact", "about", "service", "gallery", "portfolio", "project")
                ):
                    pages.append((absolute, self.firecrawl.scrape(absolute)))
                if len(pages) >= 4:
                    break

        email_candidates: list[tuple[str, str]] = []
        for url, page in pages:
            for email in EMAIL_RE.findall(self._page_text(page)):
                if self.firecrawl.email_allowed_on_official_website(email, website):
                    email_candidates.append((email.lower(), url))
        if website and not email_candidates:
            found = self.firecrawl.discover_role_email_on_website(
                website, place.name, place.postcode
            )
            if found:
                email_candidates.append(found)
        if not website:
            enriched = self.firecrawl.enrich(company, industry)
            if enriched:
                website = enriched.website
                email_candidates.append((enriched.email, enriched.email_source_url))
        if not email_candidates:
            return None

        email, email_source = sorted(
            set(email_candidates), key=lambda item: self.firecrawl.email_priority(item[0])
        )[0]
        content = "\n".join(self._page_text(page) for _, page in pages)
        score, services, opportunities = self._score(place, website, content)
        lead_class = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"
        if score < int(self.config["collection"].get("minimum_campaign_score", 65)):
            return None
        website_status = "none" if not website else ("opportunity" if opportunities else "good")
        primary = opportunities[0] if opportunities else "A proactive source of suitable new-business opportunities"
        angle = self._sales_angle(website_status, services, opportunities)
        observation = self._observation(place, website_status, opportunities)
        research = None
        if self.deep_research and website:
            try:
                research = self.deep_research.research(place.name, website, [(url, self._page_text(page)) for url, page in pages])
            except Exception:
                LOGGER.exception("Deep research failed for %s; using standard personalisation", place.name)
            if research:
                primary = research.primary_opportunity
                observation = research.personalised_observation
                services = research.specialist_services or services
        return LandscaperLead(
            company=company,
            website=website,
            email=email,
            email_source_url=email_source,
            industry=industry,
            confidence=90 if website else 75,
            google_place_id=place.place_id,
            google_maps_url=place.google_maps_url,
            google_rating=place.rating,
            google_review_count=place.review_count,
            lead_score=min(score, 100),
            lead_class=lead_class,
            website_status=website_status,
            sales_angle=angle,
            primary_opportunity=primary,
            personalised_observation=observation,
            high_value_services=services,
            research_mode=("deep_research_v2" if research else "standard_fallback" if self.deep_research else "standard"),
            business_summary=research.business_summary if research else "",
            ideal_customers=research.ideal_customers if research else [],
            differentiators=research.differentiators if research else [],
            recent_activity=research.recent_activity if research else "",
            research_evidence=research.evidence_text if research else "",
            evidence_url=research.evidence_url if research else "",
            research_confidence=research.confidence if research else 0,
            alternative_angle=research.alternative_angle if research else "",
        )

    def _score(self, place: PlaceBusiness, website: str, content: str) -> tuple[int, list[str], list[str]]:
        weights = self.config["scoring"]
        lower = content.casefold()
        score = int(weights["valid_business_email"])
        score += int(weights["relevant_service"])
        score += int(weights["active_business"])
        score += int(weights["target_geography"])
        if website:
            score += int(weights["website_exists"])
        services = [term for term in weights["high_value_terms"] if term in lower]
        if services:
            score += int(weights["high_value_services"])
        opportunities: list[str] = []
        if not website:
            opportunities.append("No independent business website was verified")
            score += int(weights["website_improvement_opportunity"])
            score += int(weights["underdeveloped_lead_generation"])
        else:
            if not any(term in lower for term in weights["conversion_terms"]):
                opportunities.append("No prominent quote or consultation route was detected")
            if not any(term in lower for term in weights["portfolio_terms"]):
                opportunities.append("No prominent project portfolio was detected")
            if opportunities:
                score += int(weights["website_improvement_opportunity"])
                score += int(weights["underdeveloped_lead_generation"])
        if place.rating is not None and place.rating >= 4.2:
            score += int(weights["good_reputation"])
        if place.review_count >= 20:
            score += int(weights["established_business"])
        return score, services, opportunities

    @staticmethod
    def _sales_angle(website_status: str, services: list[str], opportunities: list[str]) -> str:
        if website_status == "none":
            return "website_and_leads"
        if opportunities:
            return "conversion"
        if services:
            return "growth"
        return "lead_generation"

    @staticmethod
    def _observation(place: PlaceBusiness, website_status: str, opportunities: list[str]) -> str:
        if website_status == "none":
            return "I could not find an independent website that turns your Google presence into a clear route for project enquiries."
        if opportunities and "quote" in opportunities[0].casefold():
            return "I noticed your work is presented online, but there is no prominent route for a visitor to request a quote or consultation."
        if opportunities:
            return "I noticed there is an opportunity to make completed projects more prominent and connect them more directly to an enquiry."
        if place.review_count:
            return f"I noticed the business has built up {place.review_count} Google reviews, which suggests a strong base for more proactive customer acquisition."
        return "I noticed the business has a clear landscaping offer and may be well placed to add a more proactive source of enquiries."

    @staticmethod
    def _business_record(place: PlaceBusiness) -> Company:
        identifier = hashlib.sha256(place.place_id.encode("utf-8")).hexdigest()[:16].upper()
        return Company(
            company_number=f"LLE{identifier}",
            name=place.name,
            incorporated_on="Not supplied",
            company_type="google_business_profile",
            status=place.business_status or "OPERATIONAL",
            address={"postal_code": place.postcode},
        )

    @staticmethod
    def _page_text(data: dict) -> str:
        return "\n".join(str(data.get(key) or "") for key in ("markdown", "html", "rawHtml"))

    @staticmethod
    def _same_domain(first: str, second: str) -> bool:
        return FirecrawlClient._root_domain(urlparse(first).netloc) == FirecrawlClient._root_domain(urlparse(second).netloc)
