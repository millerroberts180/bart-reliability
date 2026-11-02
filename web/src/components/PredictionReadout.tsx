import type { CSSProperties } from 'react';
import {
  addSeconds,
  describeAwayGlance,
  describeRevision,
  describeRevisionRange,
  describeTimeAway,
  formatClock,
  formatClockMinute,
  formatClockSince,
  formatDuration,
  formatLongMoment,
  formatMoment,
  formatPercent,
  formatSpokenDuration,
  likelyFinalEtaSeconds,
  needsSeconds,
  STABILITY_CUTOFFS,
  STABILITY_LABELS,
  STALE_AFTER_SECONDS,
} from '../domain/eta';
import {
  describeDirectionMatch,
  describeExpected,
  describeModelError,
  describeMoved,
  RETROSPECTIVE_NOTE,
} from '../domain/revisionText';
import { routeColor } from '../domain/routeColors';
import type { RetrospectiveRecord } from '../domain/showcase';
import type { AlertContext, BoardingGroup, ForecastTrain, PredictionResponse } from '../domain/types';
import { useFreshness } from '../hooks/useFreshness';
import type { ReceivedPredictions } from './PredictionExample';
import { StabilityMark } from './StabilityMark';

/** The readout's heading. */
export const READOUT_TITLE_ID = 'readout-title';

export type ReadoutState =
  | { kind: 'loading' }
  | { kind: 'error'; retry: () => void }
  | {
      kind: 'empty';
      /** Trains listed at the station whose way out is unknown (see PredictionResponse). */
      unplacedTrainCount: number;
      /** Trains listed at the station whose trips end here. */
      terminatingTrainCount: number;
    }
  | {
      kind: 'ready';
      received: ReceivedPredictions;
      /** The explorer lists only trains with a supported model forecast. */
      train: ForecastTrain;
      /** What BART later published for this train, when the curated showcase has it. */
      retrospective: RetrospectiveRecord | null;
    };

interface PredictionReadoutProps {
  state: ReadoutState;
  stationName: string;
  group: BoardingGroup | undefined;
}

export function PredictionReadout({ state, stationName, group }: PredictionReadoutProps) {
  const announcement = {
    loading: 'Loading prediction.',
    error: 'Prediction unavailable.',
    empty: 'No model-eligible trains.',
    ready: state.kind === 'ready' ? describePrediction(state.train, stationName, saidLabel(state.received.response)) : '',
  }[state.kind];

  return (
    <section
      className={`readout readout--${state.kind}`}
      aria-labelledby={READOUT_TITLE_ID}
      aria-busy={state.kind === 'loading'}
    >
      <p className="visually-hidden" aria-live="polite">
        {announcement}
      </p>
      {state.kind === 'loading' && <LoadingReadout />}
      {state.kind === 'error' && (
        <div className="readout__message">
          <h3 id={READOUT_TITLE_ID}>Prediction unavailable</h3>
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
          <h3 id={READOUT_TITLE_ID}>No model-eligible trains</h3>
          <p>
            The latest snapshot lists no train {group ? lowerFirst(group.label) : ''} from {stationName} in the
            model’s 5-, 10- and 15-minute forecast windows.{' '}
            {emptyReason(state.unplacedTrainCount, state.terminatingTrainCount, stationName)}
          </p>
        </div>
      )}
      {state.kind === 'ready' && (
        <ReadyReadout {...state} stationName={stationName} group={group} />
      )}
    </section>
  );
}

/**
 * Why a board can be empty, said only from what the response shows. Trains that match
 * no scheduled trip cannot be placed on either side of the station, and a train whose
 * trip ends here cannot be boarded (docs/boarding_groups.md).
 */
function emptyReason(unplaced: number, terminating: number, stationName: string): string {
  const reasons: string[] = [];
  if (terminating > 0) {
    reasons.push(
      terminating === 1
        ? `BART’s feed lists 1 train at ${stationName} that ends its trip here, so it can’t be boarded and isn’t shown.`
        : `BART’s feed lists ${terminating} trains at ${stationName} that end their trips here, so they can’t be boarded and aren’t shown.`,
    );
  }
  if (unplaced > 0) {
    reasons.push(
      unplaced === 1
        ? `BART’s feed does list 1 train at ${stationName} that matches no scheduled trip, so which way it’s going isn’t known and it isn’t shown.`
        : `BART’s feed does list ${unplaced} trains at ${stationName} that match no scheduled trip, so which way they’re going isn’t known and they aren’t shown.`,
    );
  }
  if (reasons.length === 0) {
    reasons.push(
      'No train may be 5, 10 or 15 minutes away at the snapshot time, service may have ended for the night, or BART’s feed may not include the trains.',
    );
  }
  return reasons.join(' ');
}

