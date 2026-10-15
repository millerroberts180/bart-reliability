import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { formatClock } from '../domain/eta';
import { describeObservation, type HistoryAnalysis, type HistoryObservation } from '../domain/history';
import { useElementWidth } from '../hooks/useElementWidth';

export interface FinalReference {
  /** Likely final published ETA (clock time). */
  at: string;
  /** Its 80% range, as clock times. */
  lowerAt: string;
  upperAt: string;
  coverage: string;
}

interface HistoryChartProps {
  analysis: HistoryAnalysis;
  final: FinalReference;
  /** Accessible description of what is charted (station and train). */
  label: string;
}

const MINUTE = 60_000;
/** Space kept above and below the highest and lowest values (layout only). */
const Y_PADDING_MS = 30_000;
/** Minimum vertical and horizontal distance between tick labels, in pixels. */
const MIN_Y_TICK_GAP_PX = 30;
const MIN_X_TICK_GAP_PX = 64;
const ms = (iso: string) => Date.parse(iso);

// Pacific wall-clock tick labels without AM/PM ("10:05"); full times appear in the
// inspection line and the table.
const tickFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Los_Angeles',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
});
const tickLabel = (t: number) => tickFormat.format(new Date(t)).replace(/\s?[AP]M$/, '');

function niceStep(spanMs: number, pixels: number, minGapPx: number): number {
  for (const minutes of [1, 2, 5, 10, 15, 30, 60]) {
    if ((minutes * MINUTE * pixels) / spanMs >= minGapPx) return minutes * MINUTE;
  }
  return 60 * MINUTE;
}

function ticks(start: number, end: number, step: number): number[] {
  const out: number[] = [];
  for (let t = Math.ceil(start / step) * step; t <= end; t += step) out.push(t);
  return out;
}

/**
 * Step chart of BART's published arrival time at each feed snapshot. Up = BART
 * moved the ETA later, down = earlier, flat = it held. A break in the line is a
 * gap in the feed. The dashed line is the model's likely final published ETA.
 */
