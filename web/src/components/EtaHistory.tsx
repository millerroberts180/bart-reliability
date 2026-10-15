import { useCallback, useId, type ReactNode } from 'react';
import { addSeconds, formatClock, formatSpokenDuration } from '../domain/eta';
import { analyzeHistory, describeChart, summarizeHistory } from '../domain/history';
import { hasForecast, type TrainPrediction } from '../domain/types';
import { clientKey } from '../data/clientKey';
import { usePredictionEnvironment } from '../data/PredictionClientContext';
import { useFreshness } from '../hooks/useFreshness';
import { useRequest } from '../hooks/useRequest';
import { HistoryChart, type FinalReference } from './HistoryChart';
import { ObservationTable } from './ObservationTable';
import type { ReceivedPredictions } from './PredictionExample';

/** What the history section can show, mirroring the prediction readout. */
export type HistorySubject =
  | { kind: 'waiting' }
  | { kind: 'unavailable'; reason: 'error' | 'empty' }
  | { kind: 'ready'; received: ReceivedPredictions; train: TrainPrediction };

export function EtaHistory({ subject, stationName }: { subject: HistorySubject; stationName: string }) {
  return (
    <section className="history" aria-labelledby="history-title">
      <h3 id="history-title" className="history__title">
        How this ETA has changed
      </h3>
      {subject.kind === 'ready' ? (
        <ReadyHistory {...subject} stationName={stationName} />
      ) : (
        <HistoryMessage
          text={
            subject.kind === 'waiting'
              ? 'Loading history…'
              : subject.reason === 'error'
                ? 'No history to show, because the prediction request failed.'
                : 'No train is selected, so there is no history to show.'
          }
          busy={subject.kind === 'waiting'}
        />
      )}
    </section>
  );
}

function HistoryMessage({ text, busy = false, children }: { text: string; busy?: boolean; children?: ReactNode }) {
  return (
    <div className="history__body" aria-busy={busy}>
      <p className="history__summary">{text}</p>
      <div className="history__frame">{children}</div>
    </div>
  );
}

function ReadyHistory({
  received,
  train,
  stationName,
}: {
  received: ReceivedPredictions;
  train: TrainPrediction;
  stationName: string;
}) {
  const { client } = usePredictionEnvironment();
  const figureNameId = useId();
  const { response, receivedAt } = received;
  const freshness = useFreshness(response.feedTimestamp, receivedAt, response.replay);

  const load = useCallback(
    (signal: AbortSignal) => client.getPredictionHistory(train.predictionId, signal),
    [client, train.predictionId],
  );
  const { state, retry } = useRequest(
    `${clientKey(client)}:${train.predictionId}:${response.feedTimestamp}`,
    load,
  );

  const subjectLine = `${stationName} · ${train.headsign} train`;

  if (state.status === 'loading') return <HistoryMessage text="Loading history…" busy />;
  if (state.status === 'error') {
    return (
      <HistoryMessage text="The history request failed, so the chart can’t be drawn. The prediction above is unaffected.">
        <button type="button" className="button" onClick={retry}>
          Try again
        </button>
      </HistoryMessage>
    );
  }

  const analysis = analyzeHistory(state.data, response.feedTimestamp);
  const summary = summarizeHistory(analysis, { stale: freshness.stale });
  // Only a train with a model forecast gets the dashed reference, and only a supported
  // range gets the bracket; nothing is drawn in their place otherwise.
  const final: FinalReference | null = hasForecast(train)
    ? {
        at: addSeconds(train.currentEtaAt, train.predictedRevisionSeconds),
        range: train.revisionInterval && {
          lowerAt: addSeconds(train.currentEtaAt, train.revisionInterval.lowerSeconds),
          upperAt: addSeconds(train.currentEtaAt, train.revisionInterval.upperSeconds),
          coverage: `${Math.round(train.revisionInterval.level * 100)}%`,
        },
      }
    : null;

  return (
    <div className="history__body">
      <p className="history__subject">
        {subjectLine} · BART’s published arrival time at each feed snapshot
      </p>
      <p className="history__summary" data-testid="history-summary">
        {summary}
      </p>
      {freshness.stale && (
        <p className="history__note">
          These snapshots end at {formatClock(response.feedTimestamp)}, {formatSpokenDuration(freshness.ageSeconds)}{' '}
          {response.replay ? 'before the replay time' : 'ago'}. BART may have changed this ETA since.
        </p>
      )}

      {analysis.observations.length === 0 ? (
        <div className="history__frame" />
      ) : (
        <figure className="history__figure" aria-labelledby={figureNameId}>
          <span id={figureNameId} className="visually-hidden">
            {describeChart(analysis, subjectLine)}
          </span>
          <HistoryChart analysis={analysis} final={final} label={`How BART’s ETA changed: ${subjectLine}`} />
          {/* A key, not a caption: these entries define marks and say nothing about this train's data. */}
          <ul className="history__legend" aria-label="Chart key">
            <li className="legend__item">
              <span className="legend__swatch legend__swatch--bart" aria-hidden="true" />
              <span>
                <span className="visually-hidden">Solid line: </span>BART’s published ETA. Up means BART moved it
                later, down earlier, flat means it held.
              </span>
            </li>
            {final ? (
              <li className="legend__item">
                <span className="legend__swatch legend__swatch--final" aria-hidden="true" />
                <span>
                  <span className="visually-hidden">Dashed line: </span>Model’s likely final published ETA (
                  {formatClock(final.at)})
                  {final.range ? `, with its ${final.range.coverage} range at the right` : '; no likely range is available'}.
                  A forecast, not an observation.
                </span>
              </li>
            ) : (
              <li className="legend__item legend__item--note">
                No model forecast for this train, so the chart shows BART’s published ETA only.
              </li>
            )}
            {analysis.gapCount > 0 && (
              <li className="legend__item">
                <span className="legend__swatch legend__swatch--gap" aria-hidden="true" />
                <span>
                  <span className="visually-hidden">Shaded band: </span>A span with no snapshots in the feed.
                </span>
              </li>
            )}
          </ul>
        </figure>
      )}

      {analysis.observations.length > 0 && <ObservationTable analysis={analysis} />}
    </div>
  );
}
