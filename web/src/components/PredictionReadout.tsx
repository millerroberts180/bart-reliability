import {
  addSeconds,
  assessFreshness,
  describeRevision,
  describeRevisionRange,
  describeTimeAway,
  formatClock,
  formatClockMinute,
  formatDuration,
  formatPercent,
  formatSpokenDuration,
  likelyFinalEtaSeconds,
  MINUS,
  STABILITY_CUTOFFS,
  STABILITY_LABELS,
  STALE_AFTER_SECONDS,
} from '../domain/eta';
import type { AlertContext, TrainPrediction } from '../domain/types';
import { usePredictionEnvironment } from '../data/PredictionClientContext';
import { useNow } from '../hooks/useNow';
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

const STEP_LABELS = ['BART says now', 'Expected change to BART’s ETA', 'Likely final published ETA'] as const;

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
      <div className="result" aria-hidden="true">
        {STEP_LABELS.map((label, i) => (
          <div key={label} className={`result__step${i === 2 ? ' result__step--final' : ''}`}>
            <span className="result__label">{label}</span>
            <span className="placeholder placeholder--value" />
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
  const { now: clock } = usePredictionEnvironment();
  const tick = useNow(clock);
  const { response, receivedAt } = received;
  const now = tick > receivedAt ? tick : receivedAt;
  const freshness = assessFreshness(response.feedTimestamp, now);

  const current = train.currentEtaSeconds;
  const revision = train.predictedRevisionSeconds;
  const final = likelyFinalEtaSeconds(current, revision);
  const finalAt = addSeconds(train.currentEtaAt, revision);
  const { lowerSeconds, upperSeconds, level } = train.revisionInterval;
  const coverage = `${Math.round(level * 100)}%`;
  const threshold = response.model.revisionThresholdSeconds;

  return (
    <div className={freshness.stale ? 'readout__body is-stale' : 'readout__body'}>
      <div className="readout__heading">
        <h3 id="readout-title" className="readout__title">
          {stationName} · {train.headsign} train
        </h3>
        <p className="readout__meta">
          {response.model.simulated && <span className="sim-tag">Simulated</span>}
          {train.lineName}
          {train.carCount !== null && ` · ${train.carCount} cars`} · {directionLabel} · Trip {train.tripId}
        </p>
      </div>

      {freshness.stale && (
        <p className="notice notice--stale" role="status">
          <strong>Stale data.</strong> This snapshot is from {formatClockMinute(response.feedTimestamp)},{' '}
          {formatSpokenDuration(freshness.ageSeconds)} ago, past the {formatSpokenDuration(STALE_AFTER_SECONDS)}{' '}
          freshness limit. Times away are counted from then, and BART may already have revised this estimate.
        </p>
      )}

      <div className="result">
        <div className="result__step" data-testid="step-now">
          <span className="result__label">
            {freshness.stale ? `BART said at ${formatClockMinute(response.feedTimestamp)}` : 'BART says now'}
          </span>
          <ClockTime iso={train.currentEtaAt} />
          <span className="result__away">{capitalize(describeTimeAway(current))}</span>
        </div>
        <div className="result__step" data-testid="step-change">
          <span className="result__label">Expected change to BART’s ETA</span>
          <span className="result__change">{capitalize(describeRevision(revision))}</span>
          <span className="result__detail">
            Likely range ({coverage}): {describeRevisionRange(lowerSeconds, upperSeconds)}
          </span>
        </div>
        <div className="result__step result__step--final" data-testid="step-final">
          <span className="result__label">Likely final published ETA</span>
          <ClockTime iso={finalAt} />
          <span className="result__away">{capitalize(describeAwayAbout(final))}</span>
          <span className="result__detail">
            Likely range ({coverage}): {formatSpokenDuration(likelyFinalEtaSeconds(current, lowerSeconds))} to{' '}
            {describeTimeAway(likelyFinalEtaSeconds(current, upperSeconds))}
          </span>
        </div>
      </div>

      <p className="readout__caveat">
        BART may revise this estimate. The likely final published ETA is the model’s forecast of the last ETA BART will
        publish before the train reaches {stationName}. It is not an observed arrival time.
      </p>

      <p className="result__arithmetic">
        <span className="result__arithmetic-label">How it adds up</span>{' '}
        <span className="nowrap">{formatSpokenDuration(current)}</span> current published ETA{' '}
        <span className="nowrap">
          {revision < 0 ? MINUS : '+'} {formatSpokenDuration(revision)}
        </span>{' '}
        predicted revision <span className="nowrap">= {formatSpokenDuration(final)}</span> likely final published ETA
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
  );
}

/**
 * "10:14:22" with a smaller "PM". Seconds are always shown in the primary clocks so a
 * sub-minute revision never makes two different estimates look identical.
 */
function ClockTime({ iso }: { iso: string }) {
  const text = formatClock(iso);
  const split = text.lastIndexOf(' ');
  return (
    <span className="result__clock">
      {text.slice(0, split)}
      <span className="result__meridiem">{text.slice(split)}</span>
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

/** Plain-language reading of the three values, announced to screen readers. */
export function describePrediction(train: TrainPrediction, stationName: string): string {
  const final = likelyFinalEtaSeconds(train.currentEtaSeconds, train.predictedRevisionSeconds);
  const finalAt = addSeconds(train.currentEtaAt, train.predictedRevisionSeconds);
  return (
    `${stationName}, ${train.headsign} train. ` +
    `BART says ${formatClock(train.currentEtaAt)}, ${describeTimeAway(train.currentEtaSeconds)}. ` +
    `Expected change: ${describeRevision(train.predictedRevisionSeconds)}. ` +
    `Likely final published ETA: ${formatClock(finalAt)}, ${describeAwayAbout(final)}.`
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