export function HistoryChart({ analysis, final, label }: HistoryChartProps) {
  const [containerRef, width] = useElementWidth<HTMLDivElement>(640);
  const { observations, segments } = analysis;
  const latestIndex = observations.length - 1;
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const active = observations[activeIndex ?? latestIndex];
  const pointRefs = useRef<(SVGCircleElement | null)[]>([]);

  const compact = width < 480;
  const height = compact ? 250 : 290;
  // The right gutter holds the range bracket and the end labels ("Latest", "Likely final").
  const margin = { top: 30, right: compact ? 80 : 124, bottom: 50, left: compact ? 44 : 52 };
  const plotW = Math.max(40, width - margin.left - margin.right);
  const plotH = height - margin.top - margin.bottom;

  const first = observations[0];
  const last = observations[latestIndex];
  if (!first || !last) return null;

  // Time runs left to right and ends at the latest snapshot; a single snapshot sits at the right.
  const xEnd = ms(last.feedTimestamp);
  const xStart = observations.length > 1 ? ms(first.feedTimestamp) : xEnd - 5 * MINUTE;
  const x = (t: number) => margin.left + ((t - xStart) / (xEnd - xStart)) * plotW;

  // Published clock time, later at the top. Keep at least a 3-minute window so
  // seconds of drift don't look like large moves.
  const values = [...observations.map((o) => ms(o.publishedEtaAt)), ms(final.at), ms(final.lowerAt), ms(final.upperAt)];
  let yMin = Math.min(...values) - Y_PADDING_MS;
  let yMax = Math.max(...values) + Y_PADDING_MS;
  if (yMax - yMin < 3 * MINUTE) {
    const mid = (yMin + yMax) / 2;
    yMin = mid - 1.5 * MINUTE;
    yMax = mid + 1.5 * MINUTE;
  }
  const y = (t: number) => margin.top + (1 - (t - yMin) / (yMax - yMin)) * plotH;

  const yTicks = ticks(yMin, yMax, niceStep(yMax - yMin, plotH, MIN_Y_TICK_GAP_PX));
  const xTicks = observations.length > 1 ? ticks(xStart, xEnd, niceStep(xEnd - xStart, plotW, MIN_X_TICK_GAP_PX)) : [];

  const stepPath = (seg: HistoryObservation[]) =>
    seg
      .map((o, i) => {
        const px = x(ms(o.feedTimestamp)).toFixed(1);
        const py = y(ms(o.publishedEtaAt)).toFixed(1);
        return i === 0 ? `M${px} ${py}` : `H${px} V${py}`;
      })
      .join(' ');

  // A gap spans from the last snapshot before it to the first one after it.
  const gaps = observations.flatMap((o, i) => {
    const before = observations[i - 1];
    return o.afterGap && before ? [{ x1: x(ms(before.feedTimestamp)), x2: x(ms(o.feedTimestamp)) }] : [];
  });

  // End labels in the right gutter, pushed apart so they never overlap.
  const finalY = y(ms(final.at));
  const latestY = y(ms(last.publishedEtaAt));
  let latestLabelY = latestY;
  let finalLabelY = finalY;
  const LABEL_GAP = 22; // label line height plus breathing room
  if (Math.abs(latestLabelY - finalLabelY) < LABEL_GAP) {
    const mid = (latestLabelY + finalLabelY) / 2;
    const finalAbove = finalY <= latestY;
    finalLabelY = mid + (finalAbove ? -1 : 1) * (LABEL_GAP / 2);
    latestLabelY = mid + (finalAbove ? 1 : -1) * (LABEL_GAP / 2);
  }
  const gutterX = margin.left + plotW + 10;
  const labelX = gutterX + 12;

  const focusPoint = (i: number) => {
    const clamped = Math.max(0, Math.min(latestIndex, i));
    setActiveIndex(clamped);
    pointRefs.current[clamped]?.focus();
  };
  const onKeyDown = (e: KeyboardEvent, i: number) => {
    const moves: Record<string, number> = { ArrowLeft: i - 1, ArrowDown: i - 1, ArrowRight: i + 1, ArrowUp: i + 1, Home: 0, End: latestIndex };
    const next = moves[e.key];
    if (next === undefined) return;
    e.preventDefault();
    focusPoint(next);
  };
  const nearest = (clientX: number, rect: DOMRect) => {
    const t = xStart + ((clientX - rect.left - margin.left) / plotW) * (xEnd - xStart);
    let best = 0;
    observations.forEach((o, i) => {
      const bestObs = observations[best];
      if (bestObs && Math.abs(ms(o.feedTimestamp) - t) < Math.abs(ms(bestObs.feedTimestamp) - t)) best = i;
    });
    return best;
  };
  const onPointer = (e: PointerEvent<SVGRectElement>) => {
    const svg = e.currentTarget.ownerSVGElement;
    if (svg) setActiveIndex(nearest(e.clientX, svg.getBoundingClientRect()));
  };
  const tabStop = activeIndex ?? latestIndex;

  return (
    <div className="history-chart" ref={containerRef}>
      <svg
        className="history-chart__svg"
        width={width}
        height={height}
        role="group"
        aria-label={`${label}. Step chart of BART’s published arrival time at each feed snapshot; up means later. Use the arrow keys to move between snapshots.`}
      >
        {/* Horizontal grid and y-axis: published arrival time */}
        <g aria-hidden="true">
          {yTicks.map((t) => (
            <g key={t}>
              <line className="history-chart__grid" x1={margin.left} x2={margin.left + plotW} y1={y(t)} y2={y(t)} />
              <text className="history-chart__tick" x={margin.left - 8} y={y(t)} dy="0.32em" textAnchor="end">
                {tickLabel(t)}
              </text>
            </g>
          ))}
          <line
            className="history-chart__axis"
            x1={margin.left}
            x2={margin.left + plotW}
            y1={margin.top + plotH}
            y2={margin.top + plotH}
          />
          {xTicks.map((t) => (
            <text key={t} className="history-chart__tick" x={x(t)} y={margin.top + plotH + 20} textAnchor="middle">
              {tickLabel(t)}
            </text>
          ))}
          <text className="history-chart__axis-title" x={0} y={16}>
            {compact ? 'Published ETA' : 'BART’s published ETA (higher = later)'}
          </text>
          <text className="history-chart__axis-title" x={margin.left + plotW} y={height - 6} textAnchor="end">
            Snapshot time
          </text>
          {observations.length === 1 && (
            <text className="history-chart__tick" x={x(xEnd)} y={margin.top + plotH + 20} textAnchor="end">
              {tickLabel(xEnd)}
            </text>
          )}
        </g>

        {/* Gaps in the feed: the line breaks and the span is shaded */}
        <g aria-hidden="true">
          {gaps.map((g) => (
            <g key={g.x1}>
              <rect className="history-chart__gap" x={g.x1} y={margin.top} width={g.x2 - g.x1} height={plotH} />
              {g.x2 - g.x1 >= 44 && (
                <text className="history-chart__gap-label" x={(g.x1 + g.x2) / 2} y={margin.top + 14} textAnchor="middle">
                  no data
                </text>
              )}
            </g>
          ))}
        </g>

        {/* Model reference: likely final published ETA and its range */}
        <g aria-hidden="true">
          <line className="history-chart__final" x1={margin.left} x2={gutterX} y1={finalY} y2={finalY} />
          <line className="history-chart__range" x1={gutterX} x2={gutterX} y1={y(ms(final.upperAt))} y2={y(ms(final.lowerAt))} />
          <line className="history-chart__range" x1={gutterX - 4} x2={gutterX + 4} y1={y(ms(final.upperAt))} y2={y(ms(final.upperAt))} />
          <line className="history-chart__range" x1={gutterX - 4} x2={gutterX + 4} y1={y(ms(final.lowerAt))} y2={y(ms(final.lowerAt))} />
          <text className="history-chart__end-label history-chart__end-label--final" x={labelX} y={finalLabelY} dy="0.32em">
            {compact ? 'Final' : 'Likely final'}
          </text>
          <text className="history-chart__end-label" x={labelX} y={latestLabelY} dy="0.32em">
            Latest
          </text>
        </g>

        {/* BART's published ETA */}
        <g aria-hidden="true">
          {segments.map((seg, i) => (
            <path key={i} className="history-chart__line" d={stepPath(seg)} />
          ))}
        </g>

        <rect
          className="history-chart__hit"
          x={margin.left}
          y={margin.top}
          width={plotW}
          height={plotH}
          onPointerMove={onPointer}
          onPointerDown={onPointer}
          aria-hidden="true"
        />

        {active && (
          <circle
            className="history-chart__ring"
            cx={x(ms(active.feedTimestamp))}
            cy={y(ms(active.publishedEtaAt))}
            r={10}
            aria-hidden="true"
          />
        )}

        {observations.map((o, i) => {
          const isActive = active === o;
          return (
            <circle
              key={o.feedTimestamp}
              ref={(el) => {
                pointRefs.current[i] = el;
              }}
              className={`history-chart__point${i === latestIndex ? ' history-chart__point--latest' : ''}${isActive ? ' is-active' : ''}`}
              cx={x(ms(o.feedTimestamp))}
              cy={y(ms(o.publishedEtaAt))}
              r={i === latestIndex ? 5 : 3.5}
              tabIndex={i === tabStop ? 0 : -1}
              role="img"
              aria-label={describeObservation(o, i === latestIndex)}
              onFocus={() => setActiveIndex(i)}
              onKeyDown={(e) => onKeyDown(e, i)}
            />
          );
        })}
      </svg>

      {active && (
        <p className="history-chart__inspect" data-testid="history-inspect">
          <span className="history-chart__inspect-label">
            {active === last ? 'Latest snapshot' : 'Snapshot'} {formatClock(active.feedTimestamp)}
          </span>{' '}
          {describeObservation(active, active === last, { includeSnapshot: false })}
        </p>
      )}
    </div>
  );
}
