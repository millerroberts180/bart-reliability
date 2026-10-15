import type { CSSProperties } from 'react';
import {
  addSeconds,
  describeRevision,
  describeRevisionRange,
  describeTimeAway,
  formatClock,
  formatClockMinute,
  formatClockSince,
  formatDuration,
  formatPercent,
  formatSpokenDuration,
  likelyFinalEtaSeconds,
  describeAwayGlance,
  formatMoment,
  needsSeconds,
  STABILITY_CUTOFFS,
  STABILITY_LABELS,
  STALE_AFTER_SECONDS,
} from '../domain/eta';
import { routeColor } from '../domain/routeColors';
import { hasForecast, type AlertContext, type EtaOnlyTrain, type ForecastTrain, type TrainPrediction } from '../domain/types';
import { useFreshness } from '../hooks/useFreshness';
import type { ReceivedPredictions } from './PredictionExample';
import { StabilityMark } from './StabilityMark';

export type ReadoutState =
  | { kind: 'loading' }
  | { kind: 'error'; retry: () => void }
  | {
      kind: 'empty';
      /** Trains listed at the station whose direction is unknown (see PredictionResponse). */
      unplacedTrainCount: number;
      /** Whether trains in the chosen direction end their trips at this station. */
      endsHere: boolean;
    }
  | { kind: 'ready'; received: ReceivedPredictions; train: TrainPrediction };

interface PredictionReadoutProps {
  state: ReadoutState;
  stationName: string;
  directionLabel: string;
}

export function PredictionReadout({ state, stationName, directionLabel }: PredictionReadoutProps) {
  const announcement = {
    loading: 'Loading prediction.',
    error: 'Prediction unavailable.',
    empty: 'No upcoming trains.',
    ready: state.kind === 'ready' ? describePrediction(state.train, stationName) : '',
  }[state.kind];

  return (
    <section
      className={`readout readout--${state.kind}`}
      aria-labelledby="readout-title"
      aria-busy={state.kind === 'loading'}
    >
      <p className="visually-hidden" aria-live="polite">
        {announcement}
      </p>
      {state.kind === 'loading' && <LoadingReadout />}
      {state.kind === 'error' && (
        <div className="readout__message">
          <h3 id="readout-title">Prediction unavailable</h3>
          <p>
            The request for {stationName ? `${stationName} ` : ''}predictions failed. No estimate is shown, so an
            outdated one can’t be mistaken for a current one.
          </p>
          <button type="button" className="button" onClick={state.retry}>
            Try again
          </button>
        </div>
      )}
      {state.kind === 'empty' && (
        <div className="readout__message">
          <h3 id="readout-title">No upcoming trains</h3>
          <p>
            The latest snapshot lists no trains {lowerFirst(directionLabel)} from {stationName}.{' '}
            {emptyReason(state.unplacedTrainCount, state.endsHere, stationName)}
          </p>
        </div>
      )}
      {state.kind === 'ready' && <ReadyReadout {...state} stationName={stationName} directionLabel={directionLabel} />}
    </section>
  );
}

/**
 * Why a board can be empty, said only from what the response shows. BART's feed almost
 * never lists a train at the last stop of its trip, and trains that match no scheduled
 * trip have no direction (docs/local_api.md, "Empty boards").
 */
function emptyReason(unplaced: number, endsHere: boolean, stationName: string): string {
  const reasons: string[] = [];
  if (endsHere) {
    reasons.push(
      `Trains toward ${stationName} end their trips here, and BART’s feed almost never lists a train at the last stop of its trip.`,
    );
  }
  if (unplaced > 0) {
    reasons.push(
      unplaced === 1
        ? `BART’s feed does list 1 train at ${stationName} that matches no scheduled trip, so its direction isn’t known and it isn’t shown.`
        : `BART’s feed does list ${unplaced} trains at ${stationName} that match no scheduled trip, so their direction isn’t known and they aren’t shown.`,
    );
  }
  if (reasons.length === 0) {
    reasons.push(
      'Service may have ended for the night, this direction may not be running right now, or BART’s feed may not include it.',
    );
  }
  return reasons.join(' ');
}

function LoadingReadout() {
  // Mirrors the ready layout so nothing jumps when the prediction arrives.
  return (
    <>
      <div className="readout__heading">
        <h3 id="readout-title" className="readout__title">
          Loading prediction…
        </h3>
        <span className="readout__meta placeholder placeholder--short" />
      </div>
      <div className="forecast" aria-hidden="true">
        <p className="forecast__label">Likely final published ETA</p>
        <span className="placeholder placeholder--clock" />
        <span className="placeholder placeholder--short" />
      </div>
      <div className="calc" aria-hidden="true">
        {['BART currently says', 'Expected adjustment', 'Likely final published ETA'].map((label) => (
          <div key={label} className="calc__row">
            <span className="calc__label">{label}</span>
            <span className="placeholder placeholder--short" />
          </div>
        ))}
      </div>
    </>
  );
}

