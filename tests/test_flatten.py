from datetime import UTC, date, datetime

import pytest
from google.transit import gtfs_realtime_pb2

from bart_reliability.transform.flatten import (
    SCHEMA,
    flatten_feed,
    infer_service_date,
    parse_collected_at,
    rows_to_table,
)

COLLECTED_AT = datetime(2026, 10, 9, 21, 15, 0, tzinfo=UTC)
FEED_TS = int(COLLECTED_AT.timestamp()) - 5
SOURCE = "trip_updates/2026-10-09/211500Z.pb"


def make_message(timestamp=FEED_TS):
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "1.0"
    message.header.timestamp = timestamp
    return message


def add_trip(message, trip_id="T1", stops=(("M10-1", 600),), **trip_fields):
    entity = message.entity.add()
    entity.id = trip_id or "no-trip"
    if trip_id is not None:
        entity.trip_update.trip.trip_id = trip_id
    for name, value in trip_fields.items():
        setattr(entity.trip_update.trip, name, value)
    for stop_id, arrival_offset in stops:
        stu = entity.trip_update.stop_time_update.add()
        if stop_id is not None:
            stu.stop_id = stop_id
        if arrival_offset is not None:
            stu.arrival.time = int(COLLECTED_AT.timestamp()) + arrival_offset
    return entity


def test_one_row_per_stop_time_update():
    message = make_message()
    add_trip(message, "T1", stops=(("A10-1", 60), ("A20-1", 180)))
    add_trip(message, "T2", stops=(("M10-1", 300),))
    result = flatten_feed(message, COLLECTED_AT, SOURCE)
    assert [(r["trip_id"], r["stop_id"]) for r in result.rows] == [
        ("T1", "A10-1"),
        ("T1", "A20-1"),
        ("T2", "M10-1"),
    ]


def test_row_preserves_timestamps_and_computes_horizon():
    message = make_message()
    add_trip(message, "T1", stops=(("M10-1", 600),))
    (row,) = flatten_feed(message, COLLECTED_AT, SOURCE).rows
    assert row["feed_timestamp"] == FEED_TS
    assert row["collected_at"] == int(COLLECTED_AT.timestamp())
    assert row["predicted_arrival"] == int(COLLECTED_AT.timestamp()) + 600
    assert row["prediction_horizon_seconds"] == 600
    assert row["source_file"] == SOURCE


def test_missing_optional_fields_become_null_not_defaults():
    message = make_message()
    add_trip(message, "T1", stops=(("M10-1", None),))
    (row,) = flatten_feed(message, COLLECTED_AT, SOURCE).rows
    for column in [
        "route_id",
        "direction_id",
        "stop_sequence",
        "predicted_arrival",
        "predicted_departure",
        "arrival_delay_s",
        "trip_schedule_relationship",
        "stop_schedule_relationship",
        "prediction_horizon_seconds",
    ]:
        assert row[column] is None, column


def test_present_optional_fields_are_kept():
    message = make_message()
    entity = add_trip(message, "T1", route_id="YELLOW", direction_id=0, schedule_relationship=0)
    stu = entity.trip_update.stop_time_update[0]
    stu.stop_sequence = 4
    stu.arrival.delay = 90
    stu.arrival.uncertainty = 30
    stu.departure.time = stu.arrival.time + 20
    stu.schedule_relationship = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SKIPPED
    (row,) = flatten_feed(message, COLLECTED_AT, SOURCE).rows
    assert row["route_id"] == "YELLOW"
    assert row["direction_id"] == 0  # 0 is a real value here, not "missing"
    assert row["trip_schedule_relationship"] == "SCHEDULED"
    assert row["stop_sequence"] == 4
    assert row["arrival_delay_s"] == 90
    assert row["arrival_uncertainty_s"] == 30
    assert row["predicted_departure"] == row["predicted_arrival"] + 20
    assert row["stop_schedule_relationship"] == "SKIPPED"


def test_trip_and_stop_schedule_relationships_are_kept_separately():
    message = make_message()
    entity = add_trip(
        message,
        "T1",
        stops=(("A10-1", 60), ("A20-1", 120)),
        schedule_relationship=gtfs_realtime_pb2.TripDescriptor.ADDED,
    )
    second_stop = entity.trip_update.stop_time_update[1]
    second_stop.schedule_relationship = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.NO_DATA
    rows = flatten_feed(message, COLLECTED_AT, SOURCE).rows
    assert [(r["trip_schedule_relationship"], r["stop_schedule_relationship"]) for r in rows] == [
        ("ADDED", None),
        ("ADDED", "NO_DATA"),
    ]


