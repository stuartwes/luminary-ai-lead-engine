from luminary_leads.landscaper_lead_engine import LandscaperLeadEvaluator
from luminary_leads.landscaper_pipeline import LandscaperLeadPipeline
from luminary_leads.models import PlaceBusiness


def place(index):
    return PlaceBusiness(
        place_id=f"place-{index}",
        name=f"Nottingham Landscaper {index}",
        formatted_address=f"Nottingham NG{index % 9 + 1} 1AA, UK",
        business_status="OPERATIONAL",
    )


class Places:
    def __init__(self, values): self.values = values
    def search_queries(self, *args, **kwargs): return self.values


class Evaluator:
    def qualify(self, value, industry): return value


class ClickUp:
    def __init__(self, existing): self.existing = existing; self.calls = 0
    def existing_company_numbers(self): self.calls += 1; return self.existing


def test_dry_run_checks_clickup_and_searches_beyond_first_30_candidates():
    values = [place(index) for index in range(40)]
    existing = {
        LandscaperLeadEvaluator._business_record(value).company_number
        for value in values[:30]
    }
    clickup = ClickUp(existing)
    pipeline = LandscaperLeadPipeline(
        {
            "target": {"town": "Nottingham", "industry": "landscaping", "query_templates": ["landscaper in {town}"]},
            "collection": {"places_page_size": 20, "max_pages_per_query": 3, "max_candidates_per_run": 120, "max_approved_leads_per_run": 10},
        },
        Places(values), Evaluator(), clickup,
    )
    pipeline._create_task = lambda lead, dry_run: {"dry_run": dry_run}

    leads = pipeline.run(dry_run=True)

    assert clickup.calls == 1
    assert len(leads) == 10
    assert leads[0].name == "Nottingham Landscaper 30"
