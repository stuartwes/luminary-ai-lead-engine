from __future__ import annotations

from datetime import date
from difflib import SequenceMatcher
import re
from typing import Any, Iterable

import requests

from .models import Company


class CompaniesHouseClient:
    BASE_URL = "https://api.company-information.service.gov.uk"

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        self.api_key = api_key
        self.session = session or requests.Session()

    def advanced_search(
        self,
        incorporated_from: date,
        incorporated_to: date,
        sic_codes: Iterable[str],
        company_types: Iterable[str],
        company_statuses: Iterable[str],
        size: int = 5000,
    ) -> list[Company]:
        params = {
            "incorporated_from": incorporated_from.isoformat(),
            "incorporated_to": incorporated_to.isoformat(),
            "sic_codes": ",".join(sic_codes),
            "company_type": ",".join(company_types),
            "company_status": ",".join(company_statuses),
            "size": min(size, 5000),
        }
        response = self.session.get(
            f"{self.BASE_URL}/advanced-search/companies",
            params=params,
            auth=(self.api_key, ""),
            timeout=45,
        )
        response.raise_for_status()
        return [self._to_company(item) for item in response.json().get("items", [])]

    def search_companies(self, query: str, items_per_page: int = 20) -> list[Company]:
        response = self.session.get(
            f"{self.BASE_URL}/search/companies",
            params={"q": query, "items_per_page": min(items_per_page, 100)},
            auth=(self.api_key, ""),
            timeout=45,
        )
        response.raise_for_status()
        return [self._to_company(item) for item in response.json().get("items", [])]

    def find_corporate_match(
        self,
        business_name: str,
        postcode: str,
        *,
        allowed_types: tuple[str, ...] = ("ltd", "llp"),
        minimum_score: int = 70,
    ) -> tuple[Company, int] | None:
        candidates = self.search_companies(business_name)
        ranked: list[tuple[int, Company]] = []
        for company in candidates:
            if company.status.casefold() != "active":
                continue
            if company.company_type.casefold() not in {
                item.casefold() for item in allowed_types
            }:
                continue
            score = self._business_match_score(
                business_name, postcode, company.name, company.postcode
            )
            ranked.append((score, company))
        if not ranked:
            return None
        score, company = max(ranked, key=lambda item: item[0])
        return (company, score) if score >= minimum_score else None

    @staticmethod
    def _business_match_score(
        business_name: str,
        business_postcode: str,
        company_name: str,
        company_postcode: str,
    ) -> int:
        corporate_suffixes = {"limited", "ltd", "llp"}

        def tokens(value: str) -> list[str]:
            return [
                token
                for token in re.findall(r"[a-z0-9]+", value.casefold())
                if token not in corporate_suffixes and len(token) > 1
            ]

        business_tokens = tokens(business_name)
        company_tokens = tokens(company_name)
        if not business_tokens or not company_tokens:
            name_score = 0
        else:
            business_normalized = " ".join(business_tokens)
            company_normalized = " ".join(company_tokens)
            if business_normalized == company_normalized:
                name_score = 100
            else:
                business_set = set(business_tokens)
                company_set = set(company_tokens)
                overlap = len(business_set & company_set)
                token_similarity = 2 * overlap / (len(business_set) + len(company_set))
                text_similarity = SequenceMatcher(
                    None, business_normalized, company_normalized
                ).ratio()
                similarity = max(token_similarity, text_similarity)
                # A close spelling/token match is sufficient on its own. Weaker
                # names still need the registered postcode as corroboration.
                name_score = round((100 if similarity >= 0.85 else 70) * similarity)
        postcode_match = (
            bool(business_postcode and company_postcode)
            and business_postcode.replace(" ", "").casefold()
            == company_postcode.replace(" ", "").casefold()
        )
        return min(100, name_score + (30 if postcode_match else 0))

    @staticmethod
    def _to_company(item: dict[str, Any]) -> Company:
        return Company(
            company_number=str(item.get("company_number", "")),
            name=str(item.get("company_name") or item.get("title") or "").strip(),
            incorporated_on=str(item.get("date_of_creation") or item.get("incorporated_on") or ""),
            company_type=str(item.get("company_type", "")),
            status=str(item.get("company_status", "")),
            sic_codes=[str(code) for code in item.get("sic_codes", [])],
            address=item.get("registered_office_address") or item.get("address") or {},
        )
