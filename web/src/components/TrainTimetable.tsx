import { Fragment } from 'react';
import { formatDuration, STABILITY_LABELS } from '../domain/eta';
import type { TrainPrediction } from '../domain/types';
import { StabilityMark } from './StabilityMark';

interface TrainTimetableProps {
  state: 'loading' | 'error' | 'empty' | 'ready';
  trains: TrainPrediction[];
  selectedId: string | null;
  onSelect: (predictionId: string) => void;
}

const PLACEHOLDER_ROWS = 3;

/** Upcoming trains set like a printed timetable; each row is a radio choice. */
export function TrainTimetable({ state, trains, selectedId, onSelect }: TrainTimetableProps) {
  return (
    <fieldset className="field timetable" disabled={state !== 'ready'} aria-busy={state === 'loading'}>
      <legend className="field__label">Upcoming trains</legend>
      <div className="timetable__head" aria-hidden="true">
        <span>BART ETA</span>
        <span>Destination</span>
      </div>

      {state === 'ready' && (
        <div className="timetable__rows">
          {trains.map((t) => (
            <label key={t.predictionId} className="timetable__row">
              <input
                type="radio"
                name="train"
                value={t.predictionId}
                checked={t.predictionId === selectedId}
                onChange={() => onSelect(t.predictionId)}
              />
              <span className="timetable__eta">{formatDuration(t.currentEtaSeconds)}</span>
              <span className="timetable__dest">
                <span className="timetable__headsign">{withSlashBreaks(t.headsign)}</span>
                <span className="timetable__line">{t.lineName}</span>
                <span className={`timetable__stability tone-${t.stability}`}>
                  <StabilityMark stability={t.stability} />
                  {STABILITY_LABELS[t.stability]}
                </span>
              </span>
            </label>
          ))}
        </div>
      )}

      {state === 'loading' && (
        <div className="timetable__rows" aria-hidden="true">
          {Array.from({ length: PLACEHOLDER_ROWS }, (_, i) => (
            <div key={i} className="timetable__row timetable__row--placeholder">
              <span className="placeholder placeholder--short" />
              <span className="placeholder" />
            </div>
          ))}
        </div>
      )}

      {state === 'empty' && <p className="timetable__message">No trains listed in this snapshot.</p>}
      {state === 'error' && <p className="timetable__message">Train list unavailable.</p>}
    </fieldset>
  );
}

/** Allows a line break right after each "/" (e.g. "Dublin/<wbr>Pleasanton") without changing the text. */
export function withSlashBreaks(text: string) {
  return text.split('/').map((part, i, parts) => (
    <Fragment key={i}>
      {part}
      {i < parts.length - 1 && (
        <>
          /<wbr />
        </>
      )}
    </Fragment>
  ));
}
