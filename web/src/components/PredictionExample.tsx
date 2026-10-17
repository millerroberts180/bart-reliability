import { useCallback, useEffect, useRef, useState } from 'react';
import { correctionNote, resolveBoardingGroup, sameId } from '../domain/boardingSelection';
import { hasForecast, type PredictionResponse, type Station, type TrainPrediction } from '../domain/types';
import { usePredictionEnvironment } from '../data/PredictionClientContext';
import { clientKey } from '../data/clientKey';
import { useRecentStations } from '../hooks/useRecentStations';
import { useRequest } from '../hooks/useRequest';
import { readUrlSelection, useUrlNavigation, writeUrlSelection, type UrlSelection } from '../hooks/useUrlSelection';
import { EXAMPLE_HEADING_ID } from './ExampleLink';
import { EtaHistory, type HistorySubject } from './EtaHistory';
import { PredictionReadout, READOUT_TITLE_ID, type NextForecast, type ReadoutState } from './PredictionReadout';
import { StationPicker } from './StationPicker';
import { TrainTimetable } from './TrainTimetable';

export interface ReceivedPredictions {
  response: PredictionResponse;
  /** Clock reading when the response arrived, for freshness. */
  receivedAt: Date;
}

/** What the page has been asked to show; `fromUrl` while it still comes from the address. */
interface Requested extends UrlSelection {
  fromUrl: boolean;
}

