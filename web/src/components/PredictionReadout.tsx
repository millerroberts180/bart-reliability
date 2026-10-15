import type { CSSProperties } from 'react';
import {
  addSeconds,
  describeRevision,
  describeRevisionRange,
  describeTimeAway,
  formatClock,
  formatClockMinute,
  formatDuration,
  formatPercent,
  formatSpokenDuration,
  likelyFinalEtaSeconds,
  describeAwayGlance,
  needsSeconds,
  STABILITY_CUTOFFS,
  STABILITY_LABELS,
  STALE_AFTER_SECONDS,
} from '../domain/eta';
import { routeColor } from '../domain/routeColors';
import type { AlertContext, TrainPrediction } from '../domain/types';
import { useFreshness } from '../hooks/useFreshness';
import type { ReceivedPredictions } from './PredictionExample';
import { StabilityMark } from './StabilityMark';

export type ReadoutState =
  | { kind: 'loading' }
  | { kind: 'error'; retry: () => void }
  | { kind: 'empty' }
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
            The latest snapshot lists no trains {lowerFirst(directionLabel)} from {stationName}. Service may have
            ended for the night, or this direction may not be running right now.
          </p>
        </div>
      )}
      {state.kind === 'ready' && <ReadyReadout {...state} stationName={stationName} directionLabel={directionLabel} />}
    </section>
  );
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
  const freshness = useFreshness(response.feedTimestamp, receivedAt);

  const current = train.currentEtaSeconds;
  const revision = train.predictedRevisionSeconds;
  const final = likelyFinalEtaSeconds(current, revision);
  const finalAt = addSeconds(train.currentEtaAt, revision);
  const { lowerSeconds, upperSeconds, level } = train.revisionInterval;
  const coverage = `${Math.round(level * 100)}%`;
  const threshold = response.model.revisionThresholdSeconds;
  // The large forecast is always minute precision. The calculation's two clocks add
  // seconds only when the minute alone would hide the adjustment.
  const seconds = needsSeconds(train.currentEtaAt, finalAt);
  const nowLabel = freshness.stale ? `BART said at ${formatClockMinute(response.feedTimestamp)}` : 'BART currently says';

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
          </p>
        </div>

        {freshness.stale && (
          <p className="notice notice--stale" role="status">
            <strong>Stale data.</strong> This snapshot is from {formatClockMinute(response.feedTimestamp)},{' '}
            {formatSpokenDuration(freshness.ageSeconds)} ago, past the {formatSpokenDuration(STALE_AFTER_SECONDS)}{' '}
            freshness limit. Times away are counted from then, and BART may already have revised this estimate.
          </p>
        )}

        <div className="forecast" data-testid="forecast">
          <p className="forecast__label">Likely final published ETA</p>
          <p className="forecast__clock">
            <ClockTime iso={finalAt} />
          </p>
          <p className="forecast__away">{describeAwayGlance(final)}</p>
          <p className="forecast__range">
            {coverage} likely range: {formatSpokenDuration(likelyFinalEtaSeconds(current, lowerSeconds))} to{' '}
            {describeTimeAway(likelyFinalEtaSeconds(current, upperSeconds))}
          </p>
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
      </div>

      <div className="details">
        <p className="details__item">
          <span className="details__label">Adjustment range ({coverage})</span>{' '}
          {capitalize(describeRevisionRange(lowerSeconds, upperSeconds))}
        </p>

        <div className={`stability tone-${train.stability}`}>
          <p className="stability__class">
            <span className="stability__label">ETA stability</span>
            <StabilityMark stability={train.stability} />
            {STABILITY_LABELS[train.stability]}
          </p>
          <p className="stability__detail">
            <span className="stability__percent">{formatPercent(train.revisionProbability)}</span> chance BART changes
            this estimate by more than {threshold} seconds, earlier or later. Under 25%: likely to hold. 25% to 50%:
            may be revised. 50% or more: likely to be revised.
          </p>
          <ProbabilityScale probability={train.revisionProbability} />
        </div>

        <p className="readout__caveat">
          BART may revise this estimate. The likely final published ETA is the model’s forecast of the last ETA BART
          will publish before the train reaches {stationName}. It is not an observed arrival time.
        </p>

        <dl className="facts">
          <div className="facts__row">
            <dt>Service alerts</dt>
            <dd>
              <AlertList alerts={response.alerts} />
            </dd>
          </div>
          <div className="facts__row">
            <dt>Feed snapshot</dt>
            <dd>
              <span className={`freshness ${freshness.stale ? 'freshness--stale' : 'freshness--current'}`}>
                {freshness.stale ? 'Stale' : 'Current'}
              </span>{' '}
              {formatClock(response.feedTimestamp)} · {formatDuration(freshness.ageSeconds)} old. Times away are
              counted from this snapshot.
            </dd>
          </div>
          <div className="facts__row">
            <dt>Model timestamp</dt>
            <dd>
              {formatClock(response.generatedAt)} · {response.model.modelVersion}
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
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

function AlertList({ alerts }: { alerts: AlertContext[] }) {
  if (alerts.length === 0) return <>None visible in the feed for this station.</>;
  return (
    <ul className="alerts">
      {alerts.map((a) => (
        <li key={a.alertId}>
          <span className="alerts__scope">
            {ALERT_SCOPE[a.scope]} · {ALERT_CATEGORY[a.category]} · visible since {formatClock(a.visibleSince)}
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
