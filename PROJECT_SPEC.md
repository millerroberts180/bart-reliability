# BART Reliability Lab — Project Specification

**Created:** October 9, 2026  
**Status:** Initial specification

## Project question

How accurate are BART’s published real-time arrival predictions, under what conditions do they become unreliable, and can a statistical correction model improve them?

## Project objective

Build a reproducible Python and SQL pipeline that collects BART’s real-time predictions, matches them with subsequently observed arrivals, measures prediction accuracy, and evaluates a residual-correction model.

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

Evaluate predictions made approximately:

- 5 minutes before arrival
- 10 minutes before arrival
- 15 minutes before arrival

When no prediction exists at the exact horizon, select the most recent eligible prediction within a documented tolerance window. The tolerance must be finalized before calculating results.

## Initial scope and exclusions

The first version will analyze ordinary BART rail service.

Initially exclude:

- Antioch extension trips whose real-time trip identifiers do not align reliably with static GTFS
- Oakland Airport Connector trips because comparable real-time arrival information is unavailable
- Predictions that cannot be matched confidently to one scheduled trip
- Records with invalid timestamps or malformed protobuf data

Excluded records must be counted and reported rather than silently deleted.

## Primary metrics

Report the following for each evaluation horizon:

- Mean absolute error
- Median absolute error
- 90th-percentile absolute error
- Percentage of predictions within ±1 minute
- Percentage of predictions within ±2 minutes
- Mean signed error to identify systematically early or late predictions
- Sample size and exclusion rate

Break results down by station, direction, hour, weekday, prediction horizon, and service-alert status.

## Modeling plan

Begin with two references:

1. BART’s published prediction
2. A simple historical-error baseline

Then train a residual-correction model:

```text
Corrected prediction = BART prediction + predicted residual error
```

Potential features include station, direction, time of day, weekday, published minutes to arrival, recent prediction movement, previous-stop errors, and active alerts.

Split data chronologically:

- Earlier observations for training
- Later observations for validation
- Most recent observations for final testing

Do not use random splitting. The correction model will be considered useful only if it improves held-out performance or reveals meaningful reliability patterns. A result showing no improvement is acceptable if evaluated honestly.

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

- Evaluate BART predictions on a chronological held-out test period
- Compare BART against a historical baseline and correction model
- Report accuracy at 5-, 10-, and 15-minute horizons
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
- Claiming causal effects from observational results