from luminary_leads.models import Company
from luminary_leads.targeting import postcode_area, qualify_company


def base_config():
    return {
        "location": {"postcode_prefixes": ["SE", "CM"]},
        "industries": {"marketing": ["73110"]},
        "exclusions": {"sic_codes": ["99999"], "company_name_terms": ["holdings"]},
    }


def test_postcode_area_handles_london_and_essex():
    assert postcode_area("SE1 2AA") == "SE"
    assert postcode_area("CM1 1AA") == "CM"


def test_qualifies_matching_company():
    company = Company("123", "Bright Agency Ltd", "2026-07-01", "ltd", "active", ["73110"], {"postal_code": "SE1 2AA"})
    assert qualify_company(company, base_config()) == (True, "marketing")


def test_excludes_dormant_company():
    company = Company("123", "Bright Agency Ltd", "2026-07-01", "ltd", "active", ["73110", "99999"], {"postal_code": "SE1 2AA"})
    assert qualify_company(company, base_config()) == (False, "excluded SIC code")

