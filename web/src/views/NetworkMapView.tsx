import { useId, useMemo, type CSSProperties, type KeyboardEvent } from 'react';
import { VIEW_TITLE_ID } from '../App';
import { ViewLink } from '../components/ViewLink';
import { useShowcase } from '../data/ShowcaseContext';
import {
  keyStations,
  lineEnds,
  linesWithTrains,
  routeOnLine,
  stationFigures,
  stationOnLine,
  type Line,
  type StationFigures,
} from '../domain/mapData';
import {
  bubbleFill,
  bubbleRadius,
  chevronOnDark,
  LITTLE_CHANGE_S,
  MAP_MODE_LABELS,
  MAP_MODES,
  markRadius,
  toneOf,
  type MapMode,
} from '../domain/mapScale';
import { describeChange, HORIZON_SHORT, RETROSPECTIVE_NOTE } from '../domain/revisionText';
import { routeColor } from '../domain/routeColors';
import type { Horizon, MapTrain, NetworkStation, Showcase } from '../domain/showcase';
import { useElementWidth } from '../hooks/useElementWidth';
import { replaceParam, useSearchParam } from '../hooks/useView';
import { LABEL_FONT, LINE_HEIGHT, labelOffset, mapLabel, placeLabels } from './mapLabels';
import { ShowcaseUnavailable } from './ShowcaseUnavailable';

function modeFrom(value: string | null): MapMode {
  return MAP_MODES.find((m) => m === value) ?? 'forecast';
}

const MODE_NOTES: Record<MapMode, string> = {
  forecast:
    'Each bubble is a station’s median revision the model expected, from what was known at the replay moment; the dashed ring is what BART later published.',
  published: `Each bubble is a station’s median revision BART later published; the thin ring is what the model expected. ${RETROSPECTIVE_NOTE}`,
};

/** The value a station is drawn by in each mode, and the other mode's, for its ring. */
function valuesOf(f: StationFigures | undefined, mode: MapMode): { value: number | null; other: number | null } {
  if (!f) return { value: null, other: null };
  return mode === 'forecast'
    ? { value: f.medianPredicted, other: f.medianRealized }
    : { value: f.medianRealized, other: f.medianPredicted };
}

const chevron = (c: number, later: boolean) =>
  later ? `M${-c} ${c * 0.5} L0 ${-c * 0.5} L${c} ${c * 0.5}` : `M${-c} ${-c * 0.5} L0 ${c * 0.5} L${c} ${-c * 0.5}`;

export function NetworkMapView() {
  const state = useShowcase();
  const mode = modeFrom(useSearchParam('mode'));
  const selectedId = useSearchParam('station');
  const lineParam = useSearchParam('line');

  return (
    <div className="view view--map">
      <div className="view-head">
        <h1 id={VIEW_TITLE_ID} className="view-head__title" tabIndex={-1}>
          Network map
        </h1>
        <p className="view-head__lede">
          An original schematic from BART’s schedule data: how BART’s published ETA was revised at each station.
        </p>
      </div>
      {state.status === 'ready' ? (
        <MapContent showcase={state.showcase} mode={mode} selectedId={selectedId} lineParam={lineParam} />
      ) : (
        <ShowcaseUnavailable state={state} />
      )}
    </div>
  );
}