export function PredictionExample() {
  const { client, now } = usePredictionEnvironment();
  const { recentIds, remember } = useRecentStations();

  const loadStations = useCallback((signal: AbortSignal) => client.listStations(signal), [client]);
  const { state: stationsState, retry: retryStations } = useRequest<Station[]>(
    `stations:${clientKey(client)}`,
    loadStations,
  );
  const stations = stationsState.status === 'success' ? stationsState.data : [];

  // The URL seeds the choice; after that the page owns it and keeps the URL in step.
  const [requested, setRequested] = useState<Requested>(() => ({ ...readUrlSelection(), fromUrl: true }));
  const [trainId, setTrainId] = useState<string | null>(null);

  // Fall back safely whenever a choice is unset, unknown or no longer exists: to the
  // first station the active client lists (the API's order in HTTP mode).
  const requestedStation = stations.find((s) => sameId(s.id, requested.station));
  const station = requestedStation ?? stations[0];
  // A boarding group asked for at an unknown station does not apply to its stand-in.
  const appliesHere = Boolean(requestedStation) || requested.station === null;
  const resolution = station
    ? resolveBoardingGroup(station, appliesHere ? requested : { boarding: null, legacyDirection: null })
    : { group: undefined, correction: null };
  const group = resolution.group;

  // Notes explain only what the address asked for, and only once stations have loaded.
  const stationNote =
    requested.fromUrl && station && requested.station !== null && !requestedStation
      ? `Station “${requested.station}” isn’t in the list, so ${station.name} is shown instead.`
      : null;
  const groupNote =
    requested.fromUrl && station && group && resolution.correction
      ? correctionNote(resolution.correction, station, group)
      : null;

  // Keep ?station=…&boarding=… in step with what is shown, correcting invalid values.
  const shown = useRef<{ station: string; boarding: string } | null>(null);
  useEffect(() => {
    if (!station || !group) return;
    shown.current = { station: station.id, boarding: group.id };
    writeUrlSelection(shown.current);
  }, [station, group]);

  // Back and forward restore whatever the address then says, so the page and the URL
  // can never disagree. An address that matches what is shown changes nothing.
  useUrlNavigation((selection) => {
    const current = shown.current;
    if (current && sameId(current.station, selection.station) && sameId(current.boarding, selection.boarding)) return;
    setRequested({ ...selection, fromUrl: true });
    setTrainId(null);
  });

  const predictionsKey = station && group ? `${clientKey(client)}:${station.id}:${group.id}` : null;
  const loadPredictions = useCallback(
    async (signal: AbortSignal): Promise<ReceivedPredictions> => {
      if (!station || !group) throw new Error('No station selected.');
      const response = await client.getPredictions(station.id, group.id, signal);
      return { response, receivedAt: now() };
    },
    [client, now, station, group],
  );
  const { state: predictionsState, retry: retryPredictions } = useRequest(predictionsKey, loadPredictions);

  const trains = predictionsState.status === 'success' ? predictionsState.data.response.trains : [];
  // The earliest train is chosen by default; a later one only when the visitor picks it.
  const train = trains.find((t) => t.predictionId === trainId) ?? trains[0];

  const viewForecast = (target: TrainPrediction) => {
    setTrainId(target.predictionId);
    // The button that was pressed goes away, so focus moves to the result it opened.
    requestAnimationFrame(() => document.getElementById(READOUT_TITLE_ID)?.focus());
  };

  let readout: ReadoutState;
  if (stationsState.status === 'error') {
    readout = { kind: 'error', retry: retryStations };
  } else if (!station || !group || predictionsState.status === 'loading') {
    readout = { kind: 'loading' };
  } else if (predictionsState.status === 'error') {
    readout = { kind: 'error', retry: retryPredictions };
  } else if (!train) {
    const { unplacedTrainCount, terminatingTrainCount } = predictionsState.data.response;
    readout = { kind: 'empty', unplacedTrainCount, terminatingTrainCount };
  } else {
    readout = { kind: 'ready', received: predictionsState.data, train, nextForecast: nextForecastFor(train, trains) };
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
        <p>Choose where you’re boarding, which way you’re going and a train.</p>
      </div>

      <div className="example__grid">
        <form className="controls" aria-label="Choose a train" onSubmit={(e) => e.preventDefault()}>
          <div className="field">
            <StationPicker
              stations={stations}
              selected={station}
              recentIds={recentIds}
              onSelect={(s) => {
                setRequested({ station: s.id, boarding: null, legacyDirection: null, fromUrl: false });
                setTrainId(null);
                remember(s.id);
              }}
            />
            {stationNote && (
              <p className="field__note" role="status">
                {stationNote}
              </p>
            )}
          </div>

          <fieldset className="field" disabled={!station}>
            <legend className="field__label">Which way are you going?</legend>
            <div className="choice-list choice-list--compact">
              {(station?.boardingGroups ?? []).map((g) => (
                <label key={g.id} className="choice">
                  <input
                    type="radio"
                    name="boarding"
                    value={g.id}
                    checked={g.id === group?.id}
                    onChange={() => {
                      if (!station) return;
                      setRequested({ station: station.id, boarding: g.id, legacyDirection: null, fromUrl: false });
                      setTrainId(null);
                    }}
                  />
                  <span className="choice__label">{g.label}</span>
                  {g.platform && (
                    <span className="choice__platform">
                      <span className="visually-hidden">,</span> Platform {g.platform}
                    </span>
                  )}
                </label>
              ))}
            </div>
            {station?.endOfLine && (
              <p className="field__note">
                {station.name} is the end of the line. Trains arriving here end their trips, so only trains leaving are
                listed.
              </p>
            )}
            {groupNote && (
              <p className="field__note" role="status">
                {groupNote}
              </p>
            )}
          </fieldset>

          <TrainTimetable
            key={`${station?.id ?? ''}:${group?.id ?? ''}`}
            state={predictionsState.status === 'success' ? (trains.length ? 'ready' : 'empty') : predictionsState.status}
            trains={trains}
            selectedId={train?.predictionId ?? null}
            groupPlatform={group?.platform ?? null}
            onSelect={setTrainId}
          />
        </form>

        <PredictionReadout state={readout} stationName={station?.name ?? ''} group={group} onViewForecast={viewForecast} />
      </div>

      <EtaHistory subject={history} stationName={station?.name ?? ''} />
    </section>
  );
}

/**
 * For a train without a model forecast, the next train after it that has one (or,
 * failing that, the earliest one that has). It is offered as an explicit choice, never
 * selected for the visitor.
 */
function nextForecastFor(train: TrainPrediction, trains: TrainPrediction[]): NextForecast | null {
  if (hasForecast(train)) return null;
  const later = trains.slice(trains.indexOf(train) + 1).find(hasForecast);
  if (later) return { train: later, later: true };
  const earlier = trains.find(hasForecast);
  return earlier ? { train: earlier, later: false } : null;
}
