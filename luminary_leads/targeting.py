from __future__ import annotations

import re
from typing import Any

from .models import Company


def flatten_industries(config: dict[str, Any]) -> dict[str, str]:
    return {
        str(code): industry
        for industry, codes in config["industries"].items()
        for code in codes
    }


def postcode_area(postcode: str) -> str:
    match = re.match(r"^([A-Z]{1,2})", postcode.upper().strip())
    return match.group(1) if match else ""


def qualify_company(company: Company, config: dict[str, Any]) -> tuple[bool, str]:
    excluded_sics = {str(code) for code in config["exclusions"]["sic_codes"]}
    if excluded_sics.intersection(company.sic_codes):
        return False, "excluded SIC code"

    lowered_name = company.name.casefold()
    if any(term.casefold() in lowered_name for term in config["exclusions"]["company_name_terms"]):
        return False, "excluded company-name term"

    allowed_areas = {area.upper() for area in config["location"]["postcode_prefixes"]}
    if postcode_area(company.postcode) not in allowed_areas:
        return False, "outside target location"

    industries = flatten_industries(config)
    matching = [industries[code] for code in company.sic_codes if code in industries]
    if not matching:
        return False, "outside target industries"
    return True, matching[0]