function MapContent({
  showcase,
  mode,
  selectedId,
  lineParam,
}: {
  showcase: Showcase;
  mode: MapMode;
  selectedId: string | null;
  lineParam: string | null;
}) {
  const { network } = showcase;
  const lines = useMemo(() => linesWithTrains(network.trains), [network]);
  const line = lines.find((l) => l.toLowerCase() === lineParam) ?? null;
  const figures = useMemo(() => stationFigures(network.trains, line), [network, line]);
  const selected = selectedId ? network.stations.find((s) => s.stationId === selectedId) : undefined;
  const select = (id: string) => replaceParam('station', id);

  return (
    <>
      <div className="map-controls">
        <div className="segmented" role="group" aria-label="Map display">
          {MAP_MODES.map((m) => (
            <button
              key={m}
              type="button"
              className="segmented__option"
              aria-pressed={m === mode}
              onClick={() => replaceParam('mode', m)}
            >
              <span className="segmented__dot" aria-hidden="true" />
              {MAP_MODE_LABELS[m]}
            </button>
          ))}
        </div>
        <div className="line-filter" role="group" aria-labelledby="line-filter-label">
          <span id="line-filter-label" className="line-filter__label">
            Line
          </span>
          {[null, ...lines].map((l) => (
            <button
              key={l ?? 'all'}
              type="button"
              className="line-filter__option"
              aria-pressed={l === line}
              onClick={() => replaceParam('line', l ? l.toLowerCase() : null)}
              style={l ? ({ '--route': routeColor(`${l} line`) } as CSSProperties) : undefined}
            >
              <span className={l ? 'line-filter__swatch' : 'line-filter__swatch line-filter__swatch--all'} aria-hidden="true" />
              {l ?? 'All'}
            </button>
          ))}
        </div>
      </div>
      <p className="map-takeaway" aria-live="polite">
        {takeaway(figures, mode, line)}
      </p>

      <div className="map-layout">
        <figure className="network" aria-labelledby="map-legend-title">
          <a className="skip-link network__skip" href="#station-panel">
            Skip the map to the station details
          </a>
          <NetworkSvg
            showcase={showcase}
            figures={figures}
            mode={mode}
            line={line}
            selectedId={selected?.stationId ?? null}
            onSelect={select}
          />
        </figure>
        <StationPanel
          station={selected}
          figures={selected ? figures.get(selected.stationId) : undefined}
          mode={mode}
          line={line}
        />
        <MapLegend mode={mode} note={MODE_NOTES[mode]} />
      </div>

      <StationTable
        stations={network.stations}
        figures={figures}
        mode={mode}
        line={line}
        selectedId={selected?.stationId ?? null}
        onSelect={select}
      />
    </>
  );
}

/** Stations in reading order: top to bottom, then left to right, so tabbing follows the eye. */
const NO_STATIONS: ReadonlySet<string> = new Set();

function readingOrder(stations: NetworkStation[]): NetworkStation[] {
  return [...stations].sort((a, b) => a.y - b.y || a.x - b.x);
}

