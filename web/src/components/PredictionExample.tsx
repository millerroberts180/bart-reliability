import { useCallback, useEffect, useRef, useState } from 'react';
import { correctionNote, resolveBoardingGroup, sameId } from '../domain/boardingSelection';
import type { RetrospectiveRecord } from '../domain/showcase';
import { hasForecast, type ForecastTrain, type PredictionResponse, type Station } from '../domain/types';
import { usePredictionEnvironment } from '../data/PredictionClientContext';
import { clientKey } from '../data/clientKey';
import { useRecentStations } from '../hooks/useRecentStations';
import { useRequest } from '../hooks/useRequest';
import { readUrlSelection, useUrlNavigation, writeUrlSelection, type UrlSelection } from '../hooks/useUrlSelection';
import { EtaHistory, type HistorySubject } from './EtaHistory';
import { PredictionReadout, type ReadoutState } from './PredictionReadout';
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

/** A train to open when the address names none: the Highlights view's featured record. */
export interface FeaturedTrain {
  station: string;
  boarding: string;
  train: string;
}

/**
 * The train explorer. It lists only trains with a supported model forecast: the curated
 * replay contains no others, and in the development modes the rest are left out too, so no
 * train is ever shown with BART's ETA alone.
 */
export function PredictionExample({
  featured = null,
  retrospective = null,
}: {
  featured?: FeaturedTrain | null;
  retrospective?: Map<string, RetrospectiveRecord> | null;
}) {
  const { client, now } = usePredictionEnvironment();
  const { recentIds, remember } = useRecentStations();

  const loadStations = useCallback((signal: AbortSignal) => client.listStations(signal), [client]);
  const { state: stationsState, retry: retryStations } = useRequest<Station[]>(
    `stations:${clientKey(client)}`,
    loadStations,
  );
  const stations = stationsState.status === 'success' ? stationsState.data : [];

  // The URL seeds the choice; after that the page owns it and keeps the URL in step.
  const [requested, setRequested] = useState<Requested>(() => {
    const fromUrl = readUrlSelection();
    if (fromUrl.station === null && featured) {
      return { station: featured.station, boarding: featured.boarding, train: featured.train, legacyDirection: null, fromUrl: false };
    }
    return { ...fromUrl, fromUrl: true };
  });
  const [trainId, setTrainId] = useState<string | null>(() => requested.train);

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
  const choose = (next: Omit<Requested, 'train' | 'legacyDirection'>) => {
    setRequested({ ...next, train: null, legacyDirection: null });
    setTrainId(null);
  };

  // Notes explain only what the address asked for, and only once stations have loaded.
  const stationNote =
    requested.fromUrl && station && requested.station !== null && !requestedStation
      ? `Station “${requested.station}” isn’t in the list, so ${station.name} is shown instead.`
      : null;
  const groupNote =
    requested.fromUrl && station && group && resolution.correction
      ? correctionNote(resolution.correction, station, group)
      : null;

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

  const trains: ForecastTrain[] =
    predictionsState.status === 'success' ? predictionsState.data.response.trains.filter(hasForecast) : [];
  // The earliest train is chosen by default; a later one only when the visitor picks it.
  const train = trains.find((t) => t.predictionId === trainId) ?? trains[0];

  // Keep ?station=…&boarding=…&train=… in step with what is shown, correcting invalid values.
  const shown = useRef<{ station: string; boarding: string; train: string | null } | null>(null);
  const shownTrain = predictionsState.status === 'success' ? (train?.predictionId ?? null) : trainId;
  useEffect(() => {
    if (!station || !group) return;
    shown.current = { station: station.id, boarding: group.id, train: shownTrain };
    writeUrlSelection(shown.current);
  }, [station, group, shownTrain]);

  // Back and forward restore whatever the address then says, so the page and the URL
  // can never disagree. An address that matches what is shown changes nothing.
  useUrlNavigation((selection) => {
    const current = shown.current;
    if (
      current &&
      sameId(current.station, selection.station) &&
      sameId(current.boarding, selection.boarding) &&
      current.train === selection.train
    ) {
      return;
    }
    setRequested({ ...selection, fromUrl: true });
    setTrainId(selection.train);
  });

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
    readout = {
      kind: 'ready',
      received: predictionsState.data,
      train,
      retrospective: retrospective?.get(train.predictionId) ?? null,
    };
  }

  const history: HistorySubject =
    readout.kind === 'ready'
      ? { kind: 'ready', received: readout.received, train: readout.train }
      : readout.kind === 'loading'
        ? { kind: 'waiting' }
        : { kind: 'unavailable', reason: readout.kind };

  return (
    <section className="example" id="example" aria-labelledby="example-title">
      <h2 id="example-title" className="visually-hidden">
        Choose a train and read its forecast
      </h2>
      <div className="example__grid">
        <form className="controls" aria-label="Choose a train" onSubmit={(e) => e.preventDefault()}>
          <div className="field">
            <StationPicker
              stations={stations}
              selected={station}
              recentIds={recentIds}
              onSelect={(s) => {
                choose({ station: s.id, boarding: null, fromUrl: false });
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
                      choose({ station: station.id, boarding: g.id, fromUrl: false });
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

        <PredictionReadout state={readout} stationName={station?.name ?? ''} group={group} />
      </div>

      <EtaHistory subject={history} stationName={station?.name ?? ''} />
    </section>
  );
}
