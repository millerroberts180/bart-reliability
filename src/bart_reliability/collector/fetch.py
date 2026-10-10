"""Download one feed with bounded exponential-backoff retries."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import requests
from google.transit import gtfs_realtime_pb2

from bart_reliability.collector.config import FeedConfig, RetryConfig
from bart_reliability.collector.validate import ValidationError, validate_feed

logger = logging.getLogger(__name__)

# Statuses that usually clear up within seconds; anything else non-200 is permanent.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class FetchResult:
    content: bytes
    message: gtfs_realtime_pb2.FeedMessage
    attempts: int


class FetchError(Exception):
    """Raised when a feed could not be fetched and validated this cycle."""

    def __init__(self, reason: str, attempts: int, retryable: bool):
        super().__init__(reason)
        self.reason = reason
        self.attempts = attempts
        self.retryable = retryable


class _AttemptError(Exception):
    def __init__(self, reason: str, retryable: bool):
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


def backoff_delay(attempt: int, retry: RetryConfig) -> float:
    """Wait before the next attempt: initial * 2^(attempt - 1), capped at the max."""
    return min(retry.backoff_initial_seconds * 2 ** (attempt - 1), retry.backoff_max_seconds)


def fetch_valid_feed(
    session: requests.Session,
    feed: FeedConfig,
    retry: RetryConfig,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """Fetch and validate a feed, retrying transient failures.

    Raises FetchError once a permanent failure occurs or attempts run out.
    """
    for attempt in range(1, retry.max_attempts + 1):
        try:
            content, message = _attempt(session, feed, retry.timeout_seconds)
            return FetchResult(content=content, message=message, attempts=attempt)
        except _AttemptError as e:
            final = not e.retryable or attempt == retry.max_attempts
            logger.warning(
                "fetch_attempt_failed",
                extra={
                    "fields": {
                        "feed": feed.name,
                        "attempt": attempt,
                        "max_attempts": retry.max_attempts,
                        "reason": e.reason,
                        "retryable": e.retryable,
                    }
                },
            )
            if final:
                raise FetchError(e.reason, attempts=attempt, retryable=e.retryable) from e
            sleep(backoff_delay(attempt, retry))

    raise AssertionError("unreachable: max_attempts is validated to be >= 1")


def _attempt(
    session: requests.Session, feed: FeedConfig, timeout: float
) -> tuple[bytes, gtfs_realtime_pb2.FeedMessage]:
    try:
        response = session.get(feed.url, timeout=timeout)
    except requests.Timeout as e:
        raise _AttemptError(f"timeout: {e}", retryable=True) from e
    except requests.ConnectionError as e:
        raise _AttemptError(f"connection error: {e}", retryable=True) from e
    except requests.RequestException as e:
        raise _AttemptError(f"request failed: {e}", retryable=False) from e

    if response.status_code != 200:
        retryable = response.status_code in RETRYABLE_STATUSES
        raise _AttemptError(f"http {response.status_code}", retryable=retryable)

    # BART serves protobuf with a text/html content type, so only parsing can tell.
    try:
        message = validate_feed(response.content)
    except ValidationError as e:
        raise _AttemptError(f"invalid feed: {e}", retryable=True) from e
    return response.content, message
