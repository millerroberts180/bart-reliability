import { Fragment, useId, useState } from 'react';
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

/** Trains listed before "Show more"; the rest stay one press away. */
export const INITIAL_TRAIN_LIMIT = 4;

/**
 * Upcoming trains set like a printed timetable; each row is a radio choice. Only the
 * next four are listed at first, in time order. Collapsing never hides the selected
 * train: if it is later in the list, it stays listed after the first four.
 */
export function TrainTimetable({ state, trains, selectedId, onSelect }: TrainTimetableProps) {
  const rowsId = useId();
  const [expanded, setExpanded] = useState(false);
  const selectedIndex = trains.findIndex((t) => t.predictionId === selectedId);
  const visible = expanded ? trains : trains.filter((_, i) => i < INITIAL_TRAIN_LIMIT || i === selectedIndex);
  const hidden = trains.length - visible.length;
  const skipsToSelected = !expanded && selectedIndex >= INITIAL_TRAIN_LIMIT;

  return (
    <fieldset className="field timetable" disabled={state !== 'ready'} aria-busy={state === 'loading'}>
      <legend className="field__label">Upcoming trains</legend>
      <div className="timetable__head" aria-hidden="true">
        <span>BART ETA</span>
        <span>Destination</span>
      </div>

      {state === 'ready' && (
        <div className="timetable__rows" id={rowsId}>
          {visible.map((t) => (
            <Fragment key={t.predictionId}>
              {skipsToSelected && t.predictionId === selectedId && (
                <p className="timetable__skip">Later train you selected</p>
              )}
              <label className="timetable__row">
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
                  {t.stability ? (
                    <span className={`timetable__stability tone-${t.stability}`}>
                      <StabilityMark stability={t.stability} />
                      {STABILITY_LABELS[t.stability]}
                    </span>
                  ) : (
                    // No model forecast: say so in words rather than leave the slot empty.
                    <span className="timetable__stability tone-eta-only">BART ETA only</span>
                  )}
                </span>
              </label>
            </Fragment>
          ))}
        </div>
      )}

      {state === 'ready' && trains.length > INITIAL_TRAIN_LIMIT && (
        <button
          type="button"
          className="timetable__toggle"
          aria-expanded={expanded}
          aria-controls={rowsId}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? 'Show fewer trains' : `Show ${hidden} more ${hidden === 1 ? 'train' : 'trains'}`}
        </button>
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
