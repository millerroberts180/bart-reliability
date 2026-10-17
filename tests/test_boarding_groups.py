"""Boarding groups (api/boarding.py, docs/boarding_groups.md).

The real-network tests read tests/data/bart_boarding_patterns_2026-10-08.csv: every
distinct rail boarding pattern in BART's static GTFS of 2026-10-08, written by
`python -m bart_reliability.api.boarding_patterns` (api/boarding_patterns.py, which
documents the columns, ordering and source archive). It is schedule data only.
"""

import csv
import random
from collections import defaultdict
from pathlib import Path

import pytest
from boarding_fixtures import static_overrides
from gtfs_fixtures import write_gtfs_zip

from bart_reliability.api.boarding import (
    Boarding,
    group_boardings,
    group_id,
    group_label,
    opposite_pairs,
)
from bart_reliability.api.boarding_patterns import COLUMNS, boarding_patterns, main, write_patterns

PATTERNS_CSV = Path(__file__).parent / "data" / "bart_boarding_patterns_2026-10-08.csv"

# Stations the audit found where one GTFS direction_id held trains travelling opposite ways:
# every station the Orange line shares with the Green or Blue line, except Berryessa.
DIRECTION_ID_CONFLICTS = [
    "BAYF",
    "COLS",
    "FRMT",
    "FTVL",
    "HAYW",
    "LAKE",
    "MLPT",
    "SANL",
    "SHAY",
    "UCTY",
    "WARM",
]
# Toward San Jose and Dublin, or toward Oakland and beyond, at the stations above.
SOUTH_SIDE = {"Berryessa", "Berryessa/North San Jose", "Union City", "Dublin/Pleasanton"}
NORTH_SIDE = {"Daly City", "Richmond"}


def _load():
    with PATTERNS_CSV.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["boarding"] = Boarding(
            r["station_id"], r["previous_station_id"] or None, r["next_station_id"]
        )
    return rows


PATTERNS = _load()
MAPPING = group_boardings(r["boarding"] for r in PATTERNS)
STATIONS = sorted({r["station_id"] for r in PATTERNS})


def groups_at(station: str) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for r in PATTERNS:
        if r["station_id"] == station:
            out[MAPPING[(station, r["next_station_id"])]].append(r)
    return dict(out)


def by_direction_id(station: str) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for r in PATTERNS:
        if r["station_id"] == station:
            out[r["gtfs_direction_id"]].append(r)
    return dict(out)


def destinations(rows) -> set[str]:
    return {r["destination"] for r in rows}


def platforms(rows) -> set[str]:
    return {r["platform_code"] for r in rows}


def mixes_directions(rows) -> bool:
    return bool(opposite_pairs(r["boarding"] for r in rows))


# -- the Hayward fault and its fix ----------------------------------------------------


def test_hayward_no_longer_mixes_berryessa_with_daly_city_and_richmond():
    old = by_direction_id("HAYW")
    # Before: each direction_id held trains leaving from both platforms, opposite ways.
    assert destinations(old["1"]) >= {"Daly City", "Berryessa/North San Jose"}
    assert destinations(old["0"]) >= {"Richmond", "Berryessa"}
    assert platforms(old["0"]) == platforms(old["1"]) == {"1", "2"}
    assert mixes_directions(old["0"]) and mixes_directions(old["1"])

    groups = groups_at("HAYW")
    assert set(groups) == {"to-SHAY", "to-BAYF"}
    berryessa = {"Berryessa", "Berryessa/North San Jose", "Union City"}
    assert destinations(groups["to-SHAY"]) == berryessa
    assert destinations(groups["to-BAYF"]) == {"Daly City", "Richmond"}
    assert platforms(groups["to-SHAY"]) == {"1"} and platforms(groups["to-BAYF"]) == {"2"}
    assert not any(mixes_directions(g) for g in groups.values())
    # Both lines, both GTFS direction ids, on each platform.
    for g in groups.values():
        assert {r["route_short_name"].split("-")[0] for r in g} == {"Orange", "Green"}
        assert {r["gtfs_direction_id"] for r in g} == {"0", "1"}


def test_direction_id_mixes_opposite_trains_at_exactly_the_audited_stations():
    mixed = [
        s for s in STATIONS if any(mixes_directions(rows) for rows in by_direction_id(s).values())
    ]
    assert mixed == DIRECTION_ID_CONFLICTS


