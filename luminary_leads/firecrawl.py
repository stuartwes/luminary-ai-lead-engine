from __future__ import annotations

import re
import time
from dataclasses import dataclass
import logging
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

import requests

from .models import Company, EnrichedLead


EMAIL_RE = re.compile(r"(?i)(?<![\w.+-])([a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+)")
GENERIC_COMPANY_WORDS = {"limited", "ltd", "llp", "uk", "group", "services", "solutions", "company", "co"}
LOGGER = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass(slots=True)
class SearchResult:
    url: str
    title: str = ""
    description: str = ""
    markdown: str = ""


class FirecrawlClient:
    BASE_URL = "https://api.firecrawl.dev/v2"

    def __init__(
        self,
        api_key: str,
        enrichment_config: dict,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key
        self.config = enrichment_config
        self.session = session or requests.Session()
        self.sleep = sleep

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def enrich(self, company: Company, industry: str) -> EnrichedLead | None:
        website = self._discover_website(company)
        if not website:
            return None

        pages = [website]
        scraped_home = self._scrape(website)
        links = scraped_home.get("links") or []
        for link in links:
            absolute = urljoin(website, link)
            path = urlparse(absolute).path.casefold()
            if any(term in path for term in ("contact", "about", "team")) and self._same_domain(website, absolute):
                if absolute not in pages:
                    pages.append(absolute)
            if len(pages) >= int(self.config["pages_per_site"]):
                break

        candidates: list[tuple[str, str]] = []
        for index, page in enumerate(pages):
            data = scraped_home if index == 0 else self._scrape(page)
            content = "\n".join(
                str(data.get(key) or "") for key in ("markdown", "html", "rawHtml")
            )
            content += "\n" + "\n".join(str(link) for link in (data.get("links") or []))
            for email in EMAIL_RE.findall(content):
                if self._email_allowed(email, website):
                    candidates.append((email.lower(), page))

        if not candidates:
            return None
        email, source = sorted(set(candidates), key=lambda pair: self._email_priority(pair[0]))[0]
        confidence = self._match_score(company, website)
        if confidence < 60:
            return None
        return EnrichedLead(
            company=company,
            website=website,
            email=email,
            email_source_url=source,
            industry=industry,
            confidence=confidence,
            evidence=["Public role-based email on company website", f"Website match score: {confidence}/100"],
        )

    def _discover_website(self, company: Company) -> str | None:
        query = f'"{company.name}" {company.postcode} official website'
        payload = {
            "query": query,
            "limit": int(self.config["search_results"]),
            "sources": ["web"],
            "country": "UK",
            "location": "London,England,United Kingdom",
            "safe": True,
            "ignoreInvalidURLs": True,
        }
        raw = self._post_json("search", payload).get("data") or {}
        items = raw.get("web", []) if isinstance(raw, dict) else raw
        results = [
            SearchResult(
                url=str(item.get("url") or ""),
                title=str(item.get("title") or ""),
                description=str(item.get("description") or ""),
                markdown=str(item.get("markdown") or ""),
            )
            for item in items
            if isinstance(item, dict) and item.get("url")
        ]
        allowed = [item for item in results if not self._website_blocked(item.url)]
        if not allowed:
            return None
        ranked = sorted(allowed, key=lambda item: self._match_score(company, item.url, item.title, item.description), reverse=True)
        winner = ranked[0]
        return winner.url if self._match_score(company, winner.url, winner.title, winner.description) >= 60 else None

    def _scrape(self, url: str) -> dict:
        payload = {
            "url": url,
            "formats": ["markdown", "html", "links"],
            "onlyMainContent": False,
            "blockAds": True,
            "location": {"country": "GB", "languages": ["en-GB"]},
            "timeout": 45000,
        }
        return self._post_json("scrape", payload).get("data") or {}

    def _post_json(self, endpoint: str, payload: dict) -> dict:
        attempts = max(1, int(self.config.get("retry_attempts", 3)))
        backoff = max(0.0, float(self.config.get("retry_backoff_seconds", 2)))
        url = f"{self.BASE_URL}/{endpoint}"

        for attempt in range(1, attempts + 1):
            try:
                response = self.session.post(
                    url, headers=self.headers, json=payload, timeout=60
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                status = exc.response.status_code if exc.response is not None else None
                retryable = status is None or status in RETRYABLE_STATUS_CODES
                if not retryable or attempt == attempts:
                    raise
                delay = backoff * (2 ** (attempt - 1))
                LOGGER.warning(
                    "Firecrawl %s attempt %d/%d failed%s; retrying in %.1fs",
                    endpoint,
                    attempt,
                    attempts,
                    f" with HTTP {status}" if status else "",
                    delay,
                )
                self.sleep(delay)

        raise RuntimeError("Firecrawl retry loop ended unexpectedly")

    def _email_allowed(self, email: str, website: str) -> bool:
        local, _, domain = email.lower().rpartition("@")
        if domain in {item.lower() for item in self.config["blocked_email_domains"]}:
            return False
        if local not in {item.lower() for item in self.config["allowed_email_prefixes"]}:
            return False
        website_domain = self._root_domain(urlparse(website).netloc)
        return self._root_domain(domain) == website_domain

    def _website_blocked(self, url: str) -> bool:
        domain = urlparse(url).netloc.casefold().removeprefix("www.")
        return any(domain == blocked or domain.endswith("." + blocked) for blocked in self.config["blocked_website_domains"])

    @staticmethod
    def _same_domain(first: str, second: str) -> bool:
        return FirecrawlClient._root_domain(urlparse(first).netloc) == FirecrawlClient._root_domain(urlparse(second).netloc)

    @staticmethod
    def _root_domain(domain: str) -> str:
        parts = domain.casefold().removeprefix("www.").split(".")
        if len(parts) >= 3 and parts[-2:] in (["co", "uk"], ["org", "uk"], ["me", "uk"]):
            return ".".join(parts[-3:])
        return ".".join(parts[-2:])

    @staticmethod
    def _company_tokens(name: str) -> set[str]:
        tokens = set(re.findall(r"[a-z0-9]+", name.casefold()))
        return {token for token in tokens if token not in GENERIC_COMPANY_WORDS and len(token) > 2}

    def _match_score(self, company: Company, url: str, *text: str) -> int:
        tokens = self._company_tokens(company.name)
        haystack = " ".join((url, *text)).casefold()
        token_score = 0 if not tokens else round(70 * sum(token in haystack for token in tokens) / len(tokens))
        postcode_compact = company.postcode.replace(" ", "").casefold()
        location_score = 15 if postcode_compact and postcode_compact in haystack.replace(" ", "") else 0
        official_bonus = 15 if any(token in urlparse(url).netloc.casefold() for token in tokens) else 0
        return min(100, token_score + location_score + official_bonus)

    @staticmethod
    def _email_priority(email: str) -> tuple[int, str]:
        order = {"hello": 0, "info": 1, "contact": 2, "enquiries": 3, "sales": 4}
        return order.get(email.split("@", 1)[0], 9), email
