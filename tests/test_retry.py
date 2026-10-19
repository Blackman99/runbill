import io
import json
import socket
import urllib.error

import pytest

from runbill import github
from runbill.github import Client, GitHubError


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_err(code, body="", headers=None):
    return urllib.error.HTTPError("u", code, "x", headers or {}, io.BytesIO(body.encode()))


def client(monkeypatch, outcomes):
    seq = list(outcomes)
    calls = []

    def fake(req, timeout=30):
        calls.append(req.full_url)
        o = seq.pop(0)
        if isinstance(o, BaseException):
            raise o
        return Resp(json.dumps(o).encode())

    monkeypatch.setattr(github.urllib.request, "urlopen", fake)
    c = Client(token="t")
    c.sleeps = []
    c._sleep = c.sleeps.append
    return c, calls


def test_retries_5xx_then_succeeds(monkeypatch):
    c, calls = client(monkeypatch, [http_err(502), http_err(503), {"ok": 1}])
    assert c.get("/x") == {"ok": 1}
    assert len(calls) == 3 and c.sleeps == [1.0, 2.0] and c.calls == 1


def test_gives_up_after_bounded_retries(monkeypatch):
    c, calls = client(monkeypatch, [http_err(500)] * 10)
    with pytest.raises(GitHubError, match="HTTP 500.*after 3 retries"):
        c.get("/x")
    assert len(calls) == 4 and c.sleeps == [1.0, 2.0, 4.0]


def test_connection_errors_retry(monkeypatch):
    c, _ = client(monkeypatch, [
        urllib.error.URLError("reset"), TimeoutError(), socket.timeout("read"), {"ok": 2},
    ])
    assert c.get("/x") == {"ok": 2}
    assert c.sleeps == [1.0, 2.0, 4.0]


def test_retry_after_and_secondary_rate_limit(monkeypatch):
    c, _ = client(monkeypatch, [
        http_err(403, "You have exceeded a secondary rate limit", {"Retry-After": "7"}),
        http_err(429, "", {"Retry-After": "999"}),
        http_err(403, "secondary rate limit"),
        {"ok": 3},
    ])
    assert c.get("/x") == {"ok": 3}
    assert c.sleeps == [7.0, 60.0, 4.0]


@pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
def test_client_errors_not_retried(monkeypatch, code):
    c, calls = client(monkeypatch, [http_err(code, "nope"), {"ok": 1}])
    with pytest.raises(GitHubError, match=f"HTTP {code}"):
        c.get("/x")
    assert len(calls) == 1 and c.sleeps == []