/** How the row giving BART's own ETA is introduced; a replay is never described in the present tense. */
function saidLabel(response: PredictionResponse, stale = false): string {
  if (stale) return `BART said at ${formatClockMinute(response.feedTimestamp)}`;
  return response.replay ? 'BART said in this snapshot' : 'BART currently says';
}

function LoadingReadout() {
  // Mirrors the ready layout so nothing jumps when the prediction arrives.
  return (
    <>
      <div className="readout__heading">
        <h3 id={READOUT_TITLE_ID} className="readout__title">
          Loading prediction…
        </h3>
        <span className="readout__meta placeholder placeholder--short" />
      </div>
      <div className="forecast" aria-hidden="true">
        <p className="forecast__label">BART published ETA at the replay moment</p>
        <span className="placeholder placeholder--clock" />
        <span className="placeholder placeholder--short" />
      </div>
      <div className="summary" aria-hidden="true">
        {['Model’s expected ETA revision', 'Model-adjusted ETA', 'Uncertainty'].map((label) => (
          <div key={label} className="summary__row">
            <span className="summary__label">{label}</span>
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
  retrospective,
  stationName,
  group,
}: {
  received: ReceivedPredictions;
  train: ForecastTrain;
  retrospective: RetrospectiveRecord | null;
  stationName: string;
  group: BoardingGroup | undefined;
}) {
  const { response, receivedAt } = received;
  const { replay } = response;
  const freshness = useFreshness(response.feedTimestamp, receivedAt, replay);
  const said = saidLabel(response, freshness.stale);
  const platform = train.platform ?? group?.platform ?? null;

  return (
    <div className={freshness.stale ? 'readout__body is-stale' : 'readout__body'}>
      {/* Train identity, the forecast and its summary share one route rail. */}
      <div className="result-block" style={{ '--route': routeColor(train.lineName) } as CSSProperties}>
        <div className="readout__heading">
          <h3 id={READOUT_TITLE_ID} className="readout__title" tabIndex={-1}>
            {stationName} · {train.headsign} train
          </h3>
          <p className="readout__meta">
            <span className="route-tag">
              <span className="route-tag__swatch" aria-hidden="true" />
              {train.lineName}
            </span>
            {platform && <span className="readout__meta-item">Platform {platform}</span>}
            {group && <span className="readout__meta-item">{group.label}</span>}
            {train.carCount !== null && <span className="readout__meta-item">{train.carCount} cars</span>}
            {response.model.simulated && <span className="sim-tag">Simulated</span>}
          </p>
        </div>

        {replay && (
          <p className="notice notice--replay" data-testid="replay-notice">
            <strong>Historical replay—fixed, not live.</strong> BART data as of {formatLongMoment(replay.asOf)}{' '}
            Pacific.
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

        <ForecastResult
          train={train}
          threshold={response.model.revisionThresholdSeconds}
          retrospective={retrospective}
          moment={replay ? 'at the replay moment' : 'in this snapshot'}
        />
      </div>

      <div className="details">
        <Calculation
          train={train}
          said={said}
          threshold={response.model.revisionThresholdSeconds}
          stationName={stationName}
        />

        <dl className="facts facts--alerts">
          <div className="facts__row">
            <dt>Service alerts</dt>
            <dd>
              <AlertList alerts={response.alerts} feedTimestamp={response.feedTimestamp} />
            </dd>
          </div>
        </dl>

        <details className="more" data-testid="data-details">
          <summary>Data and model details</summary>
          <dl className="facts">
            <div className="facts__row">
              <dt>Data</dt>
              <dd>
                {replay
                  ? `Historical replay of recorded BART data as of ${formatLongMoment(replay.asOf)} Pacific. The data is fixed at that moment, and the forecast uses only what was known then. Nothing here is live.`
                  : 'Simulated. Every station reading, train and number is invented.'}
              </dd>
            </div>
            <div className="facts__row">
              <dt>Feed snapshot</dt>
              <dd>
                <span className={`freshness ${freshness.stale ? 'freshness--stale' : 'freshness--current'}`}>
                  {freshness.stale ? 'Stale' : replay ? 'Fresh at replay time' : 'Current'}
                </span>{' '}
                {formatClock(response.feedTimestamp)} · {formatDuration(freshness.ageSeconds)} old
                {replay ? ' at the replay time' : ''}. Times away are counted from this snapshot.
              </dd>
            </div>
            <div className="facts__row">
              <dt>Forecast generated</dt>
              <dd>
                {formatClock(response.generatedAt)}
                {replay ? ' (the replay time)' : ''}
              </dd>
            </div>
            <div className="facts__row">
              <dt>Model</dt>
              <dd>
                Version {response.model.modelVersion}, trained on data through{' '}
                {formatMoment(response.model.trainedThrough)} Pacific
              </dd>
            </div>
            <div className="facts__row">
              <dt>Trip</dt>
              <dd>{train.tripId}</dd>
            </div>
          </dl>
        </details>
      </div>
    </div>
  );
}

/**
 * The forecast in reading order: BART's published ETA at the replay moment, the model's
 * expected revision, the model-adjusted ETA, its uncertainty, and then, set apart as
 * retrospective, what BART later published.
 */
function ForecastResult({
  train,
  threshold,
  retrospective,
  moment,
}: {
  train: ForecastTrain;
  threshold: number;
  retrospective: RetrospectiveRecord | null;
  moment: string;
}) {
  const current = train.currentEtaSeconds;
  const revision = train.predictedRevisionSeconds;
  const adjusted = likelyFinalEtaSeconds(current, revision);
  const adjustedAt = addSeconds(train.currentEtaAt, revision);
  const interval = train.revisionInterval;
  // Clock times show seconds when a minute alone would make two of them look the same.
  const seconds =
    needsSeconds(train.currentEtaAt, adjustedAt) ||
    (retrospective !== null && needsSeconds(adjustedAt, retrospective.finalPublishedEtaAt));

  return (
    <>
      <div className="forecast" data-testid="forecast">
        <p className="forecast__label">BART published ETA {moment}</p>
        <p className="forecast__clock">
          <ClockTime iso={train.currentEtaAt} />
        </p>
        <p className="forecast__away">{describeAwayGlance(current)}</p>
      </div>

      <ol className="readout-steps" aria-label="The model’s forecast">
        <li className="readout-step" data-testid="step-revision">
          <p className="readout-step__label">Model’s expected ETA revision</p>
          <p className="readout-step__value">{describeExpected(revision)}</p>
        </li>
        <li className="readout-step" data-testid="step-adjusted">
          <p className="readout-step__label">Model-adjusted ETA</p>
          <p className="readout-step__value">
            <span className="nowrap">{formatClockFor(adjustedAt, seconds)}</span>{' '}
            <span>· {lowerFirst(describeAwayGlance(adjusted))}</span>
          </p>
          <p className="readout-step__note">BART’s ETA plus the expected revision. It is not an observed arrival time.</p>
        </li>
        <li className={`readout-step tone-${train.stability}`} data-testid="step-uncertainty">
          <p className="readout-step__label">Uncertainty</p>
          <p className="readout-step__value">
            <span className="summary__stability">
              <StabilityMark stability={train.stability} />
              {STABILITY_LABELS[train.stability]}
            </span>{' '}
            <span className="summary__percent">
              <span aria-hidden="true">· </span>
              <span className="stability__percent">{formatPercent(train.revisionProbability)}</span> chance BART changes
              this ETA by more than {threshold} seconds
            </span>
          </p>
          {interval && (
            <p className="readout-step__note">
              {coverageOf(interval.level)} likely range of the revision:{' '}
              {describeRevisionRange(interval.lowerSeconds, interval.upperSeconds)}
            </p>
          )}
        </li>
        {retrospective && (
          <li className="readout-step readout-step--retrospective" data-testid="step-final">
            <p className="readout-step__label">
              BART later published <span className="retro-tag">Retrospective</span>
            </p>
            <p className="readout-step__value">
              <span className="nowrap">
                {formatClockFor(retrospective.finalPublishedEtaAt, seconds)}
              </span>{' '}
              <span>· {describeMoved(retrospective.realizedRevisionSeconds)}</span>
            </p>
            <p className="readout-step__note">
              {RETROSPECTIVE_NOTE} {describeDirectionMatch(retrospective.directionMatch)}.{' '}
              {describeModelError(retrospective.modelErrorSeconds)}
            </p>
          </li>
        )}
      </ol>
    </>
  );
}

/** The exact arithmetic behind the forecast, and how stability is classified. */
function Calculation({
  train,
  said,
  threshold,
  stationName,
}: {
  train: ForecastTrain;
  said: string;
  threshold: number;
  stationName: string;
}) {
  const current = train.currentEtaSeconds;
  const revision = train.predictedRevisionSeconds;
  const final = likelyFinalEtaSeconds(current, revision);
  const finalAt = addSeconds(train.currentEtaAt, revision);
  const interval = train.revisionInterval;
  // The calculation's two clocks add seconds only when the minute alone would hide the adjustment.
  const seconds = needsSeconds(train.currentEtaAt, finalAt);

  return (
    <details className="more" data-testid="calculation">
      <summary>How the forecast is calculated</summary>
      <dl className="calc" aria-label="Exact calculation">
        <div className="calc__row" data-testid="calc-now">
          <dt>{said}</dt>
          <dd>
            <span className="nowrap">{formatClockFor(train.currentEtaAt, seconds)}</span>{' '}
            <span>· {describeTimeAway(current)}</span>
          </dd>
        </div>
        <div className="calc__row" data-testid="calc-adjust">
          <dt>
            <span className="calc__op" aria-hidden="true">
              +
            </span>
            Expected ETA revision
          </dt>
          <dd>{capitalize(describeRevision(revision))}</dd>
        </div>
        <div className="calc__row calc__row--total" data-testid="calc-final">
          <dt>
            <span className="calc__op" aria-hidden="true">
              =
            </span>
            Model-adjusted ETA
          </dt>
          <dd>
            <span className="nowrap">{formatClockFor(finalAt, seconds)}</span>{' '}
            <span>· {describeAwayAbout(final)}</span>
          </dd>
        </div>
      </dl>

      <p className="details__item">
        <span className="details__label">Adjustment range{interval ? ` (${coverageOf(interval.level)})` : ''}</span>{' '}
        {interval
          ? capitalize(describeRevisionRange(interval.lowerSeconds, interval.upperSeconds))
          : 'Not available for this forecast.'}
      </p>

      <div className={`stability tone-${train.stability}`}>
        <p className="stability__detail">
          <span className="stability__percent">{formatPercent(train.revisionProbability)}</span> chance BART changes
          this estimate by more than {threshold} seconds, earlier or later. Under 25%: likely to hold. 25% to 50%: may
          be revised. 50% or more: likely to be revised.
        </p>
        <ProbabilityScale probability={train.revisionProbability} />
      </div>

      <p className="readout__caveat">
        BART may revise this estimate. The model-adjusted ETA is BART’s ETA plus the revision the model expects
        before the train reaches {stationName}. It is not an observed arrival time.
      </p>
    </details>
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
 * the exact ones. `said` introduces BART's own ETA ("BART said in this snapshot").
 */
export function describePrediction(train: ForecastTrain, stationName: string, said: string): string {
  const adjusted = likelyFinalEtaSeconds(train.currentEtaSeconds, train.predictedRevisionSeconds);
  const adjustedAt = addSeconds(train.currentEtaAt, train.predictedRevisionSeconds);
  const seconds = needsSeconds(train.currentEtaAt, adjustedAt);
  return (
    `${stationName}, ${train.headsign} train. ` +
    `${said}: ${formatClockFor(train.currentEtaAt, seconds)}, ${describeTimeAway(train.currentEtaSeconds)}. ` +
    `${describeExpected(train.predictedRevisionSeconds)}. ` +
    `Model-adjusted ETA: ${formatClockFor(adjustedAt, seconds)}, ${describeAwayAbout(adjusted)}.`
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
