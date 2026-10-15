import { useCallback, useId, useState } from 'react';
import { formatMoment } from '../domain/eta';
import type { PredictionResponse, Station } from '../domain/types';
import { usePredictionEnvironment } from '../data/PredictionClientContext';
import { clientKey } from '../data/clientKey';
import { useRequest } from '../hooks/useRequest';
import { EXAMPLE_HEADING_ID } from './ExampleLink';
import { EtaHistory, type HistorySubject } from './EtaHistory';
import { PredictionReadout, type ReadoutState } from './PredictionReadout';
import { TrainTimetable } from './TrainTimetable';

export interface ReceivedPredictions {
  response: PredictionResponse;
  /** Clock reading when the response arrived, for freshness. */
  receivedAt: Date;
}

export function PredictionExample() {
  const { client, now } = usePredictionEnvironment();
  const stationSelectId = useId();

  const loadStations = useCallback((signal: AbortSignal) => client.listStations(signal), [client]);
  const { state: stationsState, retry: retryStations } = useRequest<Station[]>(
    `stations:${clientKey(client)}`,
    loadStations,
  );
  const stations = stationsState.status === 'success' ? stationsState.data : [];

  const [stationId, setStationId] = useState<string | null>(null);
  const [directionId, setDirectionId] = useState<string | null>(null);
  const [trainId, setTrainId] = useState<string | null>(null);

  // Fall back to the first available option whenever a choice is unset or no longer exists.
  const station = stations.find((s) => s.id === stationId) ?? stations[0];
  const direction = station?.directions.find((d) => d.id === directionId) ?? station?.directions[0];

  const predictionsKey = station && direction ? `${clientKey(client)}:${station.id}:${direction.id}` : null;
  const loadPredictions = useCallback(
    async (signal: AbortSignal): Promise<ReceivedPredictions> => {
      if (!station || !direction) throw new Error('No station selected.');
      const response = await client.getPredictions(station.id, direction.id, signal);
      return { response, receivedAt: now() };
    },
    [client, now, station, direction],
  );
  const { state: predictionsState, retry: retryPredictions } = useRequest(predictionsKey, loadPredictions);

  const trains = predictionsState.status === 'success' ? predictionsState.data.response.trains : [];
  const replayAsOf = predictionsState.status === 'success' ? (predictionsState.data.response.replay?.asOf ?? null) : null;
  const train = trains.find((t) => t.predictionId === trainId) ?? trains[0];

  let readout: ReadoutState;
  if (stationsState.status === 'error') {
    readout = { kind: 'error', retry: retryStations };
  } else if (!station || !direction || predictionsState.status === 'loading') {
    readout = { kind: 'loading' };
  } else if (predictionsState.status === 'error') {
    readout = { kind: 'error', retry: retryPredictions };
  } else if (!train) {
    readout = {
      kind: 'empty',
      unplacedTrainCount: predictionsState.data.response.unplacedTrainCount,
      endsHere: direction.destinations.some((d) => sameName(d, station.name)),
    };
  } else {
    readout = { kind: 'ready', received: predictionsState.data, train };
  }

  const history: HistorySubject =
    readout.kind === 'ready'
      ? { kind: 'ready', received: readout.received, train: readout.train }
      : readout.kind === 'loading'
        ? { kind: 'waiting' }
        : { kind: 'unavailable', reason: readout.kind };

  return (
    <section className="example" id="example" aria-labelledby={EXAMPLE_HEADING_ID}>
      <div className="example__intro">
        <h2 id={EXAMPLE_HEADING_ID} className="example__title" tabIndex={-1}>
          Try an ETA forecast
        </h2>
        <p>
          Choose a station, a direction and an upcoming train. The result shows what BART says now, how much the model
          expects BART to change that estimate, and the likely final published ETA. {sourceSentence(client.source, replayAsOf)}
        </p>
      </div>

      <div className="example__grid">
        <form className="controls" aria-label="Choose a train" onSubmit={(e) => e.preventDefault()}>
          <div className="field">
            <label className="field__label" htmlFor={stationSelectId}>
              Station
            </label>
            <select
              id={stationSelectId}
              className="select"
              value={station?.id ?? ''}
              disabled={stations.length === 0}
              onChange={(e) => {
                setStationId(e.target.value);
                setDirectionId(null);
                setTrainId(null);
              }}
            >
              {stations.length === 0 && <option value="">Loading stations…</option>}
              {stations.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <fieldset className="field" disabled={!station}>
            <legend className="field__label">Direction</legend>
            <div className="choice-list">
              {(station?.directions ?? []).map((d) => (
                <label key={d.id} className="choice">
                  <input
                    type="radio"
                    name="direction"
                    value={d.id}
                    checked={d.id === direction?.id}
                    onChange={() => {
                      setDirectionId(d.id);
                      setTrainId(null);
                    }}
                  />
                  <span>{d.label}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <TrainTimetable
            state={predictionsState.status === 'success' ? (trains.length ? 'ready' : 'empty') : predictionsState.status}
            trains={trains}
            selectedId={train?.predictionId ?? null}
            onSelect={setTrainId}
          />
        </form>

        <PredictionReadout state={readout} stationName={station?.name ?? ''} directionLabel={direction?.label ?? ''} />
      </div>

      <EtaHistory subject={history} stationName={station?.name ?? ''} />
    </section>
  );
}

/** Station names and destinations differ in spacing ("Dublin / Pleasanton", "Dublin/Pleasanton"). */
function sameName(a: string, b: string): boolean {
  const key = (s: string) => s.replace(/\s+/g, '').toLowerCase();
  return key(a) === key(b);
}

/** Says where the values come from; replay data is named as such and never as live. */
function sourceSentence(source: 'simulated' | 'api', replayAsOf: string | null): string {
  if (source === 'simulated') return 'All values are simulated.';
  if (replayAsOf) return `Values are a historical replay of recorded BART data as of ${formatMoment(replayAsOf)}, not live.`;
  return 'Values come from the prediction API and are labelled with how they were produced.';
}
