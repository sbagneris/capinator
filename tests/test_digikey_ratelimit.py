"""Tests for DigiKeyV4's rate-limit / call-count instrumentation, exercised without
network or credentials by stubbing the OAuth session's POST."""
import capinator.digikey as dk


class FakeResponse:
    def __init__(self, status_code=200, headers=None, json_data=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._json = json_data or {"Products": []}

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class FakeSession:
    """Returns queued responses in order; records how many POSTs it saw."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.token = {"access_token": "tok"}
        self.posts = 0

    def post(self, *args, **kwargs):
        self.posts += 1
        return self._responses.pop(0)


def _bare_client():
    api = object.__new__(dk.DigiKeyV4)
    api.call_count = 0
    api.rate_limit_limit = 0
    api.rate_limit_remaining = None
    return api


def test_do_post_counts_and_captures_headers():
    api = _bare_client()
    api.session = FakeSession([
        FakeResponse(headers={"X-RateLimit-Limit": "1000", "X-RateLimit-Remaining": "997"})
    ])
    api._post_search({"any": "payload"})
    assert api.call_count == 1
    assert api.rate_limit_limit == 1000
    assert api.rate_limit_remaining == 997


def test_401_retry_reauths_and_counts_both_posts(monkeypatch):
    api = _bare_client()
    api.session = FakeSession([
        FakeResponse(status_code=401, headers={"X-RateLimit-Remaining": "5"}),
        FakeResponse(status_code=200, headers={"X-RateLimit-Remaining": "4"}),
    ])
    # re-auth just swaps in a token-bearing session; keep the same queue
    monkeypatch.setattr(api, "authenticate", lambda: api.session)
    api._post_search({"any": "payload"})
    assert api.call_count == 2          # both the 401 and the retry are counted
    assert api.rate_limit_remaining == 4  # latest header wins


def test_missing_headers_are_ignored():
    api = _bare_client()
    api.session = FakeSession([FakeResponse(headers={})])
    api._post_search({"any": "payload"})
    assert api.call_count == 1
    assert api.rate_limit_limit == 0 and api.rate_limit_remaining is None
