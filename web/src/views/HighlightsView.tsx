import type { CSSProperties } from 'react';
import { VIEW_TITLE_ID } from '../App';
import { METHODOLOGY_URL } from '../components/SiteHeader';
import { ViewLink } from '../components/ViewLink';
import { useShowcase } from '../data/ShowcaseContext';
import { formatClock, formatDuration } from '../domain/eta';
import {
  describeChange,
  describeDirectionMatch,
  describeModelError,
  HORIZON_ADJECTIVE,
  HORIZON_LABELS,
  RETROSPECTIVE_NOTE,
  TERMS,
} from '../domain/revisionText';
import { routeColor } from '../domain/routeColors';
import { HORIZONS, type ChangeRow, type Horizon, type Showcase } from '../domain/showcase';
import { replaceParam, useSearchParam } from '../hooks/useView';
import { ShowcaseUnavailable } from './ShowcaseUnavailable';

export const CHANGES_TITLE_ID = 'changes-title';

function horizonFrom(value: string | null): Horizon {
  return HORIZONS.find((h) => h === value) ?? '300';
}

export function HighlightsView() {
  const state = useShowcase();
  const horizon = horizonFrom(useSearchParam('horizon'));

  return (
    <div className="view view--highlights">
      <section className="intro" aria-labelledby={VIEW_TITLE_ID}>
        <h1 id={VIEW_TITLE_ID} className="intro__title" tabIndex={-1}>
          ETA Reliability
        </h1>
        <p className="intro__lede">How might BART revise a published ETA as a train approaches?</p>
        <p className="intro__summary">
          The model forecasts how much BART will still change a train’s published ETA before BART settles on its final
          estimate. <strong>It does not predict when a train physically arrives.</strong>
        </p>

        {state.status === 'ready' && (
          <>
            <p className="intro__replay">
              <span className="intro__replay-label">Historical replay</span> {state.showcase.meta.localTime}
            </p>
            <dl className="figures">
              <div className="figures__item">
                <dt>Supported forecasts in this replay</dt>
                <dd>{state.showcase.meta.includedRecords}</dd>
              </div>
              <div className="figures__item">
                <dt>Stations represented</dt>
                <dd>{state.showcase.meta.stationsRepresented}</dd>
              </div>
              <div className="figures__item">
                <dt>Model version</dt>
                <dd className="figures__version">{state.showcase.meta.modelVersion}</dd>
              </div>
            </dl>
            <p className="intro__disclosure">{state.showcase.meta.disclosure}</p>
          </>
        )}
      </section>

      {state.status === 'ready' ? (
        <section className="changes" aria-labelledby={CHANGES_TITLE_ID}>
          <h2 id={CHANGES_TITLE_ID} className="section-title">
            Largest ETA changes in this replay
          </h2>
          <p className="changes__intro">
            Trains whose published ETA BART later moved the most, at each forecast horizon. These are revisions to BART’s
            ETA, not train delays.
          </p>
          <div className="segmented" role="group" aria-label="Forecast horizon">
            {HORIZONS.map((h) => (
              <button
                key={h}
                type="button"
                className="segmented__option"
                aria-pressed={h === horizon}
                onClick={() => replaceParam('horizon', h)}
              >
                <span className="segmented__dot" aria-hidden="true" />
                {HORIZON_LABELS[h]}
              </button>
            ))}
          </div>
          <p className="changes__count" aria-live="polite">
            {state.showcase.changes[horizon].length
              ? `Top ${state.showcase.changes[horizon].length} at the ${HORIZON_ADJECTIVE[horizon]} horizon, one per train.`
              : `No trains at the ${HORIZON_ADJECTIVE[horizon]} horizon in this replay.`}
          </p>
          <ol className="changes__list">
            {state.showcase.changes[horizon].map((row) => (
              <ChangeEntry key={row.predictionId} row={row} />
            ))}
          </ol>
          <p className="changes__context">{context(state.showcase)}</p>
          <p className="changes__note">
            “BART later published” is the final stable ETA BART published afterwards. {RETROSPECTIVE_NOTE} It is not a
            physical arrival time.
          </p>
        </section>
      ) : (
        <ShowcaseUnavailable state={state} />
      )}

      <p className="view-links">
        <ViewLink view="map">See the network map</ViewLink>
        <a href={METHODOLOGY_URL}>Methodology on GitHub</a>
      </p>
    </div>
  );
}

function ChangeEntry({ row }: { row: ChangeRow }) {
  const titleId = `change-${row.rank}-${row.horizonSeconds}`;
  return (
    <li className="change" aria-labelledby={titleId} style={{ '--route': routeColor(row.lineName) } as CSSProperties}>
      <div className="change__head">
        <span className="change__rank" aria-hidden="true">
          {row.rank}
        </span>
        <h3 id={titleId} className="change__title">
          {row.stationName} <span aria-hidden="true">→</span>
          <span className="visually-hidden">to</span> {row.destination}
        </h3>
        <p className="change__line">
          <span className="change__swatch" aria-hidden="true" />
          {row.lineName}
        </p>
      </div>

      <ol className="sequence" aria-label={`${TERMS.bart}, ${TERMS.adjusted}, then what ${TERMS.final}`}>
        <li className="sequence__step">
          <span className="sequence__label">BART said</span>
          <span className="sequence__value">{formatClock(row.bartPublishedEtaAt)}</span>
          <span className="sequence__detail">
            {TERMS.bart}, {formatDuration(row.bartPublishedEtaSeconds)} away
          </span>
        </li>
        <li className="sequence__step">
          <span className="sequence__label">Model expected</span>
          <span className="sequence__value">{formatClock(row.modelAdjustedEtaAt)}</span>
          <span className="sequence__detail">
            {TERMS.adjusted}. Predicted change: {describeChange(row.predictedRevisionSeconds)}
          </span>
        </li>
        <li className="sequence__step sequence__step--retrospective">
          <span className="sequence__label">BART later published</span>
          <span className="sequence__value">{formatClock(row.finalPublishedEtaAt)}</span>
          <span className="sequence__detail">
            Retrospective. Realized change: {describeChange(row.realizedRevisionSeconds)}
          </span>
        </li>
      </ol>

      <p className={`change__verdict ${row.directionMatch ? 'change__verdict--match' : 'change__verdict--differ'}`}>
        <svg className="change__mark" viewBox="0 0 14 14" aria-hidden="true">
          {row.directionMatch ? <path d="M2.5 7.5 5.5 10.5 11.5 3.5" /> : <path d="M3 3 11 11M11 3 3 11" />}
        </svg>
        <strong>{describeDirectionMatch(row.directionMatch)}.</strong> {describeModelError(row.modelErrorSeconds)}
      </p>
      <p className="change__link">
        <ViewLink
          view="explorer"
          params={{ station: row.stationId, boarding: row.boardingGroupId, train: row.predictionId }}
          aria-describedby={titleId}
        >
          View in the train explorer
        </ViewLink>
      </p>
    </li>
  );
}

/**
 * What the rankings alone would hide: the direction result over every train in the
 * replay, not only the largest changes, and how the moment was chosen.
 */
function context(showcase: Showcase): string {
  const records = [...showcase.retrospective.values()];
  const matched = records.filter((r) => r.directionMatch).length;
  return (
    `Across all ${records.length} trains in this replay, the predicted direction matched what BART later published for ` +
    `${matched} and differed for ${records.length - matched}. The moment was chosen from ` +
    `${showcase.meta.candidatesConsidered.toLocaleString('en-US')} snapshots of the day by coverage alone; no outcome ` +
    'or accuracy was read.'
  );
}