@pytest.mark.parametrize("station", DIRECTION_ID_CONFLICTS)
def test_each_affected_station_now_separates_the_two_sides(station):
    groups = groups_at(station)
    sides = {}
    for gid, rows in groups.items():
        assert not mixes_directions(rows), gid
        dests = destinations(rows)
        if dests == {"Oakland Airport"}:  # Coliseum's airport connector
            continue
        side = "south" if dests <= SOUTH_SIDE else "north" if dests <= NORTH_SIDE else None
        assert side is not None, (gid, dests)
        assert side not in sides, (station, sides, gid)
        sides[side] = gid
    assert set(sides) == {"south", "north"}
    # Each old direction_id is now split across both groups: it could not be kept.
    for rows in by_direction_id(station).values():
        assert len({MAPPING[(station, r["next_station_id"])] for r in rows}) >= 2


# -- the whole network ----------------------------------------------------------------


def test_no_group_anywhere_holds_trains_going_opposite_ways():
    assert len(STATIONS) == 50
    total = 0
    for station in STATIONS:
        groups = groups_at(station)
        total += len(groups)
        for gid, rows in groups.items():
            assert not mixes_directions(rows), (station, gid)
    assert total == 95


def test_terminals_have_one_way_out_and_coliseum_three():
    counts = {s: len(groups_at(s)) for s in STATIONS}
    assert sorted(s for s, n in counts.items() if n == 1) == [
        "ANTC",
        "BERY",
        "DUBL",
        "MLBR",
        "OAKL",
        "RICH",
    ]
    assert [s for s, n in counts.items() if n == 3] == ["COLS"]
    assert all(n in (1, 2, 3) for n in counts.values())


def test_branches_leaving_from_one_side_share_a_group():
    expected = {
        ("BAYF", "to-CAST-HAYW"),  # toward Hayward and toward Castro Valley
        ("MCAR", "to-ASHB-ROCK"),  # toward Richmond and toward Antioch
        ("WOAK", "to-12TH-LAKE"),
        ("LAKE", "to-12TH-WOAK"),
        ("12TH", "to-LAKE-WOAK"),
        ("SBRN", "to-MLBR-SFIA"),
    }
    joined = {(s, gid) for (s, _), gid in MAPPING.items() if gid.count("-") > 1}
    assert joined == expected


def test_sfo_keeps_millbrae_and_san_francisco_apart_although_they_share_platforms():
    groups = groups_at("SFIA")
    assert set(groups) == {"to-MLBR", "to-SBRN"}
    assert platforms(groups["to-MLBR"]) == platforms(groups["to-SBRN"]) == {"1", "2"}
    assert "Millbrae" in destinations(groups["to-MLBR"])
    assert destinations(groups["to-SBRN"]) == {"Antioch", "Pittsburg/Bay Point", "Richmond"}


def test_a_platform_alone_would_mix_directions_at_bay_fair():
    platform_2 = [r for r in PATTERNS if r["station_id"] == "BAYF" and r["platform_code"] == "2"]
    assert mixes_directions(platform_2)  # a few Blue line trains start there toward Dublin
    assert len({MAPPING[("BAYF", r["next_station_id"])] for r in platform_2}) == 2


def test_group_ids_depend_only_on_the_network():
    shuffled = [r["boarding"] for r in PATTERNS]
    random.Random(7).shuffle(shuffled)
    assert group_boardings(shuffled) == MAPPING
    # Frequency plays no part: one train per pattern gives the same groups.
    assert group_boardings({r["boarding"] for r in PATTERNS}) == MAPPING


# -- the fixture and its generator ----------------------------------------------------


def test_fixture_has_the_documented_columns_order_and_line_endings():
    raw = PATTERNS_CSV.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    with PATTERNS_CSV.open(newline="") as f:
        reader = csv.reader(f)
        assert tuple(next(reader)) == COLUMNS
        rows = list(reader)
    keys = [tuple(r[:7]) for r in rows]
    assert keys == sorted(keys) and len(set(keys)) == len(keys) == 347
    assert sum(int(r[8]) for r in rows) == 51672


