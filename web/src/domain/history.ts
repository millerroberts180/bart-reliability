import { formatClock, formatSpokenDuration } from './eta';
import type { PredictionHistoryPoint } from './types';

/**
 * Provisional prototype assumption: consecutive snapshots more than this many seconds
 * apart are a gap in the feed (the collector polls every 60 s; matches
 * max_collection_gap_s in config/eta_revision.toml). Not yet checked against real history.
 */
export const HISTORY_GAP_SECONDS = 90;

/**
 * Provisional prototype assumption: a change of at least this many seconds between
 * consecutive snapshots counts as a change in the summary; smaller ones are drift
 * (matches tier_a_spread_s in config/eta_revision.toml). Not yet checked against real history.
 */
export const REVISION_THRESHOLD_SECONDS = 30;

export interface HistoryObservation extends PredictionHistoryPoint {
  /**
   * Difference from the previous available published estimate in seconds (positive =
   * later); null for the first. After a gap this spans the missing snapshots, so it is
   * not an observed change: any number of changes may have happened in between.
   */
  changeSeconds: number | null;
  /** True when a gap in the feed precedes this observation. */
  afterGap: boolean;
  /** Seconds since the previous available snapshot when afterGap, otherwise null. */
  gapSeconds: number | null;
}

export interface HistoryAnalysis {
  observations: HistoryObservation[];
  /** Runs of observations without gaps; the chart draws one line per run. */
  segments: HistoryObservation[][];
  gapCount: number;
  /** Seconds from the first observation to the latest one. */
  spanSeconds: number;
  /** Latest published ETA minus the first one. */
  netChangeSeconds: number;
  /**
   * Observed changes of at least REVISION_THRESHOLD_SECONDS: between consecutive
   * snapshots with no gap between them. Differences across a gap are never counted.
   */
  revisionCount: number;
  /** Observed non-zero changes smaller than the threshold (also excluding gaps). */
  smallChangeCount: number;
}

const seconds = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 1000);

/**
 * Orders the history and keeps only observations at or before `latestFeedTimestamp`,
 * so the chart can never show a snapshot newer than the prediction it explains.
 */
export function analyzeHistory(points: PredictionHistoryPoint[], latestFeedTimestamp: string): HistoryAnalysis {
  const cutoff = Date.parse(latestFeedTimestamp);
  const ordered = points
    .filter((p) => Date.parse(p.feedTimestamp) <= cutoff)
    .sort((a, b) => Date.parse(a.feedTimestamp) - Date.parse(b.feedTimestamp));

  const observations: HistoryObservation[] = ordered.map((p, i) => {
    const previous = ordered[i - 1];
    const sincePrevious = previous ? seconds(previous.feedTimestamp, p.feedTimestamp) : 0;
    const afterGap = sincePrevious > HISTORY_GAP_SECONDS;
    return {
      ...p,
      changeSeconds: previous ? seconds(previous.publishedEtaAt, p.publishedEtaAt) : null,
      afterGap,
      gapSeconds: afterGap ? sincePrevious : null,
    };
  });

  const segments: HistoryObservation[][] = [];
  for (const o of observations) {
    const current = segments[segments.length - 1];
    if (!current || o.afterGap) segments.push([o]);
    else current.push(o);
  }

  // Only changes between consecutive snapshots with no gap between them were observed.
  const observed = observations.flatMap((o) => (o.changeSeconds !== null && !o.afterGap ? [o.changeSeconds] : []));
  const first = observations[0];
  const last = observations[observations.length - 1];
  return {
    observations,
    segments,
    gapCount: observations.filter((o) => o.afterGap).length,
    spanSeconds: first && last ? seconds(first.feedTimestamp, last.feedTimestamp) : 0,
    netChangeSeconds: first && last ? seconds(first.publishedEtaAt, last.publishedEtaAt) : 0,
    revisionCount: observed.filter((c) => Math.abs(c) >= REVISION_THRESHOLD_SECONDS).length,
    smallChangeCount: observed.filter((c) => c !== 0 && Math.abs(c) < REVISION_THRESHOLD_SECONDS).length,
  };
}

/**
 * True when BART published the same ETA at every snapshot, with no gap in which a change
 * could have gone unseen. Such a history needs no chart to be understood.
 */
export function isFlat(analysis: HistoryAnalysis): boolean {
  const { observations, gapCount, revisionCount, smallChangeCount, netChangeSeconds } = analysis;
  return observations.length > 1 && gapCount === 0 && revisionCount === 0 && smallChangeCount === 0 && netChangeSeconds === 0;
}

const NUMBER_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];
const count = (n: number) => NUMBER_WORDS[n] ?? String(n);

