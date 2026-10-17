# Boarding groups: which way a train leaves a station

The website asks a rider where they are boarding and which way they are going, then
lists the trains. Until this change it grouped a station's trains by GTFS `direction_id`.
That field is defined per route, so it cannot stand for a station-wide direction. At
Hayward, "direction 1" held both Green line trains to Daly City and Orange line trains to
Berryessa, which leave from opposite platforms and travel opposite ways.

This document records the audit of BART's static GTFS (feed of 2026-10-08), the rule that
replaced `direction_id`, why the rule holds on BART's network, and its limits.

## Audit

### What the schedule provides

- **50 stations** (`location_type` 1) and **105 platform stops** (`location_type` 0), each
  with a `parent_station` and a `platform_code`. The real-time feed always names a
  platform stop, never a station.
- Platforms per station: 1 at Millbrae and Oakland Airport; 2 at 42 stations; 3 at 12th
  Street, 19th Street, Coliseum, Daly City and SFO; 4 at MacArthur. Two platform stops
  have no scheduled trains (Antioch `E30-1`, SFO `Y10-3`).
- `directions.txt` labels each route's `direction_id` "North" or "South", and each route
  chooses its own. Orange-N (route 3, toward Richmond) and Green-N (route 6, toward
  Berryessa) both use `direction_id` 0, but they travel opposite ways between Lake Merritt
  and Milpitas. Blue-N (toward Dublin/Pleasanton) does the same as Green-N.
- Bus bridges (`BridgeA`, `BridgeB`, `route_type` 3) stop at some rail platforms on
  weekends during planned work. They are not trains and are left out below.

### Method

A **visit** is a trip's consecutive scheduled stops at one station. SFO trips list SFO
twice in a row (arrival, then departure after reversing), and those two stops are one
visit. For each visit that is not the trip's last, the audit records the station the
train comes from, the station it goes to next, and the platform it leaves from. That is a
**boarding**. A visit that ends the trip cannot be boarded.

Two boardings at a station go **physically opposite ways** when one heads to the station
the other has just come from (`a.next == c.previous`). The audit checked every station
for opposite boardings under each grouping, over all 347 distinct rail boarding patterns
in the feed (every rail trip on every service day; see "Real-schedule fixture" below).

### Findings

**`direction_id` grouping is wrong at 11 stations:** Lake Merritt, Fruitvale, Coliseum,
San Leandro, Bay Fair, Hayward, South Hayward, Union City, Fremont, Warm Springs and
Milpitas. These are the stations the Orange line shares with the Green or Blue line. At
each one, both `direction_id` values held trains travelling opposite ways:

| Station | `direction_id` 0 held | `direction_id` 1 held |
|---|---|---|
| Hayward, South Hayward, Union City, Fremont, Warm Springs, Milpitas | Orange to Richmond **and** Green to Berryessa | Green to Daly City **and** Orange to Berryessa (and Union City) |
| Lake Merritt, Fruitvale, Coliseum, San Leandro, Bay Fair | Orange to Richmond **and** Green to Berryessa, Blue to Dublin/Pleasanton | Green and Blue to Daly City **and** Orange to Berryessa (and Union City) |

Berryessa, where both lines end, has only one way out, so nothing there was mixed. The
other 38 stations were unaffected. At those stations every train sharing a
`direction_id` also shares a physical direction.

**The platform is almost, but not exactly, a physical direction:**

- At 42 stations every train leaving one platform travels the same way.
- Some trains that start their trip at a station leave from the "other" platform. At Bay
  Fair a few Blue line trains start on platform 2, the Daly City side, and head for
  Dublin/Pleasanton. Union City and Warm Springs do the same on weekends.
- At SFO, trains to Millbrae and trains to San Francisco leave from the same two
  platforms, because every train reverses there.
- Some single directions use two platforms by line: 12th Street and 19th Street
  northbound use 1 and 3, and MacArthur uses 1 and 3 (and 2 and 4).

So grouping by platform alone would mix opposite directions at Bay Fair and SFO.

## The rule