function ReadyReadout({
  received,
  train,
  stationName,
  directionLabel,
}: {
  received: ReceivedPredictions;
  train: TrainPrediction;
  stationName: string;
  directionLabel: string;
}) {
  const { response, receivedAt } = received;
  const { replay } = response;
  const freshness = useFreshness(response.feedTimestamp, receivedAt, replay);
  const forecast = hasForecast(train);

  return (
    <div className={freshness.stale ? 'readout__body is-stale' : 'readout__body'}>
      {/* Train identity, the forecast and its calculation share one route rail. */}
      <div className="result-block" style={{ '--route': routeColor(train.lineName) } as CSSProperties}>
        <div className="readout__heading">
          <h3 id="readout-title" className="readout__title">
            {stationName} · {train.headsign} train
          </h3>
          <p className="readout__meta">
            <span className="route-tag">
              <span className="route-tag__swatch" aria-hidden="true" />
              {train.lineName}
            </span>
            <span className="readout__meta-item">{directionLabel}</span>
            {train.carCount !== null && <span className="readout__meta-item">{train.carCount} cars</span>}
            <span className="readout__meta-item">Trip {train.tripId}</span>
            {response.model.simulated && <span className="sim-tag">Simulated</span>}
            {replay && <span className="sim-tag replay-tag">Historical replay</span>}
          </p>
        </div>

        {replay && (
          <p className="notice notice--replay" data-testid="replay-notice">
            <strong>Historical replay, not live.</strong> Recorded BART data as of {formatMoment(replay.asOf)}{' '}
            Pacific. The forecast uses only what was known at that moment.
          </p>
        )}

        {freshness.stale && (
          <p className="notice notice--stale" role="status">
            <strong>Stale data.</strong> This snapshot is from {formatClockMinute(response.feedTimestamp)},{' '}
            {formatSpokenDuration(freshness.ageSeconds)} {replay ? 'before the replay time' : 'ago'}, past the{' '}
            {formatSpokenDuration(STALE_AFTER_SECONDS)} freshness limit. Times away are counted from then, and BART may
            already have revised this estimate.
          </p>
        )}

        {forecast ? (
          <ForecastResult train={train} stale={freshness.stale} feedTimestamp={response.feedTimestamp} />
        ) : (
          <EtaOnlyResult train={train} stale={freshness.stale} feedTimestamp={response.feedTimestamp} />
        )}
      </div>

      <div className="details">
        {forecast ? (
          <ForecastDetails train={train} threshold={response.model.revisionThresholdSeconds} stationName={stationName} />
        ) : (
          <p className="readout__caveat">
            BART may revise this estimate. Without a model forecast, the page shows BART’s published ETA exactly as
            BART published it.
          </p>
        )}

        <dl className="facts">
          <div className="facts__row">
            <dt>Service alerts</dt>
            <dd>
              <AlertList alerts={response.alerts} feedTimestamp={response.feedTimestamp} />
            </dd>
          </div>
          <div className="facts__row">
            <dt>Feed snapshot</dt>
            <dd>
              <span className={`freshness ${freshness.stale ? 'freshness--stale' : 'freshness--current'}`}>
                {freshness.stale ? 'Stale' : 'Current'}
              </span>{' '}
              {formatClock(response.feedTimestamp)} · {formatDuration(freshness.ageSeconds)} old
              {replay ? ' at the replay time' : ''}. Times away are counted from this snapshot.
            </dd>
          </div>
          <div className="facts__row">
            <dt>Model timestamp</dt>
            <dd>
              {formatClock(response.generatedAt)}
              {replay ? ' (replay time)' : ''} · {response.model.modelVersion}
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}

function ForecastResult({ train, stale, feedTimestamp }: { train: ForecastTrain; stale: boolean; feedTimestamp: string }) {
  const current = train.currentEtaSeconds;
  const revision = train.predictedRevisionSeconds;
  const final = likelyFinalEtaSeconds(current, revision);
  const finalAt = addSeconds(train.currentEtaAt, revision);
  const interval = train.revisionInterval;
  // The large forecast is always minute precision. The calculation's two clocks add
  // seconds only when the minute alone would hide the adjustment.
  const seconds = needsSeconds(train.currentEtaAt, finalAt);
  const nowLabel = stale ? `BART said at ${formatClockMinute(feedTimestamp)}` : 'BART currently says';

  return (
    <>
      <div className="forecast" data-testid="forecast">
        <p className="forecast__label">Likely final published ETA</p>
        <p className="forecast__clock">
          <ClockTime iso={finalAt} />
        </p>
        <p className="forecast__away">{describeAwayGlance(final)}</p>
        {interval ? (
          <p className="forecast__range">
            {coverageOf(interval.level)} likely range: {formatSpokenDuration(likelyFinalEtaSeconds(current, interval.lowerSeconds))}{' '}
            to {describeTimeAway(likelyFinalEtaSeconds(current, interval.upperSeconds))}
          </p>
        ) : (
          <p className="forecast__range forecast__range--none" data-testid="no-range">
            No likely range is shown: the model’s range isn’t supported for this data.
          </p>
        )}
        <p className="forecast__basis">Model forecast of BART’s last published ETA, not an observed arrival.</p>
      </div>

      <dl className="calc" aria-label="How the forecast is calculated">
        <div className="calc__row" data-testid="calc-now">
          <dt>{nowLabel}</dt>
          <dd>
            <span className="nowrap">{formatClockFor(train.currentEtaAt, seconds)}</span>{' '}
            <span className="nowrap">· {describeTimeAway(current)}</span>
          </dd>
        </div>
        <div className="calc__row" data-testid="calc-adjust">
          <dt>
            <span className="calc__op" aria-hidden="true">
              +
            </span>
            Expected adjustment
          </dt>
          <dd>{capitalize(describeRevision(revision))}</dd>
        </div>
        <div className="calc__row calc__row--total" data-testid="calc-final">
          <dt>
            <span className="calc__op" aria-hidden="true">
              =
            </span>
            Likely final published ETA
          </dt>
          <dd>
            <span className="nowrap">{formatClockFor(finalAt, seconds)}</span>{' '}
            <span className="nowrap">· {describeAwayAbout(final)}</span>
          </dd>
        </div>
      </dl>
    </>
  );
}

/** A train outside the model's support: BART's published ETA, as published, and why. */
function EtaOnlyResult({ train, stale, feedTimestamp }: { train: EtaOnlyTrain; stale: boolean; feedTimestamp: string }) {
  const nowLabel = stale ? `BART said at ${formatClockMinute(feedTimestamp)}` : 'BART currently says';
  return (
    <>
      <div className="forecast forecast--eta-only" data-testid="forecast">
        <p className="forecast__label">BART’s published ETA</p>
        <p className="forecast__clock">
          <ClockTime iso={train.currentEtaAt} />
        </p>
        <p className="forecast__away">{describeAwayGlance(train.currentEtaSeconds)}</p>
        <p className="forecast__range forecast__range--none" data-testid="no-forecast">
          {NO_FORECAST_REASON[train.predictionStatus]}
        </p>
      </div>
      <dl className="calc" aria-label="BART’s published ETA">
        <div className="calc__row" data-testid="calc-now">
          <dt>{nowLabel}</dt>
          <dd>
            <span className="nowrap">{formatClock(train.currentEtaAt)}</span>{' '}
            <span className="nowrap">· {describeTimeAway(train.currentEtaSeconds)}</span>
          </dd>
        </div>
      </dl>
    </>
  );
}

const NO_FORECAST_REASON: Record<EtaOnlyTrain['predictionStatus'], string> = {
  outside_model_horizon:
    'No model forecast right now. The model only forecasts trains BART shows about 5, 10 or 15 minutes away.',
  outside_model_population: 'No model forecast: the model was not trained on trains like this one.',
  fallback_required: 'No model forecast: this train is outside what the model has been shown to support.',
  features_unavailable: 'No model forecast: some model inputs were missing from this snapshot.',
};

function ForecastDetails({
  train,
  threshold,
  stationName,
}: {
  train: ForecastTrain;
  threshold: number;
  stationName: string;
}) {
  const interval = train.revisionInterval;
  return (
    <>
      <p className="details__item">
        <span className="details__label">Adjustment range{interval ? ` (${coverageOf(interval.level)})` : ''}</span>{' '}
        {interval
          ? capitalize(describeRevisionRange(interval.lowerSeconds, interval.upperSeconds))
          : 'Not available for this forecast.'}
      </p>

      <div className={`stability tone-${train.stability}`}>
        <p className="stability__class">
          <span className="stability__label">ETA stability</span>
          <StabilityMark stability={train.stability} />
          {STABILITY_LABELS[train.stability]}
        </p>
        <p className="stability__detail">
          <span className="stability__percent">{formatPercent(train.revisionProbability)}</span> chance BART changes
          this estimate by more than {threshold} seconds, earlier or later. Under 25%: likely to hold. 25% to 50%: may
          be revised. 50% or more: likely to be revised.
        </p>
        <ProbabilityScale probability={train.revisionProbability} />
      </div>

      <p className="readout__caveat">
        BART may revise this estimate. The likely final published ETA is the model’s forecast of the last ETA BART will
        publish before the train reaches {stationName}. It is not an observed arrival time.
      </p>
    </>
  );
}

function coverageOf(level: number): string {
  return `${Math.round(level * 100)}%`;
}

function formatClockFor(iso: string, seconds: boolean): string {
  return seconds ? formatClock(iso) : formatClockMinute(iso);
}

/** "5:58" with a smaller "PM", always to the minute; the two never wrap apart. */
function ClockTime({ iso }: { iso: string }) {
  const text = formatClockMinute(iso);
  const split = text.lastIndexOf(' ');
  return (
    <span className="clock">
      {text.slice(0, split)}
      <span className="clock__meridiem">{text.slice(split)}</span>
    </span>
  );
}

function ProbabilityScale({ probability }: { probability: number }) {
  const pct = (v: number) => `${Math.min(100, Math.max(0, v * 100))}%`;
  return (
    <div className="scale" aria-hidden="true">
      <div className="scale__track">
        <span className="scale__fill" style={{ width: pct(probability) }} />
        <span className="scale__tick" style={{ left: pct(STABILITY_CUTOFFS.mayBeRevised) }} />
        <span className="scale__tick" style={{ left: pct(STABILITY_CUTOFFS.likelyToBeRevised) }} />
      </div>
      <div className="scale__labels">
        <span>0%</span>
        <span style={{ left: pct(STABILITY_CUTOFFS.mayBeRevised) }}>25%</span>
        <span style={{ left: pct(STABILITY_CUTOFFS.likelyToBeRevised) }}>50%</span>
        <span>100%</span>
      </div>
    </div>
  );
}

const ALERT_SCOPE: Record<AlertContext['scope'], string> = {
  system: 'Systemwide',
  route: 'Line',
  station: 'Station',
};
const ALERT_CATEGORY: Record<AlertContext['category'], string> = {
  planned_work: 'planned work',
  incident: 'incident',
  unclassified: 'unclassified',
};

function AlertList({ alerts, feedTimestamp }: { alerts: AlertContext[]; feedTimestamp: string }) {
  if (alerts.length === 0) return <>None visible in the feed for this station.</>;
  return (
    <ul className="alerts">
      {alerts.map((a) => (
        <li key={a.alertId}>
          <span className="alerts__scope">
            {ALERT_SCOPE[a.scope]} · {ALERT_CATEGORY[a.category]} · visible since {formatClockSince(a.visibleSince, feedTimestamp)}
          </span>
          <span className="alerts__text">{a.headerText}</span>
        </li>
      ))}
      <li className="alerts__note">An alert in the feed is context, not proof of a delay or a change to this train.</li>
    </ul>
  );
}

/**
 * Screen-reader reading of the result: the glanceable forecast first, then the exact
 * calculation. The glance values are labelled as rounded so they never conflict with
 * the exact ones.
 */
export function describePrediction(train: TrainPrediction, stationName: string): string {
  if (!hasForecast(train)) {
    return (
      `${stationName}, ${train.headsign} train. ` +
      `BART’s published ETA: ${formatClockMinute(train.currentEtaAt)}, ${lowerFirst(describeAwayGlance(train.currentEtaSeconds))}. ` +
      `${NO_FORECAST_REASON[train.predictionStatus]}`
    );
  }
  const final = likelyFinalEtaSeconds(train.currentEtaSeconds, train.predictedRevisionSeconds);
  const finalAt = addSeconds(train.currentEtaAt, train.predictedRevisionSeconds);
  const seconds = needsSeconds(train.currentEtaAt, finalAt);
  return (
    `${stationName}, ${train.headsign} train. ` +
    `Likely final published ETA: ${formatClockMinute(finalAt)}, ${lowerFirst(describeAwayGlance(final))}. ` +
    `Exact calculation: BART currently says ${formatClockFor(train.currentEtaAt, seconds)}, ` +
    `${describeTimeAway(train.currentEtaSeconds)}; expected adjustment ${describeRevision(train.predictedRevisionSeconds)}; ` +
    `likely final published ETA ${formatClockFor(finalAt, seconds)}, ${describeAwayAbout(final)}.`
  );
}

function describeAwayAbout(seconds: number): string {
  return Math.round(seconds) <= 0 ? 'due now' : `about ${describeTimeAway(seconds)}`;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}
