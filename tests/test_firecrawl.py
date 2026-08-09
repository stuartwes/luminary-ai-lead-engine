from luminary_leads.firecrawl import FirecrawlClient
from luminary_leads.models import Company


CONFIG = {
    "blocked_email_domains": ["gmail.com"],
    "allowed_email_prefixes": ["hello", "info"],
    "blocked_website_domains": ["linkedin.com"],
    "pages_per_site": 3,
    "search_results": 5,
}


def test_only_role_email_on_same_domain_is_allowed():
    client = FirecrawlClient("test", CONFIG)
    assert client._email_allowed("hello@brightagency.co.uk", "https://brightagency.co.uk")
    assert not client._email_allowed("jane@brightagency.co.uk", "https://brightagency.co.uk")
    assert not client._email_allowed("hello@gmail.com", "https://brightagency.co.uk")
    assert not client._email_allowed("info@another.co.uk", "https://brightagency.co.uk")


def test_company_domain_match_scores_highly():
    client = FirecrawlClient("test", CONFIG)
    company = Company("123", "Bright Agency Limited", "2026-07-01", "ltd", "active", ["73110"], {"postal_code": "SE1 2AA"})
    assert client._match_score(company, "https://brightagency.co.uk") >= 60

