import pytest
import requests
import responses
from conftest import TRIP_URL

from bart_reliability.collector.config import FeedConfig
from bart_reliability.collector.fetch import FetchError, backoff_delay, fetch_valid_feed

FEED = FeedConfig(name="trip_updates", url=TRIP_URL)


@pytest.fixture
def sleeps():
    """Record requested backoff waits instead of actually sleeping."""
    return []


def fetch(config, sleeps):
    with requests.Session() as session:
        return fetch_valid_feed(session, FEED, config.retry, sleep=sleeps.append)


def test_backoff_doubles_and_is_capped(config):
    delays = [backoff_delay(n, config.retry) for n in range(1, 6)]
    assert delays == [1.0, 2.0, 4.0, 4.0, 4.0]


@responses.activate
def test_success_on_first_attempt(config, sleeps, trip_update_bytes):
    responses.get(TRIP_URL, body=trip_update_bytes, content_type="text/html")
    result = fetch(config, sleeps)
    assert result.content == trip_update_bytes
    assert result.attempts == 1
    assert sleeps == []


@responses.activate
def test_timeout_then_success_retries_with_backoff(config, sleeps, trip_update_bytes):
    responses.get(TRIP_URL, body=requests.exceptions.ConnectTimeout("timed out"))
    responses.get(TRIP_URL, body=requests.exceptions.ConnectionError("reset"))
    responses.get(TRIP_URL, body=trip_update_bytes)
    result = fetch(config, sleeps)
    assert result.attempts == 3
    assert sleeps == [1.0, 2.0]


@responses.activate
def test_503_is_retried(config, sleeps, trip_update_bytes):
    responses.get(TRIP_URL, status=503)
    responses.get(TRIP_URL, body=trip_update_bytes)
    assert fetch(config, sleeps).attempts == 2


@responses.activate
def test_invalid_body_is_retried(config, sleeps, trip_update_bytes):
    responses.get(TRIP_URL, body=b"<html>oops</html>")
    responses.get(TRIP_URL, body=trip_update_bytes)
    assert fetch(config, sleeps).attempts == 2


@responses.activate
def test_404_fails_immediately_without_retry(config, sleeps):
    responses.get(TRIP_URL, status=404)
    with pytest.raises(FetchError) as info:
        fetch(config, sleeps)
    assert info.value.attempts == 1
    assert info.value.retryable is False
    assert "404" in info.value.reason
    assert len(responses.calls) == 1
    assert sleeps == []


@responses.activate
def test_gives_up_after_max_attempts(config, sleeps):
    responses.get(TRIP_URL, status=503)
    with pytest.raises(FetchError) as info:
        fetch(config, sleeps)
    assert info.value.attempts == config.retry.max_attempts
    assert len(responses.calls) == config.retry.max_attempts
    # No wait after the final attempt.
    assert sleeps == [1.0, 2.0]


def test_worst_case_retry_time_fits_well_inside_interval(config):
    retry = config.retry
    timeouts = retry.max_attempts * retry.timeout_seconds
    waits = sum(backoff_delay(n, retry) for n in range(1, retry.max_attempts))
    assert timeouts + waits <= 10


@responses.activate
def test_request_uses_configured_timeout(config, sleeps, trip_update_bytes):
    responses.get(TRIP_URL, body=trip_update_bytes)
    fetch(config, sleeps)
    assert responses.calls[0].request.req_kwargs["timeout"] == config.retry.timeout_seconds
