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


def test_official_website_can_publish_named_same_domain_mailbox():
    client = FirecrawlClient("test", CONFIG)

    assert client.email_allowed_on_official_website(
        "jane@brightagency.co.uk", "https://brightagency.co.uk"
    )
    assert not client.email_allowed_on_official_website(
        "jane@gmail.com", "https://brightagency.co.uk"
    )
    assert not client.email_allowed_on_official_website(
        "jane@another.co.uk", "https://brightagency.co.uk"
    )


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
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self.payload = payload
        self.headers = headers or {}

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
        self.last_json = kwargs.get("json")
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
        {
            **CONFIG,
            "retry_attempts": 3,
            "retry_backoff_seconds": 0.5,
            "retry_jitter_seconds": 0,
        },
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


def test_honours_retry_after_header_for_rate_limits():
    session = SequencedSession([
        FakeResponse(429, {}, {"Retry-After": "7"}),
        FakeResponse(200, {"data": {"web": []}}),
    ])
    delays = []
    client = FirecrawlClient(
        "test",
        {
            **CONFIG,
            "rate_limit_retry_attempts": 3,
            "rate_limit_backoff_seconds": 2,
            "retry_jitter_seconds": 0,
        },
        session=session,
        sleep=delays.append,
    )

    result = client._post_json("search", {"query": "test"})

    assert result == {"data": {"web": []}}
    assert delays == [7.0]
    assert session.calls == 2


def test_rate_limit_backoff_is_longer_and_capped_without_header():
    session = SequencedSession([
        FakeResponse(429, {}),
        FakeResponse(429, {}),
        FakeResponse(429, {}),
        FakeResponse(200, {"data": {"web": []}}),
    ])
    delays = []
    client = FirecrawlClient(
        "test",
        {
            **CONFIG,
            "rate_limit_retry_attempts": 4,
            "rate_limit_backoff_seconds": 5,
            "rate_limit_max_wait_seconds": 8,
            "retry_jitter_seconds": 0,
        },
        session=session,
        sleep=delays.append,
    )

    client._post_json("search", {"query": "test"})

    assert delays == [5.0, 8.0, 8.0]
    assert session.calls == 4


def test_search_uses_configured_us_market():
    session = SequencedSession([FakeResponse(200, {"data": {"web": []}})])
    client = FirecrawlClient(
        "test",
        {
            **CONFIG,
            "search_country": "US",
            "search_location": "Florida,United States",
        },
        session=session,
    )
    company = Company(
        "USFLL26000123456",
        "Bright Marketing LLC",
        "2026-08-07",
        "FLAL",
        "A",
        address={"postal_code": "33101"},
    )

    assert client._discover_website(company) is None
    assert session.last_json["country"] == "US"
    assert session.last_json["location"] == "Florida,United States"


def test_indexed_site_search_finds_only_same_domain_role_email():
    session = SequencedSession([
        FakeResponse(
            200,
            {
                "data": {
                    "web": [
                        {
                            "url": "https://brightagency.co.uk/contact",
                            "title": "Contact Bright Agency",
                            "description": "Email hello@brightagency.co.uk",
                        },
                        {
                            "url": "https://directory.example/bright-agency",
                            "description": "Email info@brightagency.co.uk",
                        },
                    ]
                }
            },
        )
    ])
    client = FirecrawlClient("test", CONFIG, session=session)

    result = client.discover_role_email_on_website(
        "https://brightagency.co.uk", "Bright Agency", "SE1 2AA"
    )

    assert result == (
        "hello@brightagency.co.uk",
        "https://brightagency.co.uk/contact",
    )
    assert '"brightagency.co.uk"' in session.last_json["query"]


def test_indexed_external_profile_can_supply_same_domain_role_email():
    session = SequencedSession([
        FakeResponse(
            200,
            {
                "data": {
                    "web": [
                        {
                            "url": "https://localprofile.example/bright-agency",
                            "title": "Bright Agency contact details",
                            "description": "Email info@brightagency.co.uk",
                        }
                    ]
                }
            },
        )
    ])
    client = FirecrawlClient("test", CONFIG, session=session)

    assert client.discover_role_email_on_website(
        "https://brightagency.co.uk", "Bright Agency", "SE1 2AA"
    ) == (
        "info@brightagency.co.uk",
        "https://localprofile.example/bright-agency",
    )
