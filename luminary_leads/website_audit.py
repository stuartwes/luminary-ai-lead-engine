from __future__ import annotations

import logging
import re
from datetime import date
from urllib.parse import urljoin, urlparse

from .firecrawl import EMAIL_RE, FirecrawlClient
from .models import Company, EnrichedLead, PlaceBusiness


LOGGER = logging.getLogger(__name__)


PLATFORM_SIGNATURES = (
    ("Wix", ("wixstatic.com", "wix.com/website/builder", "x-wix-")),
    ("Squarespace", ("static1.squarespace.com", "squarespace.com")),
    ("Weebly", ("editmysite.com", "weebly.com")),
    ("GoDaddy", ("godaddysites.com", "wsimg.com")),
    ("IONOS", ("mywebsite-editor.com", "ionos.co.uk")),
    ("WordPress", ("wp-content/", "wp-includes/")),
)


class WebsiteAuditClient:
    def __init__(self, firecrawl: FirecrawlClient, config: dict) -> None:
        self.firecrawl = firecrawl
        self.config = config

    def qualify(
        self,
        company: Company,
        place: PlaceBusiness,
        industry: str,
        corporate_match_score: int,
    ) -> EnrichedLead | None:
        if not place.website:
            discovered = self.firecrawl.enrich(company, industry)
            if not discovered:
                LOGGER.info(
                    "Skipped %s: no verified website with a public same-domain role email",
                    place.name,
                )
                return None
            if discovered.website:
                place.website = discovered.website
            else:
                discovered.lead_type = "web_design_weak_site"
                discovered.google_place_id = place.place_id
                discovered.google_maps_url = place.google_maps_url
                discovered.google_rating = place.rating
                discovered.google_review_count = place.review_count
                discovered.opportunity_score = 80
                discovered.primary_issue = "No independent business website was verified"
                discovered.audit_signals = [
                    "Google Places supplied no website",
                    "External search found no verified independent company website",
                ]
                discovered.confidence = min(discovered.confidence, corporate_match_score)
                return discovered

        homepage = self.firecrawl.scrape(place.website)
        pages: list[tuple[str, dict]] = [(place.website, homepage)]
        for link in homepage.get("links") or []:
            if not isinstance(link, str):
                continue
            absolute = urljoin(place.website, link)
            path = urlparse(absolute).path.casefold()
            if not self._same_domain(place.website, absolute):
                continue
            if any(
                cue in path
                for cue in ("contact", "about", "service", "gallery", "portfolio", "project")
            ) and absolute not in {url for url, _ in pages}:
                pages.append((absolute, self.firecrawl.scrape(absolute)))
            if len(pages) >= int(self.config.get("pages_per_site", 4)):
                break

        combined = "\n".join(self._page_text(data) for _, data in pages)
        lower = combined.casefold()
        platform = self._platform(combined)
        signals: list[str] = []
        score = 0

        diy_platforms = {item.casefold() for item in self.config.get("diy_platforms", [])}
        if platform.casefold() in diy_platforms:
            score += 15
            signals.append(f"Built with {platform}; template-platform review recommended")

        homepage_words = len(re.findall(r"\b[\w'-]+\b", self._page_text(homepage)))
        if homepage_words < int(self.config.get("thin_homepage_word_count", 120)):
            score += 15
            signals.append("Homepage has little crawlable descriptive content")

        if not any(term in lower for term in self.config.get("cta_terms", [])):
            score += 10
            signals.append("No clear quote, consultation or enquiry call to action detected")

        if not any(term in lower for term in self.config.get("portfolio_terms", [])):
            score += 10
            signals.append("No clear project gallery, portfolio or case-study section detected")

        if not any(term in lower for term in self.config.get("service_terms", [])):
            score += 10
            signals.append("No clear service-detail content detected")

        if not any(marker in lower for marker in ("localbusiness", "homeandconstructionbusiness")):
            score += 5
            signals.append("No LocalBusiness schema marker detected in scraped pages")

        copyright_years = [int(value) for value in re.findall(r"(?:©|copyright)\s*(20\d{2})", lower)]
        if copyright_years and max(copyright_years) <= date.today().year - 3:
            score += 10
            signals.append(f"Copyright notice appears dated ({max(copyright_years)})")

        if place.rating is not None and place.rating >= 4.5 and place.review_count >= 20:
            score += 10
            signals.append("Strong Google reputation: 4.5+ rating with at least 20 reviews")
        if place.review_count >= 50:
            score += 5
            signals.append("Established demand signal: at least 50 Google reviews")
        if bool(self.config.get("premium_visual_sector", True)):
            score += 10
            signals.append("Premium visual sector suited to a portfolio-led website")

        email_candidates: list[tuple[str, str]] = []
        for url, data in pages:
            for email in EMAIL_RE.findall(self._page_text(data)):
                if self.firecrawl.email_allowed(email, place.website):
                    email_candidates.append((email.lower(), url))
        if not email_candidates:
            discovered_email = self.firecrawl.discover_role_email_on_website(
                place.website, place.name, place.postcode
            )
            if discovered_email:
                email_candidates.append(discovered_email)
                LOGGER.info(
                    "Found a public same-domain role email for %s through indexed-site search",
                    place.name,
                )
        if not email_candidates:
            LOGGER.info(
                "Skipped %s: no public role-based email found on the website domain",
                place.name,
            )
            return None

        minimum_score = int(self.config.get("minimum_opportunity_score", 50))
        if score < minimum_score:
            LOGGER.info(
                "Skipped %s: website opportunity score %d is below the minimum %d",
                place.name,
                score,
                minimum_score,
            )
            return None

        email, source = sorted(
            set(email_candidates), key=lambda item: self.firecrawl.email_priority(item[0])
        )[0]
        primary_issue = self._primary_issue(signals, platform)
        return EnrichedLead(
            company=company,
            website=place.website,
            email=email,
            email_source_url=source,
            industry=industry,
            confidence=corporate_match_score,
            evidence=["Public role-based email on the Google-listed company website"],
            lead_type="web_design_weak_site",
            google_place_id=place.place_id,
            google_maps_url=place.google_maps_url,
            google_rating=place.rating,
            google_review_count=place.review_count,
            website_platform=platform,
            opportunity_score=min(score, 100),
            primary_issue=primary_issue,
            audit_signals=signals,
        )

    @staticmethod
    def _page_text(data: dict) -> str:
        return "\n".join(
            str(data.get(key) or "") for key in ("markdown", "html", "rawHtml")
        ) + "\n" + "\n".join(
            str(link) for link in (data.get("links") or [])
        )

    @staticmethod
    def _platform(content: str) -> str:
        lower = content.casefold()
        for name, signatures in PLATFORM_SIGNATURES:
            if any(signature in lower for signature in signatures):
                return name
        return "Unknown/custom"

    @staticmethod
    def _same_domain(first: str, second: str) -> bool:
        return FirecrawlClient._root_domain(urlparse(first).netloc) == FirecrawlClient._root_domain(
            urlparse(second).netloc
        )

    @staticmethod
    def _primary_issue(signals: list[str], platform: str) -> str:
        priority = (
            "little crawlable",
            "project gallery",
            "call to action",
            "service-detail",
            "copyright",
        )
        for term in priority:
            match = next((signal for signal in signals if term in signal.casefold()), None)
            if match:
                return match
        if platform != "Unknown/custom":
            return f"The {platform} website has several upgrade opportunities"
        return signals[0] if signals else "Website audit identified an upgrade opportunity"
