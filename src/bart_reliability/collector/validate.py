"""Check that a response body is a well-formed GTFS-Realtime FeedMessage."""

from __future__ import annotations

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2


class ValidationError(ValueError):
    """Raised when response bytes are not a usable GTFS-Realtime feed."""


def validate_feed(content: bytes) -> gtfs_realtime_pb2.FeedMessage:
    """Parse content with the official bindings and return the FeedMessage.

    Parsing alone is not enough: empty bytes parse as an empty message, so we
    also require the header's required fields and a non-zero feed timestamp.
    A feed with zero entities (e.g. no alerts in the feed) is still valid.
    """
    if not content:
        raise ValidationError("empty response body")

    message = gtfs_realtime_pb2.FeedMessage()
    try:
        message.ParseFromString(content)
    except DecodeError as e:
        raise ValidationError(f"protobuf decode failed: {e}") from e

    if not message.IsInitialized():
        missing = ", ".join(message.FindInitializationErrors())
        raise ValidationError(f"missing required fields: {missing}")
    if message.header.timestamp == 0:
        raise ValidationError("header.timestamp is missing or zero")

    return message
