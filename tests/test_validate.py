import pytest
from conftest import FEED_TIMESTAMP, build_feed

from bart_reliability.collector.validate import ValidationError, validate_feed


def test_valid_feed_returns_message(trip_update_bytes):
    message = validate_feed(trip_update_bytes)
    assert message.header.timestamp == FEED_TIMESTAMP
    assert len(message.entity) == 3


def test_feed_with_no_entities_is_valid(empty_alerts_bytes):
    message = validate_feed(empty_alerts_bytes)
    assert len(message.entity) == 0


def test_empty_body_is_rejected():
    with pytest.raises(ValidationError, match="empty"):
        validate_feed(b"")


@pytest.mark.parametrize(
    "content",
    [b"<html><body>Service Unavailable</body></html>", b"\xff\xfe garbage"],
    ids=["html_error_page", "random_bytes"],
)
def test_non_protobuf_is_rejected(content):
    with pytest.raises(ValidationError, match="decode failed"):
        validate_feed(content)


def test_truncated_feed_is_rejected(trip_update_bytes):
    with pytest.raises(ValidationError):
        validate_feed(trip_update_bytes[: len(trip_update_bytes) // 2])


def test_zero_timestamp_is_rejected():
    with pytest.raises(ValidationError, match="timestamp"):
        validate_feed(build_feed(entities=1, timestamp=0))