function NetworkSvg({
  showcase,
  figures,
  mode,
  line,
  selectedId,
  onSelect,
}: {
  showcase: Showcase;
  figures: Map<string, StationFigures>;
  mode: MapMode;
  line: Line | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const titleId = useId();
  const { network } = showcase;
  const [frame, renderedWidth] = useElementWidth<HTMLDivElement>(network.width);
  // Rendered pixels per viewBox unit. The whole network always fits the window; on a phone
  // only stations where lines meet or end (and the selected one) are named, larger: line
  // ends first, and a name that would touch another is left to the table.
  const scale = renderedWidth / network.width;
  const compact = scale < 0.6;
  const font = compact ? Math.min(44, 12.5 / scale) : LABEL_FONT;
  const keys = useMemo(() => keyStations(network.routes), [network]);
  const ends = useMemo(() => lineEnds(network.routes), [network]);
  const at = new Map(network.stations.map((s) => [s.stationId, s]));
  const radius = (s: NetworkStation) => markRadius(valuesOf(figures.get(s.stationId), mode).value);
  const labelled = (s: NetworkStation) => !compact || keys.has(s.stationId) || s.stationId === selectedId;
  const placement = placeLabels(network.stations, labelled, radius, network.width, {
    font,
    height: network.height,
    dropOnCollision: compact,
    first: selectedId,
    early: compact ? ends : NO_STATIONS,
  });
  const onKey = (event: KeyboardEvent<SVGGElement>, id: string) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onSelect(id);
    }
  };
  const points = (ids: string[]) =>
    ids
      .map((id) => at.get(id))
      .filter((s): s is NetworkStation => Boolean(s))
      .map((s) => `${s.x},${s.y}`)
      .join(' ');
  // Largest marks first, so a small one is never hidden under a large neighbour.
  const bySize = [...network.stations].sort((a, b) => radius(b) - radius(a));

  return (
    <div className="network__frame" ref={frame}>
      <svg
        className="network__svg"
        viewBox={`0 0 ${network.width} ${network.height}`}
        role="group"
        aria-labelledby={titleId}
      >
        <title id={titleId}>
          {`Network schematic: ${MAP_MODE_LABELS[mode].toLowerCase()}${line ? `, ${line} line` : ''}`}
        </title>
        <g className={line ? 'network__tracks network__tracks--quiet' : 'network__tracks'} aria-hidden="true">
          {network.routes.map((r) => (
            <polyline key={r.routeId} points={points(r.stationIds)} />
          ))}
        </g>
        {line && (
          <g className="network__line" aria-hidden="true" style={{ '--route': routeColor(`${line} line`) } as CSSProperties}>
            {network.routes
              .filter((r) => routeOnLine(r, line))
              .map((r) => (
                <polyline key={`casing-${r.routeId}`} className="network__casing" points={points(r.stationIds)} />
              ))}
            {network.routes
              .filter((r) => routeOnLine(r, line))
              .map((r) => (
                <polyline key={r.routeId} points={points(r.stationIds)} />
              ))}
          </g>
        )}
        <g className="network__marks" aria-hidden="true">
          {bySize.map((s) => (
            <Mark
              key={s.stationId}
              station={s}
              {...valuesOf(figures.get(s.stationId), mode)}
              mode={mode}
              dim={!stationOnLine(s, line)}
            />
          ))}
        </g>
        <g className="network__stations">
          {readingOrder(network.stations).map((s) => {
            const f = figures.get(s.stationId);
            const { value } = valuesOf(f, mode);
            const r = radius(s);
            const place = placement.get(s.stationId);
            const classes = [
              'station',
              f ? '' : 'station--none',
              s.stationId === selectedId ? 'station--selected' : '',
              stationOnLine(s, line) ? '' : 'station--dim',
            ];
            return (
              <g
                key={s.stationId}
                className={classes.filter(Boolean).join(' ')}
                transform={`translate(${s.x} ${s.y})`}
                role="button"
                tabIndex={0}
                aria-pressed={s.stationId === selectedId}
                aria-label={stationLabel(s, f, mode, value, line)}
                onClick={() => onSelect(s.stationId)}
                onKeyDown={(e) => onKey(e, s.stationId)}
              >
                <circle className="station__hit" r={Math.max(r + 4, compact ? 22 : 17)} />
                <circle className="station__ring" r={r + 5} />
                {place && (
                  <StationName lines={mapLabel(s)} {...labelOffset(place, r, font, mapLabel(s).length)} />
                )}
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}

/**
 * A station's mark: a bubble sized and shaded by the revision, with a chevron for its
 * direction and a ring for the other mode's value; a dot for little or no change; a small
 * hollow circle with no supported forecast.
 */
function StationName({
  lines,
  x,
  y,
  textAnchor,
  fontSize,
}: {
  lines: string[];
  x: number;
  y: number;
  textAnchor: 'start' | 'end' | 'middle';
  fontSize: number;
}) {
  return (
    <text className="station__label" x={x} y={y} textAnchor={textAnchor} fontSize={fontSize}>
      {lines.map((line, i) => (
        <tspan key={line} x={x} dy={i === 0 ? 0 : fontSize * LINE_HEIGHT}>
          {line}
        </tspan>
      ))}
    </text>
  );
}

function Mark({
  station,
  value,
  other,
  mode,
  dim,
}: {
  station: NetworkStation;
  value: number | null;
  other: number | null;
  mode: MapMode;
  dim: boolean;
}) {
  // The other mode's value as a ring, drawn only where it differs visibly from the bubble.
  const showRing = other !== null && Math.abs(markRadius(other) - markRadius(value)) >= 2.5;
  const ring =
    showRing && other !== null ? (
      <circle className={`mark__ring mark__ring--${mode === 'forecast' ? 'published' : 'forecast'}`} r={markRadius(other)} />
    ) : null;
  let body;
  if (value === null) {
    body = <circle className="mark mark--none" r={5} />;
  } else if (Math.abs(value) < LITTLE_CHANGE_S) {
    body = <circle className="mark mark--little" r={6} />;
  } else {
    const r = bubbleRadius(value);
    const later = value > 0;
    body = (
      <>
        <circle className={`mark mark--${later ? 'later' : 'earlier'}`} r={r} style={{ fill: bubbleFill(value) }} />
        <path
          className={chevronOnDark(value) ? 'mark__chevron mark__chevron--light' : 'mark__chevron'}
          d={chevron(Math.min(5, r * 0.42), later)}
        />
      </>
    );
  }
  return (
    <g className={dim ? 'mark-group mark-group--dim' : 'mark-group'} transform={`translate(${station.x} ${station.y})`}>
      {body}
      {ring}
    </g>
  );
}

function stationLabel(
  s: NetworkStation,
  f: StationFigures | undefined,
  mode: MapMode,
  value: number | null,
  line: Line | null,
): string {
  const where = line ? `${s.stationName}, ${line} line` : s.stationName;
  if (!f || value === null) {
    return line && !stationOnLine(s, line)
      ? `${where}: not on this line`
      : `${where}: no supported forecast at this replay moment`;
  }
  const trains = `${f.count} supported ${f.count === 1 ? 'train' : 'trains'}`;
  const what = mode === 'forecast' ? 'median expected revision' : 'median revision BART later published';
  return `${where}: ${trains}, ${what} ${describeChange(value)}`;
}

/** One computed sentence on what the map shows in this mode, for every line or one. */
function takeaway(figures: Map<string, StationFigures>, mode: MapMode, line: Line | null): string {
  const values = [...figures.values()].map((f) => valuesOf(f, mode).value ?? 0);
  const later = values.filter((v) => toneOf(v).startsWith('later')).length;
  const earlier = values.filter((v) => toneOf(v).startsWith('earlier')).length;
  const what = mode === 'forecast' ? 'The model expected the ETA to move later' : 'BART’s ETA later moved later';
  const scope = line ? ` on the ${line} line` : '';
  return `${what} at ${later} of ${values.length} stations with a supported forecast${scope}, and earlier at ${earlier}.`;
}

function MapLegend({ mode, note }: { mode: MapMode; note: string }) {
  const later = mode === 'forecast' ? 'ETA expected to move later' : 'ETA moved later';
  const earlier = mode === 'forecast' ? 'ETA expected to move earlier' : 'ETA moved earlier';
  return (
    <div className="map-legend">
      <p id="map-legend-title" className="map-legend__title">
        {mode === 'forecast' ? 'Median expected ETA revision' : 'Median ETA revision BART later published'}
      </p>
      <p className="map-legend__note">{note}</p>
      <ul className="map-legend__items">
        <li className="map-legend__item">
          <svg className="map-legend__sizes" viewBox="0 0 120 56" aria-hidden="true">
            {[15, 60, 120].map((s, i) => (
              <circle
                key={s}
                className="mark mark--later"
                cx={[12, 44, 90][i]}
                cy={28}
                r={bubbleRadius(s)}
                style={{ fill: bubbleFill(s) }}
              />
            ))}
          </svg>
          Larger and redder as the revision grows: 15 sec, 1 min, 2 min
        </li>
        <li className="map-legend__item">
          <LegendGlyph seconds={60} /> {later}
        </li>
        <li className="map-legend__item">
          <LegendGlyph seconds={-60} /> {earlier}
        </li>
        <li className="map-legend__item">
          <svg className="map-legend__glyph" viewBox="-14 -14 28 28" aria-hidden="true">
            <circle className="mark mark--little" r={6} />
          </svg>
          Little or no change, under 15 sec
        </li>
        <li className="map-legend__item">
          <svg className="map-legend__glyph" viewBox="-14 -14 28 28" aria-hidden="true">
            <circle className={`mark__ring mark__ring--${mode === 'forecast' ? 'published' : 'forecast'}`} r={10} />
          </svg>
          {mode === 'forecast'
            ? 'Dashed ring: what BART later published (retrospective)'
            : 'Thin ring: what the model expected at the time'}
        </li>
        <li className="map-legend__item">
          <svg className="map-legend__glyph" viewBox="-14 -14 28 28" aria-hidden="true">
            <circle className="mark mark--none" r={5} />
          </svg>
          No supported forecast at this replay moment
        </li>
      </ul>
    </div>
  );
}

function LegendGlyph({ seconds }: { seconds: number }) {
  return (
    <svg className="map-legend__glyph" viewBox="-14 -14 28 28" aria-hidden="true">
      <circle className={`mark mark--${seconds > 0 ? 'later' : 'earlier'}`} r={11} style={{ fill: bubbleFill(seconds) }} />
      <path className="mark__chevron mark__chevron--light" d={chevron(4.6, seconds > 0)} />
    </svg>
  );
}

function StationPanel({
  station,
  figures,
  mode,
  line,
}: {
  station: NetworkStation | undefined;
  figures: StationFigures | undefined;
  mode: MapMode;
  line: Line | null;
}) {
  if (!station) {
    return (
      <aside id="station-panel" className="station-panel" aria-live="polite">
        <h2 className="station-panel__title">Select a station</h2>
        <p>Choose a station on the map or in the table below to see its largest ETA revisions.</p>
      </aside>
    );
  }
  const scope = line ? ` on the ${line} line` : '';
  const link = figures ? (mode === 'forecast' ? figures.largestPredicted : figures.largestRealized) : null;
  return (
    <aside id="station-panel" className="station-panel" aria-live="polite" aria-labelledby="station-panel-title">
      <h2 id="station-panel-title" className="station-panel__title">
        {station.stationName}
      </h2>
      {!figures || !figures.largestPredicted || !figures.largestRealized ? (
        <p className="station-panel__none">
          {line && !stationOnLine(station, line)
            ? `The ${line} line does not stop here.`
            : `No supported forecast${scope} at this replay moment.`}
        </p>
      ) : (
        <>
          <p className="station-panel__count">
            {figures.count} supported {figures.count === 1 ? 'train' : 'trains'}
            {scope} at this moment
          </p>
          <dl className="station-panel__facts">
            {(() => {
              const forecast = (
                <PanelFact
                  key="forecast"
                  term="Largest expected ETA revision"
                  seconds={figures.largestPredicted.predictedRevisionSeconds}
                  train={figures.largestPredicted}
                />
              );
              const published = (
                <PanelFact
                  key="published"
                  term="Largest ETA revision BART later published"
                  seconds={figures.largestRealized.realizedRevisionSeconds}
                  train={figures.largestRealized}
                  retrospective
                />
              );
              // The fact for the map's current mode comes first.
              return mode === 'published' ? [published, forecast] : [forecast, published];
            })()}
          </dl>
          {link && (
            <p className="station-panel__link">
              <ViewLink
                view="explorer"
                params={{ station: station.stationId, boarding: link.boardingGroupId, train: link.predictionId }}
              >
                View the {link.destination} train in the train explorer
              </ViewLink>
            </p>
          )}
        </>
      )}
    </aside>
  );
}

function PanelFact({
  term,
  seconds,
  train,
  retrospective = false,
}: {
  term: string;
  seconds: number;
  train: MapTrain;
  retrospective?: boolean;
}) {
  return (
    <div className="station-panel__fact">
      <dt>
        {term}
        {retrospective && <span className="station-panel__retro"> (retrospective)</span>}
      </dt>
      <dd>
        <span className="station-panel__value">{capitalize(describeChange(seconds))}</span>
        <span className="station-panel__train">
          {train.destination} train · {train.lineName} · {HORIZON_SHORT[String(train.horizonSeconds) as Horizon]} forecast
        </span>
      </dd>
    </div>
  );
}

function StationTable({
  stations,
  figures,
  mode,
  line,
  selectedId,
  onSelect,
}: {
  stations: NetworkStation[];
  figures: Map<string, StationFigures>;
  mode: MapMode;
  line: Line | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const sorted = [...stations]
    .filter((s) => stationOnLine(s, line))
    .sort((a, b) => a.stationName.localeCompare(b.stationName));
  return (
    <details className="station-table">
      <summary>{line ? `Every ${line} line station as a table` : 'Every station as a table'}</summary>
      <div className="station-table__scroll">
        <table>
          <caption className="visually-hidden">Stations, their supported trains and median ETA revisions</caption>
          <thead>
            <tr>
              <th scope="col">Station</th>
              <th scope="col">Supported trains</th>
              <th scope="col">Median expected revision</th>
              <th scope="col">Median revision BART later published</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((s) => {
              const f = figures.get(s.stationId);
              return (
                <tr key={s.stationId} aria-current={s.stationId === selectedId ? 'true' : undefined}>
                  <th scope="row">
                    <button type="button" className="link-button" onClick={() => onSelect(s.stationId)}>
                      {s.stationName}
                    </button>
                  </th>
                  <td>{f?.count ?? 'None'}</td>
                  <td>{cell(f?.medianPredicted ?? null, mode === 'forecast')}</td>
                  <td>{cell(f?.medianRealized ?? null, mode === 'published')}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function cell(seconds: number | null, current: boolean) {
  if (seconds === null) return <span className="station-table__none">No supported forecast</span>;
  return <span className={current ? 'station-table__current' : undefined}>{capitalize(describeChange(seconds))}</span>;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
