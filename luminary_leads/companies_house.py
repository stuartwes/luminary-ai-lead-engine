from __future__ import annotations

from datetime import date
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

    @staticmethod
    def _to_company(item: dict[str, Any]) -> Company:
        return Company(
            company_number=str(item.get("company_number", "")),
            name=str(item.get("company_name", "")).strip(),
            incorporated_on=str(item.get("date_of_creation") or item.get("incorporated_on") or ""),
            company_type=str(item.get("company_type", "")),
            status=str(item.get("company_status", "")),
            sic_codes=[str(code) for code in item.get("sic_codes", [])],
            address=item.get("registered_office_address") or item.get("address") or {},
        )

