from datetime import date

from luminary_leads.florida import (
    FloridaDailyFile,
    FloridaSunbizClient,
    parse_corporate_file,
    parse_corporate_line,
)
from luminary_leads.florida_pipeline import FloridaLeadPipeline, classify_florida_company
from luminary_leads.models import Company, EnrichedLead


def fixed_width_record(
    *,
    number="L26000123456",
    name="BRIGHT DIGITAL MARKETING LLC",
    status="A",
    filing_type="FLAL",
    city="MIAMI",
    state="FL",
    postal_code="33101",
    filed="08072026",
):
    line = [" "] * 1440

    def put(start, length, value):
        line[start : start + length] = f"{value:<{length}}"[:length]

    put(0, 12, number)
    put(12, 192, name)
    put(204, 1, status)
    put(205, 15, filing_type)
    put(304, 28, city)
    put(332, 2, state)
    put(334, 10, postal_code)
    put(344, 2, "US")
    put(472, 8, filed)
    return "".join(line)


def test_parses_official_fixed_width_corporate_record():
    company = parse_corporate_line(fixed_width_record())

    assert company is not None
    assert company.company_number == "USFLL26000123456"
    assert company.name == "BRIGHT DIGITAL MARKETING LLC"
    assert company.company_type == "FLAL"
    assert company.incorporated_on == "2026-08-07"
    assert company.postcode == "33101"
    assert company.address["source_document_number"] == "L26000123456"


def test_skips_malformed_records_and_parses_valid_rows():
    content = ("short\n" + fixed_width_record() + "\n").encode("cp1252")
    assert len(parse_corporate_file(content)) == 1


def test_blank_optional_password_env_uses_published_public_credential(monkeypatch):
    monkeypatch.setenv("FLORIDA_SUNBIZ_PASSWORD", "")
    client = FloridaSunbizClient({})
    assert client.password == "PubAccess1845!"


def test_name_targeting_classifies_and_excludes_registration_businesses():
    company = parse_corporate_line(fixed_width_record())
    config = {
        "industry_name_terms": {"marketing": ["marketing"]},
        "company_name_terms": ["registered agent"],
    }
    assert classify_florida_company(company, config) == "marketing"

    excluded = Company(
        "USFL1", "ACME REGISTERED AGENT MARKETING LLC", "2026-08-07", "FLAL", "A"
    )
    assert classify_florida_company(excluded, config) == ""


class FakeSunbiz:
    def latest(self, today=None):
        records = [
            parse_corporate_line(fixed_width_record()),
            parse_corporate_line(fixed_width_record(number="P26000999999", name="OLD MARKETING INC", filed="01012020", filing_type="DOMP")),
            parse_corporate_line(fixed_width_record(number="N26000000001", name="NONPROFIT TRAINING INC", filing_type="DOMNP")),
        ]
        return FloridaDailyFile(date(2026, 8, 7), records, "test")


class FakeFirecrawl:
    def enrich(self, company, industry):
        return EnrichedLead(
            company,
            "https://brightdigitalmarketing.com",
            "hello@brightdigitalmarketing.com",
            "https://brightdigitalmarketing.com/contact",
            industry,
            85,
        )


class FakeClickUp:
    def __init__(self):
        self.created = []

    def existing_company_numbers(self):
        return set()

    def create_review_task(self, lead, dry_run=False):
        self.created.append((lead, dry_run))


def test_pipeline_only_enriches_recent_active_domestic_target_company():
    config = {
        "collection": {
            "filing_types": ["DOMP", "FLAL"],
            "new_company_max_age_days": 10,
            "max_candidates_per_run": 300,
            "max_review_leads_per_run": 50,
        },
        "targeting": {
            "industry_name_terms": {"marketing": ["marketing"], "training": ["training"]},
            "company_name_terms": [],
        },
    }
    clickup = FakeClickUp()
    pipeline = FloridaLeadPipeline(config, FakeSunbiz(), FakeFirecrawl(), clickup)

    leads = pipeline.run(today=date(2026, 8, 10), dry_run=True)

    assert len(leads) == 1
    assert leads[0].company.name == "BRIGHT DIGITAL MARKETING LLC"
    assert clickup.created[0][1] is True