1. **Boarding groups are built from boardings, not from `direction_id`.** At each
   station, boardings are joined into one group when they go to the same next station or
   come from the same previous station. The result is the set of ways a train can leave
   the station: one per side of the line, joining branches that share a platform side.
   At Bay Fair that is one group toward Hayward or Castro Valley and one toward San
   Leandro.
2. **The build checks every group and refuses to mix directions.** If a group ever held
   two opposite boardings, its boardings are split by next station, and any boarding that
   still conflicts (a train reversing back the way it came) is left out of every group.
   No such case exists in BART's current feed; the tests cover it with synthetic data.
3. **Groups are computed over the whole feed** (every rail trip, every service day), so a
   group keeps its identity from day to day. What a group shows is computed for the
   replay's service date: its destinations, platforms and GTFS direction ids. A group with
   no trains that day is not offered.
4. **The ID is stable and readable.** It is `to-` followed by the group's next stations,
   sorted and joined by `-`: `to-SHAY` and `to-BAYF` at Hayward, `to-CAST-HAYW` at Bay
   Fair. It depends only on the shape of the network, never on frequency or service day.
5. **The label names destinations; the platform is shown only when it is certain.**
   `label` is "Toward …" from the destinations served that day, as before. `platform` is
   that day's platform code when every train in the group leaves from that one platform.
   Otherwise it is `null`, and each train carries its own scheduled platform instead.
6. **Trains are placed by their scheduled stop.** A train listed at a station is placed
   from its schedule. Its matched scheduled stop gives the visit and the next station,
   and the next station gives the group. If the feed lists the train at a platform its
   schedule does not use there, its one scheduled visit to the station is used instead.
   Nothing reads `direction_id`.
   - A train whose visit ends its trip cannot be boarded. It is counted in
     `terminatingTrainCount`, not shown.
   - A train that matches no scheduled trip, or has more than one possible visit, is
     counted in `unplacedTrainCount`. This includes the Antioch extension's real-time
     trips. No direction is invented for it.

### Why this works on BART

BART's lines form a tree with two junction areas, around Oakland (where the trunk splits
toward Richmond, Pittsburg/Bay Point and Fremont/Dublin) and at the SFO/Millbrae wye.
At a station, trains either go on along the line or turn back.

- A train going on leaves toward one neighbour and arrives from another. Every train
  leaving toward the same neighbour is going the same way.
- Two branches that leave from the same side of a station share the station the trains
  just came from, so rule 1 joins them. That covers Bay Fair toward Hayward and Castro
  Valley, and MacArthur toward Ashby and Rockridge.
- Opposite sides never share either neighbour, because one side's next station is the
  other side's previous station. The check in rule 2 makes that a guarantee rather than
  an assumption.

On the 2026-10-08 feed the rule gives:

- 95 groups at 50 stations;
- one group at each true terminal (Antioch, Berryessa, Dublin/Pleasanton, Millbrae,
  Oakland Airport, Richmond);
- three at Coliseum, counting the Oakland Airport connector;
- two everywhere else.

No group holds opposite boardings.

### Hayward, before and after

| | Before (`direction_id`) | After (boarding group) |
|---|---|---|
| Choice 1 | "Toward Berryessa and Richmond": Green to Berryessa (platform 1) and Orange to Richmond (platform 2) | `to-SHAY`, Platform 1: "Toward Berryessa/North San Jose" (Orange and Green) |
| Choice 2 | "Toward Berryessa/North San Jose and Daly City": Orange to Berryessa (platform 1) and Green to Daly City (platform 2) | `to-BAYF`, Platform 2: "Toward Daly City and Richmond" (Green and Orange) |

The replay at 2026-10-15 10:00 PDT showed the old fault directly. Hayward's direction-1
board listed Green line trains on platform `A60-2` and Orange line trains on `A60-1`.

## Old links

Links written before this change carry `?direction=0|1`. Such a link is translated only
when it is unambiguous: when exactly one group at the station carries that GTFS direction
id. At Embarcadero, `direction=0` becomes `to-WOAK`. At Hayward both groups carry both
ids, so the link is not translated. The page then shows the first group and says why.
Each group lists its `gtfsDirectionIds` only for this translation, and nothing else uses
them.

## Tests