def test_bart_delay_values_are_kept_as_supplied():
    message = make_message()
    entity = add_trip(message, "T1", stops=(("M10-1", None),))
    stu = entity.trip_update.stop_time_update[0]
    stu.arrival.delay = 274  # delay only, no absolute time
    stu.departure.delay = -15  # early departures are negative
    (row,) = flatten_feed(message, COLLECTED_AT, SOURCE).rows
    assert row["arrival_delay_s"] == 274
    assert row["departure_delay_s"] == -15
    assert row["predicted_arrival"] is None
    assert row["prediction_horizon_seconds"] is None


def test_empty_feed_produces_no_rows_and_a_valid_table():
    result = flatten_feed(make_message(), COLLECTED_AT, SOURCE)
    assert result.rows == []
    table = rows_to_table(result.rows)
    assert table.num_rows == 0
    assert table.schema == SCHEMA


def test_rows_without_trip_or_stop_id_are_counted_and_skipped():
    message = make_message()
    add_trip(message, None, stops=(("M10-1", 60),))
    add_trip(message, "T2", stops=((None, 60), ("M20-1", 60)))
    result = flatten_feed(message, COLLECTED_AT, SOURCE)
    assert [r["stop_id"] for r in result.rows] == ["M20-1"]
    assert result.stats.skipped_missing_key == 2


def test_repeated_trip_and_stop_in_one_feed_is_deduplicated():
    message = make_message()
    add_trip(message, "T1", stops=(("M10-1", 60), ("M10-1", 90)))
    result = flatten_feed(message, COLLECTED_AT, SOURCE)
    assert len(result.rows) == 1
    assert result.rows[0]["prediction_horizon_seconds"] == 60
    assert result.stats.duplicates_in_file == 1


def test_entities_without_trip_update_are_ignored():
    message = make_message()
    message.entity.add(id="alert-only").alert.header_text.translation.add(text="hi")
    assert flatten_feed(message, COLLECTED_AT, SOURCE).rows == []


def test_rows_convert_to_schema():
    message = make_message()
    add_trip(message, "T1", stops=(("M10-1", 600),))
    table = rows_to_table(flatten_feed(message, COLLECTED_AT, SOURCE).rows)
    assert table.schema == SCHEMA
    assert table.column("predicted_arrival")[0].as_py() == datetime(2026, 10, 9, 21, 25, tzinfo=UTC)


@pytest.mark.parametrize(
    ("collected_at", "expected"),
    [
        # 2026-10-09 is PDT (UTC-7).
        (datetime(2026, 10, 9, 21, 15, tzinfo=UTC), date(2026, 10, 9)),  # 14:15 local
        (datetime(2026, 10, 10, 6, 59, 59, tzinfo=UTC), date(2026, 10, 9)),  # 23:59 local
        (datetime(2026, 10, 10, 9, 59, 59, tzinfo=UTC), date(2026, 10, 9)),  # 02:59 local
        (datetime(2026, 10, 10, 10, 0, 0, tzinfo=UTC), date(2026, 10, 10)),  # 03:00 local
        # 2026-12-01 is PST (UTC-8).
        (datetime(2026, 12, 1, 10, 30, tzinfo=UTC), date(2026, 11, 30)),  # 02:30 local
        (datetime(2026, 12, 1, 11, 0, tzinfo=UTC), date(2026, 12, 1)),  # 03:00 local
    ],
)
def test_inferred_service_date_uses_pacific_time_and_3am_cutoff(collected_at, expected):
    assert infer_service_date(collected_at) == expected


def test_parse_collected_at_from_snapshot_path():
    assert parse_collected_at("trip_updates/2026-10-09/224227Z.pb") == datetime(
        2026, 10, 9, 22, 42, 27, tzinfo=UTC
    )


@pytest.mark.parametrize(
    "name",
    ["trip_updates/2026-10-09/notes.pb", "trip_updates/224227Z.pb", "x/2026-13-40/000000Z.pb"],
)
def test_parse_collected_at_rejects_unexpected_names(name):
    with pytest.raises(ValueError):
        parse_collected_at(name)