def test_generator_collapses_repeated_stops_and_leaves_out_buses(tmp_path):
    # The Hayward fixture schedule: two lines each way, a train ending at Hayward, a bus.
    archive = write_gtfs_zip(tmp_path / "gtfs.zip", static_overrides(), source=None)
    rows = boarding_patterns(archive)
    # Sorted by station, neighbours, platform, then route: Green before Orange.
    assert [(r[1], r[2], r[3], r[4], r[7], r[8]) for r in rows if r[0] == "A60"] == [
        ("A50", "A70", "1", "Green-N", "Berryessa", "1"),
        ("A50", "A70", "1", "Orange-S", "Berryessa/North San Jose", "2"),
        ("A70", "A50", "2", "Green-S", "Daly City", "1"),
        ("A70", "A50", "2", "Orange-N", "Richmond", "1"),
    ]  # the bus bridge (route_type 3) and the train ending at Hayward add nothing
    assert not any(r[4] == "BridgeA" for r in rows)
    starts = [r for r in rows if r[1] == ""]
    assert starts and all(r[0] in {"A50", "A70"} for r in starts)  # every trip starts at an end

    # SFO-style: two consecutive stops at one station are one visit, leaving from the last.
    overrides = static_overrides()
    times = overrides["stop_times.txt"]
    trip = [r for r in times if r[0] == "OR_S"]
    for r in trip[2:]:  # make room after Hayward (stop 2)
        r[4] = str(int(r[4]) + 1)
    times.insert(times.index(trip[1]) + 1, ["OR_S", "08:11:00", "08:11:00", "A60-2", "3"])
    rows = boarding_patterns(write_gtfs_zip(tmp_path / "sfo.zip", overrides, source=None))
    # OR_S now stops at platform 1 and then platform 2: one visit, leaving from 2. The
    # other Orange train (OR_MOVED) still leaves from 1. No visit leads to its own station.
    or_s = [(r[1], r[2], r[3], r[8]) for r in rows if r[0] == "A60" and r[4] == "Orange-S"]
    assert or_s == [("A50", "A70", "1", "1"), ("A50", "A70", "2", "1")]
    assert not any(r[0] == r[2] for r in rows)


def test_generator_output_is_deterministic_and_checks_the_archive(tmp_path, capsys):
    archive = write_gtfs_zip(tmp_path / "gtfs.zip", static_overrides(), source=None)
    write_patterns(archive, tmp_path / "a.csv")
    write_patterns(archive, tmp_path / "b.csv")
    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()
    with pytest.raises(SystemExit) as refused:
        main([str(archive), str(tmp_path / "c.csv"), "--sha256", "0" * 64])
    assert refused.value.code == 2 and not (tmp_path / "c.csv").exists()
    assert "expected 000" in capsys.readouterr().err


# -- the rule on constructed cases ----------------------------------------------------


def test_a_group_that_would_hold_opposite_trains_is_split():
    # Trains from P go on to X or Y, so X and Y would be joined; but one train comes from
    # X and goes on to Y, so the joined group would hold X-bound and X-arriving trains.
    boardings = [Boarding("S", "P", "X"), Boarding("S", "P", "Y"), Boarding("S", "X", "Y")]
    assert opposite_pairs(boardings)
    assert group_boardings(boardings) == {("S", "X"): "to-X", ("S", "Y"): "to-Y"}


def test_a_reversing_train_never_joins_the_two_sides():
    boardings = [Boarding("S", "A", "B"), Boarding("S", "B", "A"), Boarding("S", "A", "A")]
    mapping = group_boardings(boardings)
    assert mapping == {("S", "A"): "to-A", ("S", "B"): "to-B"}  # it is placed toward A


def test_starting_trains_join_their_side_by_where_they_go():
    boardings = [Boarding("S", "A", "B"), Boarding("S", None, "B"), Boarding("S", "B", "A")]
    assert group_boardings(boardings) == {("S", "A"): "to-A", ("S", "B"): "to-B"}


def test_group_ids_are_sorted_and_readable():
    assert group_id(["HAYW", "CAST", "HAYW"]) == "to-CAST-HAYW"
    assert group_id(["SHAY"]) == "to-SHAY"


def test_labels_name_each_destination_once():
    assert group_label(["Berryessa", "Berryessa/North San Jose"]) == (
        "Toward Berryessa/North San Jose"
    )
    assert group_label(["Millbrae", "Millbrae (Caltrain Transfer Platform)", "Daly City"]) == (
        "Toward Daly City and Millbrae (Caltrain Transfer Platform)"
    )
    assert group_label(["Richmond", "Daly City"]) == "Toward Daly City and Richmond"
    assert group_label(["A", "B", "C"]) == "Toward A, B and C"
    assert group_label([]) == "Toward unlisted destinations"
