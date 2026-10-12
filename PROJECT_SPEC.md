# BART Reliability Lab — Project Specification

**Created:** October 9, 2026  
**Revised:** October 12, 2026 (reframed around ETA revision; see "Why not arrival accuracy")\
**Status:** Active specification

## Project question

How stable are BART’s published arrival estimates (ETAs), and where and when are they most likely to be revised as a train approaches?

## Why not arrival accuracy

The original question asked how accurate BART’s predictions are against actual arrivals. BART does not publish an independent vehicle-location (AVL) or actual-arrival feed, so actual arrivals cannot be observed from public data. The closest available reference is BART’s own **final stable published estimate** for a stop, taken when the feed shows the train has moved past it (`observed_arrival_proxy`, see `docs/observed_arrival_proxy.md`).

That reference comes from the same system that publishes the predictions, so comparing against it is circular: it measures how much an ETA is **revised** before the train reaches the stop, not how close the ETA was to the physical arrival. This project therefore studies ETA revision. It never reports the proxy as an observed arrival or the revision as arrival-accuracy error. Evaluating physical accuracy would require an independent AVL or actual-arrival source, which BART does not publish.

## Project objective

Build a reproducible Python and SQL pipeline that collects BART’s real-time predictions, reconstructs each trip-stop’s ETA history against its final stable published estimate, measures how ETAs are revised as trains approach, and evaluates a model that predicts whether and by how much an ETA will be revised.

The project should demonstrate:

- Python data collection and transformation
- SQL joins, window functions, aggregations, and temporal analysis
- Data-quality testing
- Leakage-safe machine-learning evaluation
- Clear communication through an interactive dashboard

## Data sources

1. **Static GTFS:** Scheduled trips, routes, stops, and stop times
2. **GTFS-Realtime Trip Updates:** Published arrival predictions
3. **GTFS-Realtime Alerts:** Service disruption information
4. **BART ridership data:** Hourly origin-destination counts used for rider-weighted analysis

No BART API key is required for the GTFS or GTFS-Realtime feeds.

## Collection plan

- Poll trip updates and alerts every 60 seconds.
- Record the collection time in UTC.
- Preserve the timestamp supplied by the feed.
- Validate every response before storing it.
- Initially save valid responses as raw protobuf files.
- Compact raw snapshots into hourly Parquet files.
- Query the processed data through DuckDB.

Proposed storage flow:

```text
Raw protobuf snapshots → hourly Parquet files → DuckDB SQL tables
```

## Evaluation horizons

Measure ETA revision for estimates published approximately:

- 5 minutes before the final stable estimate
- 10 minutes before the final stable estimate
- 15 minutes before the final stable estimate

Horizons are measured as time to the final stable estimate, not as the horizon BART published. When no estimate exists at the exact horizon, select the nearest eligible estimate within the documented tolerance (±60 seconds; `config/eta_revision.toml`). The final estimates that define the reference are never used as horizon estimates.

## Initial scope and exclusions

The first version will analyze ordinary BART rail service.

Initially exclude:

- Antioch extension trips whose real-time trip identifiers do not align reliably with static GTFS
- Oakland Airport Connector trips because comparable real-time arrival information is unavailable
- Predictions that cannot be matched confidently to one scheduled trip
- Records with invalid timestamps or malformed protobuf data

Excluded records must be counted and reported rather than silently deleted.

## Primary metrics

`eta_revision_seconds` = final stable published estimate − estimate published at the horizon. Positive values mean the ETA later moved later; negative values mean it later moved earlier. Both describe movement relative to the final stable published estimate, not error against an observed arrival.

Report the following for each horizon:

- Mean absolute ETA revision (`absolute_eta_revision_seconds`)
- Median absolute ETA revision
- 90th-percentile absolute ETA revision
- Percentage of ETAs revised by at most ±1 minute
- Percentage of ETAs revised by at most ±2 minutes
- Mean signed ETA revision, to identify systematic revision later or earlier
- Sample size, quality tier, and exclusion rate

Break results down by station, direction, hour, weekday, prediction horizon, and service-alert status.

## Modeling plan

Goal: predict **whether and by how much** a published ETA will be revised before the train reaches the stop:

- a classification target (revised by more than ±60 seconds, and in which direction), and
- a regression target (`eta_revision_seconds`).

Begin with two references:

1. No revision: assume the published ETA will not change
2. A simple historical-revision baseline (e.g. mean revision by station, horizon, and hour)

Potential features include station, direction, time of day, weekday, time to the final estimate, recent ETA movement, revisions at upstream stops, and active alerts. Features must only use information available when the ETA was published.

Split data chronologically:

- Earlier observations for training
- Later observations for validation
- Most recent observations for final testing

Do not use random splitting. The revision model will be considered useful only if it improves held-out performance over both references or reveals meaningful revision patterns. A result showing no improvement is acceptable if evaluated honestly. The model predicts revision of BART’s published ETAs; it makes no claim about physical arrival times.

## Initial success criterion

The collector must run continuously for 24 hours and:

- Complete at least 99% of expected polling intervals
- Avoid overwriting snapshots
- Successfully validate every stored protobuf file
- Recover automatically from temporary network failures
- Produce enough logging to identify missing intervals and failures
- Restart without corrupting previously collected data

## Final success criterion

The finished project must:

- Evaluate ETA revision prediction on a chronological held-out test period
- Compare a revision model against the no-revision and historical-revision baselines
- Report ETA revision at 5-, 10-, and 15-minute horizons
- Include rider-weighted reliability analysis
- Provide reproducible Python and SQL code
- Include automated tests and data-quality checks
- Present the findings in a public Streamlit dashboard
- Document assumptions, exclusions, limitations, and unsuccessful approaches

## Out of scope for version one

- Providing arrival predictions to actual passengers
- Building a mobile application
- Modeling other Bay Area transit agencies
- Streaming infrastructure such as Kafka or Spark
- Deep-learning models
- Reproducing BART’s internal prediction system
- Claiming physical arrival accuracy without an independent AVL or actual-arrival source
- Claiming causal effects from observational results