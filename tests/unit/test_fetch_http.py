import random

import pytest
import requests

from price_comparator.models import ScrapeStatus
from price_comparator.scrapers.fetch import FetchError, HttpFetcher
from tests.fakes import FakeResponse, FakeSession


def make(session, sleeps=None, **kwargs):
    sleeps = sleeps if sleeps is not None else []
    defaults = {
        "session": session,
        "user_agent": "test-agent",
        "timeout_s": 5,
        "max_retries": 3,
        "delay_range": (1.0, 2.0),
        "retry_wait_s": 4.0,
        "sleep": sleeps.append,
        "rng": random.Random(1),
    }
    defaults.update(kwargs)
    return HttpFetcher(**defaults), sleeps


def test_success_decodes_utf8_bytes():
    body = "Taladro eléctrico ñandú".encode()
    fetcher, _ = make(FakeSession(FakeResponse(200, body, "https://x.test/final")))
    resp = fetcher.get("https://x.test/", {"q": "a"})
    assert resp.status_code == 200
    assert resp.text == "Taladro eléctrico ñandú"
    assert resp.url == "https://x.test/final"


def test_sends_single_configured_user_agent_and_verifies_tls():
    session = FakeSession(FakeResponse(200, b"ok"))
    fetcher, _ = make(session)
    fetcher.get("https://x.test/", {"q": "a"})
    call = session.calls[0]
    assert call["headers"]["User-Agent"] == "test-agent"
    assert call["params"] == {"q": "a"}
    assert call["timeout"] == 5
    assert call.get("verify", True) is True


def test_polite_delay_is_applied_before_each_request():
    fetcher, sleeps = make(FakeSession(FakeResponse(200, b"ok")))
    fetcher.get("https://x.test/")
    assert len(sleeps) == 1
    assert 1.0 <= sleeps[0] <= 2.0


def test_404_is_returned_not_raised():
    fetcher, _ = make(FakeSession(FakeResponse(404, b"nope")))
    assert fetcher.get("https://x.test/").status_code == 404


def test_403_then_200_recovers_with_backoff():
    session = FakeSession(FakeResponse(403, b""), FakeResponse(200, b"ok"))
    fetcher, sleeps = make(session)
    assert fetcher.get("https://x.test/").text == "ok"
    assert len(session.calls) == 2
    assert any(s >= 4.0 for s in sleeps)


def test_persistent_429_raises_blocked_after_max_retries():
    session = FakeSession(FakeResponse(429, b""))
    fetcher, _ = make(session)
    with pytest.raises(FetchError) as err:
        fetcher.get("https://x.test/")
    assert err.value.kind is ScrapeStatus.BLOCKED
    assert len(session.calls) == 3


def test_backoff_grows_between_retries():
    fetcher, sleeps = make(FakeSession(FakeResponse(429, b"")), max_retries=3)
    with pytest.raises(FetchError):
        fetcher.get("https://x.test/")
    waits = [s for s in sleeps if s >= 4.0]
    assert waits == sorted(waits) and len(set(waits)) > 1


def test_500_is_retried_then_succeeds():
    session = FakeSession(FakeResponse(500, b""), FakeResponse(200, b"ok"))
    fetcher, _ = make(session)
    assert fetcher.get("https://x.test/").text == "ok"


def test_persistent_500_raises_error():
    fetcher, _ = make(FakeSession(FakeResponse(503, b"")))
    with pytest.raises(FetchError) as err:
        fetcher.get("https://x.test/")
    assert err.value.kind is ScrapeStatus.ERROR


def test_timeouts_raise_timeout_after_retries():
    session = FakeSession(requests.exceptions.Timeout("slow"))
    fetcher, _ = make(session)
    with pytest.raises(FetchError) as err:
        fetcher.get("https://x.test/")
    assert err.value.kind is ScrapeStatus.TIMEOUT
    assert len(session.calls) == 3


def test_connection_errors_raise_error_after_retries():
    fetcher, _ = make(FakeSession(requests.exceptions.ConnectionError("down")))
    with pytest.raises(FetchError) as err:
        fetcher.get("https://x.test/")
    assert err.value.kind is ScrapeStatus.ERROR