- `tests/test_boarding_groups.py` checks the rule on all 347 rail boarding patterns of
  the 2026-10-08 feed (`tests/data/bart_boarding_patterns_2026-10-08.csv`, schedule data
  only; see "Real-schedule fixture"). It checks that:
  - `direction_id` mixes opposite trains at exactly the 11 stations above;
  - each of those stations now separates its two sides;
  - no group anywhere holds opposite trains, giving 95 groups at 50 stations;
  - terminals have one group, and branches leaving one side share a group;
  - SFO keeps Millbrae and San Francisco apart although they share platforms;
  - the IDs do not depend on order or frequency.

  Constructed cases cover the split and a reversing train.
- `tests/test_local_api.py` builds a small Hayward warehouse (`tests/boarding_fixtures.py`)
  with the Orange and Green lines' own `direction_id` values. It checks the API's groups,
  platforms and boards, and covers:
  - a train listed at an unscheduled platform;
  - a train ending at Hayward;
  - an unmatched real-time trip;
  - a bus bridge that must not affect the platform.
- The website's tests check Hayward over the recorded replay and over the full mock
  network, old `?direction=` links (translated, ambiguous and unmatched), and back and
  forward navigation.

## Real-schedule fixture

`tests/data/bart_boarding_patterns_2026-10-08.csv` is derived from one archive, recorded
in [warehouse.md](warehouse.md#selected-archive-checked-2026-10-10):

- **Archive:** BART's static GTFS from
  `https://www.bart.gov/sites/default/files/2026-08/google_transit_20260810-20270108_v02.zip`.
  The local copy is `data/raw/gtfs_static/2026-10-08/google_transit.zip`, which is
  ignored by Git and never committed.
- **SHA-256:** `affdc4d70cac01f71e54f049c754ba36824a885edcdef2ef8b024820c9e93080`

Regenerate it from the repository root (the command refuses an archive with any other
hash):

```bash
.venv/bin/python -m bart_reliability.api.boarding_patterns \
    data/raw/gtfs_static/2026-10-08/google_transit.zip \
    tests/data/bart_boarding_patterns_2026-10-08.csv \
    --sha256 affdc4d70cac01f71e54f049c754ba36824a885edcdef2ef8b024820c9e93080
```

The generator is `src/bart_reliability/api/boarding_patterns.py`. It reads `stops.txt`,
`routes.txt`, `trips.txt` and `stop_times.txt` from the archive, keeps rail routes
(`route_type` 1) only, and writes UTF-8 CSV with LF line endings. The same archive always
gives the same bytes (SHA-256 of the current file:
`225037f5032d90e144b1e3357829bdc5fb6f072f6c68422ee1179775ea4edd64`). The file has 347 rows
plus a header.

| Column | Meaning |
|---|---|
| `station_id` | Parent station of the visit (consecutive stops at one station are one visit) |
| `previous_station_id` | Station of the trip's previous visit; empty where the trip starts |
| `next_station_id` | Station of the trip's next visit (a visit that ends the trip is not a boarding) |
| `platform_code` | `platform_code` of the visit's last stop, where the train leaves from |
| `route_short_name` | Route, e.g. `Orange-S` |
| `gtfs_direction_id` | The trip's `direction_id`, route-relative |
| `trip_headsign` | The trip's headsign |
| `destination` | The headsign's last part (`SFO / SF / Antioch` gives `Antioch`) |
| `scheduled_departures` | Number of such boardings over every service day in the archive |

Each row is one distinct combination of the first seven columns. Rows are sorted by those
seven columns as plain strings, so an empty `previous_station_id` sorts first. The tests
check the header, the order, uniqueness, the row count and the departure total.

## Limits

- **Schedule-based.** Groups and platforms come from the static schedule. A platform
  change on the day is not detected, except that a train listed at an unscheduled
  platform shows no platform number.
- **Network changes.** A new station or line changes the neighbours, and with them the
  group IDs of the stations next to it. Old links then fall back with a note.
- **Oakland Airport connector.** Its group at Coliseum and Oakland Airport is offered,
  but BART publishes no real-time trips for it (`realtime_routes.txt`), so its board is
  always empty.
- **Antioch extension.** Its real-time trips match no scheduled trip, so they stay
  unplaced at Antioch and Pittsburg Center.