function spanPhrase(spanSeconds: number): string {
  if (spanSeconds < 60) return formatSpokenDuration(spanSeconds);
  const minutes = Math.round(spanSeconds / 60);
  return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`;
}

function timesPhrase(n: number): string {
  if (n === 1) return 'once';
  if (n === 2) return 'twice';
  return `${count(n)} times`;
}

export interface SummaryContext {
  /**
   * True when the window must be named by its snapshot time ("In the 14 minutes before the
   * 9:50:20 AM snapshot") rather than as "the last 14 minutes": a stale snapshot, or any
   * historical replay, where "the last" would read as live.
   */
  anchored: boolean;
}

/** One plain-language sentence (two with gaps) describing how BART changed this ETA. */
export function summarizeHistory(analysis: HistoryAnalysis, { anchored }: SummaryContext): string {
  const { observations, spanSeconds, netChangeSeconds: net, revisionCount, gapCount } = analysis;
  const first = observations[0];
  const last = observations[observations.length - 1];
  if (!first || !last) return 'No earlier snapshots of this ETA are available yet.';
  if (observations.length === 1) {
    return `Only one snapshot so far: BART first published this ETA at ${formatClock(first.feedTimestamp)}, so there is no change to show yet.`;
  }

  if (gapCount > 0) return summarizeWithGaps(analysis, { anchored });

  const window = anchored
    ? `In the ${spanPhrase(spanSeconds)} before the ${formatClock(last.feedTimestamp)} snapshot`
    : `Over the last ${spanPhrase(spanSeconds)}`;
  const direction = net > 0 ? 'later' : 'earlier';
  const amount = formatSpokenDuration(net);

  const threshold = `${REVISION_THRESHOLD_SECONDS} seconds`;
  let sentence: string;
  if (net === 0 && revisionCount === 0) sentence = `${window}, BART’s ETA for this train held steady.`;
  else if (net === 0) {
    sentence = `${window}, BART changed this ETA ${timesPhrase(revisionCount)} by ${threshold} or more, but it ended where it started.`;
  } else if (revisionCount === 0) {
    sentence = `${window}, BART’s ETA drifted ${amount} ${direction} in small changes of under ${threshold}.`;
  } else {
    const changes =
      revisionCount === 1
        ? `in one change of ${threshold} or more`
        : `across ${count(revisionCount)} changes of ${threshold} or more`;
    sentence = `${window}, BART moved this ETA ${amount} ${direction} ${changes}.`;
  }
  return sentence;
}

/**
 * With gaps, only the endpoints and the changes between consecutive snapshots are
 * known. The first sentence reports endpoint movement; the second reports observed
 * changes and says that changes during the gaps are unknown.
 */
function summarizeWithGaps(analysis: HistoryAnalysis, { anchored }: SummaryContext): string {
  const { observations, netChangeSeconds: net, revisionCount, smallChangeCount, gapCount } = analysis;
  const last = observations[observations.length - 1];
  const span = anchored && last
    ? `From the first available snapshot to the ${formatClock(last.feedTimestamp)} snapshot`
    : 'From the first to the latest available snapshot';
  const endpoint =
    net === 0
      ? `${span}, the ETA ended where it started.`
      : `${span}, the ETA ended ${formatSpokenDuration(net)} ${net > 0 ? 'later' : 'earlier'}.`;

  const gaps = gapCount === 1 ? 'one gap' : `${count(gapCount)} gaps`;
  const during = gapCount === 1 ? 'during the gap' : 'during the gaps';
  const threshold = `${REVISION_THRESHOLD_SECONDS} seconds`;
  let observed: string;
  if (revisionCount > 0) {
    const what = revisionCount === 1 ? `One observed change of ${threshold} or more` : `${capitalize(count(revisionCount))} observed changes of ${threshold} or more`;
    observed = `${what} occurred outside ${gaps}; additional changes ${during} are unknown.`;
  } else if (smallChangeCount > 0) {
    observed = `Outside ${gaps}, only small changes of under ${threshold} were observed; changes ${during} are unknown.`;
  } else {
    observed = `No change was observed outside ${gaps}; changes ${during} are unknown.`;
  }
  return `${endpoint} ${observed}`;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** "45 seconds later than the previous snapshot", "unchanged …", "first snapshot shown". */
export function describeChangeFromPrevious(o: HistoryObservation): string {
  if (o.changeSeconds === null) return 'first snapshot shown';
  const direction = o.changeSeconds > 0 ? 'later' : 'earlier';
  if (o.afterGap) {
    // Only the difference between the two available snapshots is known.
    const difference =
      o.changeSeconds === 0
        ? 'the same as the previous available snapshot'
        : `${formatSpokenDuration(o.changeSeconds)} ${direction} than the previous available snapshot`;
    const gap = o.gapSeconds === null ? 'a gap' : `a ${formatSpokenDuration(o.gapSeconds)} gap`;
    return `${difference}, across ${gap} in the feed; changes during the gap are unknown`;
  }
  if (o.changeSeconds === 0) return 'unchanged from the previous snapshot';
  return `${formatSpokenDuration(o.changeSeconds)} ${direction} than the previous snapshot`;
}

/**
 * Everything known about one observation, in words. Used for the chart's value (the
 * snapshot being inspected) and for the visible inspection line.
 */
export function describeObservation(
  o: HistoryObservation,
  isLatest: boolean,
  { includeSnapshot = true }: { includeSnapshot?: boolean } = {},
): string {
  const snapshot = includeSnapshot ? `${isLatest ? 'Latest snapshot' : 'Snapshot'} ${formatClock(o.feedTimestamp)}: ` : '';
  const away = o.publishedEtaSeconds > 0 ? `${formatSpokenDuration(o.publishedEtaSeconds)} away` : 'due';
  return `${snapshot}BART published ${formatClock(o.publishedEtaAt)}, ${away}, ${describeChangeFromPrevious(o)}.`;
}

/**
 * Accessible name for a populated chart: what is plotted and over what span. It
 * states the data, never the chart key, so a gap legend can't read as a status.
 */
export function describeChart(analysis: HistoryAnalysis, subject: string): string {
  const { observations, gapCount } = analysis;
  const first = observations[0];
  const last = observations[observations.length - 1];
  if (!first || !last) return `Chart of BART’s published ETA for ${subject}: no snapshots yet.`;
  const span =
    observations.length === 1
      ? `one snapshot, at ${formatClock(last.feedTimestamp)}`
      : `${observations.length} snapshots from ${formatClock(first.feedTimestamp)} to ${formatClock(last.feedTimestamp)}`;
  const gaps = gapCount === 0 ? '' : gapCount === 1 ? ', with one gap in the feed' : `, with ${count(gapCount)} gaps in the feed`;
  return `Chart of BART’s published ETA for ${subject}: ${span}${gaps}.`;
}
