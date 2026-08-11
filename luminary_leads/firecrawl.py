from __future__ import annotations

import re
import random
import time
from dataclasses import dataclass
import logging
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

import requests

from .models import Company, EnrichedLead


EMAIL_RE = re.compile(r"(?i)(?<![\w.+-])([a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+)")
GENERIC_COMPANY_WORDS = {
    "limited", "ltd", "llp", "llc", "inc", "corporation", "corp", "florida",
    "uk", "usa", "group", "services", "solutions", "company", "co",
}
LOGGER = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
REGISTRY_CUES = {
    "registry code",
    "registered address",
    "registration information",
    "company status",
    "company number",
}


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
        clock: Callable[[], float] = time.monotonic,
        random_fn: Callable[[], float] = random.random,
    ) -> None:
        self.api_key = api_key
        self.config = enrichment_config
        self.session = session or requests.Session()
        self.sleep = sleep
        self.clock = clock
        self.random_fn = random_fn
        self._next_request_at = 0.0

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def enrich(self, company: Company, industry: str) -> EnrichedLead | None:
        website = self._discover_website(company)
        if not website:
            return self._discover_public_email_without_website(company, industry)

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

    def _discover_public_email_without_website(
        self, company: Company, industry: str
    ) -> EnrichedLead | None:
        query = f'"{company.name}" {company.postcode} email contact'
        payload = {
            "query": query,
            "limit": int(self.config.get("email_search_results_without_website", 8)),
            "sources": ["web"],
            "country": self.config.get("search_country", "UK"),
            "location": self.config.get(
                "search_location", "London,England,United Kingdom"
            ),
            "safe": True,
            "ignoreInvalidURLs": True,
        }
        raw = self._post_json("search", payload).get("data") or {}
        items = raw.get("web", []) if isinstance(raw, dict) else raw
        candidates: list[tuple[str, str, int]] = []

        for item in items:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            source_url = str(item["url"])
            if self._email_source_blocked(source_url):
                continue
            source_text = "\n".join(
                str(item.get(key) or "")
                for key in ("title", "description", "markdown")
            )
            result = SearchResult(
                url=source_url,
                title=str(item.get("title") or ""),
                description=str(item.get("description") or ""),
                markdown=str(item.get("markdown") or ""),
            )
            if self._looks_like_registry_listing(company, result):
                continue
            score = self._match_score(company, source_url, source_text)
            if score < 60:
                continue

            emails = EMAIL_RE.findall(source_text)
            if not emails:
                try:
                    scraped = self._scrape(source_url)
                except requests.RequestException:
                    LOGGER.warning("Could not scrape email source %s", source_url)
                    continue
                source_text = "\n".join(
                    str(scraped.get(key) or "")
                    for key in ("markdown", "html", "rawHtml")
                )
                emails = EMAIL_RE.findall(source_text)

            for email in emails:
                if self._email_allowed_without_website(email, company, score):
                    candidates.append((email.lower(), source_url, score))

        if not candidates:
            return None
        email, source, confidence = sorted(
            set(candidates), key=lambda item: self._email_priority(item[0])
        )[0]
        return EnrichedLead(
            company=company,
            website="",
            email=email,
            email_source_url=source,
            industry=industry,
            confidence=confidence,
            evidence=[
                "Public role-based corporate email found without an official website",
                f"Company/source match score: {confidence}/100",
            ],
        )

    def _discover_website(self, company: Company) -> str | None:
        query = f'"{company.name}" {company.postcode} official website'
        payload = {
            "query": query,
            "limit": int(self.config["search_results"]),
            "sources": ["web"],
            "country": self.config.get("search_country", "UK"),
            "location": self.config.get(
                "search_location", "London,England,United Kingdom"
            ),
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
        allowed = [
            item
            for item in results
            if not self._website_blocked(item.url)
            and not self._looks_like_registry_listing(company, item)
            and self._domain_matches_company(company, item.url)
        ]
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
            "location": {
                "country": self.config.get("scrape_country", "GB"),
                "languages": self.config.get("scrape_languages", ["en-GB"]),
            },
            "timeout": 45000,
        }
        return self._post_json("scrape", payload).get("data") or {}

    def scrape(self, url: str) -> dict:
        """Scrape a known company URL using the configured safety and retry policy."""
        return self._scrape(url)

    def email_allowed(self, email: str, website: str) -> bool:
        return self._email_allowed(email, website)

    def email_priority(self, email: str) -> tuple[int, str]:
        return self._email_priority(email)

    def discover_role_email_on_website(
        self, website: str, business_name: str, postcode: str
    ) -> tuple[str, str] | None:
        """Search indexed pages on a known business domain for a role address."""
        domain = self._root_domain(urlparse(website).netloc)
        payload = {
            "query": f'site:{domain} "{business_name}" {postcode} email contact',
            "limit": int(self.config.get("email_search_results_on_site", 8)),
            "sources": ["web"],
            "country": self.config.get("search_country", "UK"),
            "location": self.config.get(
                "search_location", "London,England,United Kingdom"
            ),
            "safe": True,
            "ignoreInvalidURLs": True,
        }
        raw = self._post_json("search", payload).get("data") or {}
        items = raw.get("web", []) if isinstance(raw, dict) else raw
        candidates: list[tuple[str, str]] = []

        for item in items:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            source_url = str(item["url"])
            if not self._same_domain(website, source_url):
                continue
            source_text = "\n".join(
                str(item.get(key) or "")
                for key in ("title", "description", "markdown")
            )
            emails = EMAIL_RE.findall(source_text)
            if not emails:
                try:
                    scraped = self._scrape(source_url)
                except requests.RequestException:
                    LOGGER.warning("Could not scrape indexed contact page %s", source_url)
                    continue
                source_text = "\n".join(
                    str(scraped.get(key) or "")
                    for key in ("markdown", "html", "rawHtml")
                )
                emails = EMAIL_RE.findall(source_text)
            for email in emails:
                if self._email_allowed(email, website):
                    candidates.append((email.lower(), source_url))

        if not candidates:
            return None
        return sorted(set(candidates), key=lambda item: self._email_priority(item[0]))[0]

    def _post_json(self, endpoint: str, payload: dict) -> dict:
        attempts = max(1, int(self.config.get("retry_attempts", 3)))
        rate_limit_attempts = max(
            attempts, int(self.config.get("rate_limit_retry_attempts", attempts))
        )
        backoff = max(0.0, float(self.config.get("retry_backoff_seconds", 2)))
        rate_limit_backoff = max(
            0.0, float(self.config.get("rate_limit_backoff_seconds", backoff))
        )
        max_rate_limit_wait = max(
            rate_limit_backoff,
            float(self.config.get("rate_limit_max_wait_seconds", 60)),
        )
        jitter = max(0.0, float(self.config.get("retry_jitter_seconds", 1)))
        url = f"{self.BASE_URL}/{endpoint}"

        for attempt in range(1, rate_limit_attempts + 1):
            try:
                self._pace_requests()
                response = self.session.post(
                    url, headers=self.headers, json=payload, timeout=60
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                status = exc.response.status_code if exc.response is not None else None
                allowed_attempts = rate_limit_attempts if status == 429 else attempts
                retryable = status is None or status in RETRYABLE_STATUS_CODES
                if not retryable or attempt >= allowed_attempts:
                    raise
                if status == 429:
                    retry_after = self._retry_after_seconds(exc.response)
                    delay = (
                        retry_after
                        if retry_after is not None
                        else min(
                            rate_limit_backoff * (2 ** (attempt - 1)),
                            max_rate_limit_wait,
                        )
                        + self.random_fn() * jitter
                    )
                else:
                    delay = backoff * (2 ** (attempt - 1)) + self.random_fn() * jitter
                LOGGER.warning(
                    "Firecrawl %s attempt %d/%d failed%s; retrying in %.1fs",
                    endpoint,
                    attempt,
                    allowed_attempts,
                    f" with HTTP {status}" if status else "",
                    delay,
                )
                self.sleep(delay)

        raise RuntimeError("Firecrawl retry loop ended unexpectedly")

    def _pace_requests(self) -> None:
        interval = max(
            0.0, float(self.config.get("minimum_request_interval_seconds", 0))
        )
        if interval == 0:
            return
        now = self.clock()
        wait = max(0.0, self._next_request_at - now)
        if wait:
            self.sleep(wait)
            now = self.clock()
        self._next_request_at = max(now, self._next_request_at) + interval

    @staticmethod
    def _retry_after_seconds(response: requests.Response | None) -> float | None:
        if response is None:
            return None
        value = str(getattr(response, "headers", {}).get("Retry-After", "")).strip()
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            return None

    def _email_allowed(self, email: str, website: str) -> bool:
        local, _, domain = email.lower().rpartition("@")
        if domain in {item.lower() for item in self.config["blocked_email_domains"]}:
            return False
        if local not in {item.lower() for item in self.config["allowed_email_prefixes"]}:
            return False
        website_domain = self._root_domain(urlparse(website).netloc)
        return self._root_domain(domain) == website_domain

    def _email_allowed_without_website(
        self, email: str, company: Company, source_score: int
    ) -> bool:
        local, _, domain = email.lower().rpartition("@")
        if domain in {item.lower() for item in self.config["blocked_email_domains"]}:
            return False
        if local not in {item.lower() for item in self.config["allowed_email_prefixes"]}:
            return False
        domain_text = self._root_domain(domain).split(".", 1)[0]
        domain_matches_company = any(
            token in domain_text for token in self._company_tokens(company.name)
        )
        return domain_matches_company

    def _domain_matches_company(self, company: Company, url: str) -> bool:
        domain_text = self._root_domain(urlparse(url).netloc).split(".", 1)[0]
        return any(
            token in domain_text for token in self._company_tokens(company.name)
        )

    @staticmethod
    def _looks_like_registry_listing(company: Company, result: SearchResult) -> bool:
        path = urlparse(result.url).path.casefold()
        text = " ".join(
            (result.title, result.description, result.markdown)
        ).casefold()
        company_number = re.sub(r"[^a-z0-9]", "", company.company_number.casefold())
        compact_path = re.sub(r"[^a-z0-9]", "", path)
        registry_path = bool(
            re.search(r"/(?:company|companies|business)/(?:uk/)?[a-z0-9]*\d", path)
        )
        number_reproduced = bool(company_number) and (
            company_number in compact_path or company_number in re.sub(r"[^a-z0-9]", "", text)
        )
        cue_count = sum(cue in text for cue in REGISTRY_CUES)
        return registry_path or (number_reproduced and cue_count >= 2)

    def _email_source_blocked(self, url: str) -> bool:
        domain = urlparse(url).netloc.casefold().removeprefix("www.")
        blocked_domains = self.config.get(
            "blocked_email_source_domains", self.config["blocked_website_domains"]
        )
        return any(
            domain == blocked or domain.endswith("." + blocked)
            for blocked in blocked_domains
        )

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