def test_oversized_response_is_rejected():
    fetcher, _ = make(FakeSession(FakeResponse(200, b"x" * 5000)), max_bytes=1000)
    with pytest.raises(FetchError) as err:
        fetcher.get("https://x.test/")
    assert err.value.kind is ScrapeStatus.ERROR
    assert "grande" in err.value.detail


def test_error_details_never_contain_the_query_string():
    fetcher, _ = make(FakeSession(FakeResponse(429, b"")))
    with pytest.raises(FetchError) as err:
        fetcher.get("https://x.test/search", {"q": "secreto"})
    assert "secreto" not in err.value.detail


class FakeClock:
    """Reloj y sleep de mentira: dormir avanza el reloj."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def budgeted(session, clock, **kwargs):
    defaults = {
        "session": session,
        "timeout_s": 15,
        "max_retries": 5,
        "delay_range": (1.0, 1.0),
        "retry_wait_s": 4.0,
        "total_budget_s": 10.0,
        "sleep": clock.sleep,
        "clock": clock,
        "rng": random.Random(1),
    }
    defaults.update(kwargs)
    return HttpFetcher(**defaults)


def test_total_budget_stops_retries_before_max_retries_and_keeps_the_error_kind():
    clock, session = FakeClock(), FakeSession(FakeResponse(429, b""))
    fetcher = budgeted(session, clock)
    with pytest.raises(FetchError) as err:
        fetcher.get("https://x.test/")
    assert err.value.kind is ScrapeStatus.BLOCKED
    assert len(session.calls) < 5
    assert clock.now <= 10.0 + 1e-9  # jamás se pasa del plazo total


def test_request_timeout_shrinks_to_the_remaining_budget():
    clock, session = FakeClock(), FakeSession(FakeResponse(200, b"ok"))
    budgeted(session, clock, total_budget_s=6.0).get("https://x.test/")
    assert session.calls[0]["timeout"] <= 6.0 - 1.0 + 1e-9  # ya se durmió la pausa cortés


def test_budget_exhausted_before_the_first_attempt_is_a_timeout_without_requests():
    clock, session = FakeClock(), FakeSession(FakeResponse(200, b"ok"))
    with pytest.raises(FetchError) as err:
        budgeted(session, clock, total_budget_s=0.5).get("https://x.test/")
    assert err.value.kind is ScrapeStatus.TIMEOUT
    assert session.calls == []


def test_budget_does_not_affect_a_fast_success():
    clock, session = FakeClock(), FakeSession(FakeResponse(200, b"ok"))
    assert budgeted(session, clock).get("https://x.test/").text == "ok"


def test_waiting_for_a_host_slot_counts_against_the_budget():
    fetcher = HttpFetcher(
        session=FakeSession(FakeResponse(200, b"ok")),
        max_concurrent=1,
        total_budget_s=0.2,
        delay_range=(0.0, 0.0),
        sleep=lambda _s: None,
    )
    fetcher._slots.acquire()  # otro hilo tiene el único cupo
    with pytest.raises(FetchError) as err:
        fetcher.get("https://x.test/")
    assert err.value.kind is ScrapeStatus.TIMEOUT


class DrippingResponse:
    """Un servidor que gotea 1 chunk cada 6 s: cada lectura individual respeta el timeout."""

    status_code = 200
    url = "https://x.test/"

    def __init__(self, clock, chunks=100):
        self._clock, self._chunks = clock, chunks
        self.closed = False

    def iter_content(self, size):
        for _ in range(self._chunks):
            self._clock.now += 6.0
            yield b"x"

    def close(self):
        self.closed = True


def test_slow_drip_response_cannot_outlive_the_total_budget():
    """Regresión: `_read` no miraba el plazo y un servidor lento retenía el hilo indefinidamente."""
    clock = FakeClock()
    resp = DrippingResponse(clock)
    fetcher = budgeted(FakeSession(resp), clock, total_budget_s=10.0, delay_range=(0.0, 0.0))
    with pytest.raises(FetchError) as err:
        fetcher.get("https://x.test/")
    assert err.value.kind is ScrapeStatus.TIMEOUT
    assert clock.now <= 10.0 + 6.0  # a lo más un chunk pasado del plazo
    assert resp.closed
