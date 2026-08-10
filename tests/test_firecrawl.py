import requests

from luminary_leads.firecrawl import FirecrawlClient, SearchResult
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


def test_role_email_can_qualify_without_a_website_when_company_match_is_strong():
    company = Company(
        "123",
        "Bright Agency Limited",
        "2026-07-01",
        "ltd",
        "active",
        ["73110"],
        {"postal_code": "SE1 2AA"},
    )
    client = FirecrawlClient("test", CONFIG)

    assert client._email_allowed_without_website(
        "hello@brightagency.co.uk", company, 70
    )
    assert not client._email_allowed_without_website(
        "jane@brightagency.co.uk", company, 100
    )
    assert not client._email_allowed_without_website("hello@gmail.com", company, 100)
    assert not client._email_allowed_without_website("info@jars.lt", company, 100)


def test_registry_company_page_is_rejected_even_with_exact_company_details():
    client = FirecrawlClient("test", CONFIG)
    company = Company(
        "15099106",
        "Web Int Limited",
        "2026-07-01",
        "ltd",
        "active",
        ["62020"],
        {"postal_code": "EC1V 2NX"},
    )
    result = SearchResult(
        url="https://jars.lt/en/company/uk/15099106-web-int-limited",
        title="WEB INT LIMITED | Registry code 15099106",
        description="Registered Address EC1V 2NX. Company status Active.",
    )

    assert client._looks_like_registry_listing(company, result)
    assert not client._domain_matches_company(company, result.url)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


class SequencedSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        return next(self.responses)


def test_retries_temporary_firecrawl_errors_with_exponential_backoff():
    session = SequencedSession([
        FakeResponse(500, {}),
        FakeResponse(503, {}),
        FakeResponse(200, {"data": {"web": []}}),
    ])
    delays = []
    client = FirecrawlClient(
        "test",
        {**CONFIG, "retry_attempts": 3, "retry_backoff_seconds": 0.5},
        session=session,
        sleep=delays.append,
    )

    result = client._post_json("search", {"query": "test"})

    assert result == {"data": {"web": []}}
    assert session.calls == 3
    assert delays == [0.5, 1.0]


def test_does_not_retry_non_transient_firecrawl_errors():
    session = SequencedSession([FakeResponse(400, {})])
    client = FirecrawlClient("test", CONFIG, session=session, sleep=lambda _: None)

    try:
        client._post_json("search", {"query": "test"})
    except requests.HTTPError:
        pass
    else:
        raise AssertionError("Expected Firecrawl HTTP error")

    assert session.calls == 1
