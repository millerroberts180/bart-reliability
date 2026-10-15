import type { StabilityClass } from './types';

/** Collector polls every 60 s; a snapshot older than two polls is stale. */
export const STALE_AFTER_SECONDS = 120;

/** Class boundaries on the probability of a revision larger than the threshold. */
export const STABILITY_CUTOFFS = { mayBeRevised: 0.25, likelyToBeRevised: 0.5 } as const;

/**
 * current published ETA + predicted revision = likely final published ETA.
 * The result is still a published estimate, never an observed arrival.
 */
export function likelyFinalEtaSeconds(currentEtaSeconds: number, predictedRevisionSeconds: number): number {
  return currentEtaSeconds + predictedRevisionSeconds;
}

/** Shift a clock time by a number of seconds. */
export function addSeconds(iso: string, seconds: number): string {
  return new Date(Date.parse(iso) + seconds * 1000).toISOString();
}

export function classifyStability(revisionProbability: number): StabilityClass {
  if (revisionProbability >= STABILITY_CUTOFFS.likelyToBeRevised) return 'likely_to_be_revised';
  if (revisionProbability >= STABILITY_CUTOFFS.mayBeRevised) return 'may_be_revised';
  return 'likely_to_hold';
}

export const STABILITY_LABELS: Record<StabilityClass, string> = {
  likely_to_hold: 'Likely to hold',
  may_be_revised: 'May be revised',
  likely_to_be_revised: 'Likely to be revised',
};

export interface Freshness {
  ageSeconds: number;
  stale: boolean;
}

export function assessFreshness(feedTimestamp: string, now: Date, staleAfterSeconds = STALE_AFTER_SECONDS): Freshness {
  const ageSeconds = Math.max(0, Math.round((now.getTime() - Date.parse(feedTimestamp)) / 1000));
  return { ageSeconds, stale: ageSeconds > staleAfterSeconds };
}

/** Whole minutes and seconds of a duration, omitting zero parts (but never empty). */
export function durationParts(totalSeconds: number): [number, 'min' | 's'][] {
  const s = Math.abs(Math.round(totalSeconds));
  const minutes = Math.floor(s / 60);
  const seconds = s % 60;
  const parts: [number, 'min' | 's'][] = [];
  if (minutes > 0) parts.push([minutes, 'min']);
  if (seconds > 0 || minutes === 0) parts.push([seconds, 's']);
  return parts;
}

/** "7 min 35 s", "45 s", "12 min". Sign is ignored; callers word direction. */
export function formatDuration(totalSeconds: number): string {
  return durationParts(totalSeconds)
    .map(([value, unit]) => `${value} ${unit}`)
    .join(' ');
}

export const MINUS = '−';

/** "+1 min 25 s", "−40 s", "0 s". */
export function formatSignedDuration(totalSeconds: number): string {
  const rounded = Math.round(totalSeconds);
  if (rounded === 0) return '0 s';
  return `${rounded > 0 ? '+' : MINUS}${formatDuration(rounded)}`;
}

/**
 * Duration for reading copy: "12 seconds", "1 second", "2 min 10 sec", "12 min".
 * Sign is ignored.
 */
export function formatSpokenDuration(totalSeconds: number): string {
  const s = Math.abs(Math.round(totalSeconds));
  if (s < 60) return `${s} ${s === 1 ? 'second' : 'seconds'}`;
  return durationParts(s)
    .map(([value, unit]) => `${value} ${unit === 's' ? 'sec' : 'min'}`)
    .join(' ');
}

/** "about 12 seconds later", "about 40 seconds earlier", "no change expected". */
export function describeRevision(seconds: number): string {
  const direction = revisionDirectionWord(seconds);
  if (direction === 'unchanged') return 'no change expected';
  return `about ${formatSpokenDuration(seconds)} ${direction}`;
}

/**
 * A revision range in words, always naming the direction:
 * "10 seconds earlier to 35 seconds later", "20 seconds to 2 min 30 sec later",
 * "5 seconds to 45 seconds earlier", "no change to 1 min 50 sec later".
 */
export function describeRevisionRange(lowerSeconds: number, upperSeconds: number): string {
  const lower = Math.round(lowerSeconds);
  const upper = Math.round(upperSeconds);
  const spoken = (v: number) => (v === 0 ? 'no change' : formatSpokenDuration(v));
  if (lower < 0 && upper > 0) return `${formatSpokenDuration(lower)} earlier to ${formatSpokenDuration(upper)} later`;
  if (lower >= 0 && upper > 0) return `${spoken(lower)} to ${formatSpokenDuration(upper)} later`;
  if (lower < 0 && upper <= 0) return `${spoken(upper)} to ${formatSpokenDuration(lower)} earlier`;
  return 'no change';
}

/**
 * Glanceable time remaining, rounded to whole minutes: "About 2 min away",
 * "Less than 1 min away". The exact value stays in the calculation.
 */
export function describeAwayGlance(seconds: number): string {
  const s = Math.round(seconds);
  if (s <= 0) return 'Due now';
  if (s < 60) return 'Less than 1 min away';
  return `About ${Math.round(s / 60)} min away`;
}

/** "2 min 10 sec away"; a non-positive time reads as "due now". */
export function describeTimeAway(seconds: number): string {
  return Math.round(seconds) <= 0 ? 'due now' : `${formatSpokenDuration(seconds)} away`;
}

export function revisionDirectionWord(seconds: number): 'later' | 'earlier' | 'unchanged' {
  if (Math.round(seconds) > 0) return 'later';
  if (Math.round(seconds) < 0) return 'earlier';
  return 'unchanged';
}

export function formatPercent(probability: number): string {
  return `${Math.round(probability * 100)}%`;
}

// BART runs on Pacific time; format explicitly so output does not depend on the
// viewer's machine time zone.
const clockFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Los_Angeles',
  hour: 'numeric',
  minute: '2-digit',
  second: '2-digit',
  hour12: true,
});

const minuteFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Los_Angeles',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
});

/** "5:42:10 PM" (Pacific). */
export function formatClock(iso: string): string {
  return clockFormat.format(new Date(iso));
}

/**
 * Whether two clock times need seconds to be told apart: true when they differ but
 * read the same to the minute. It controls whether the exact calculation's clocks
 * (BART's current ETA and the likely final published ETA) show seconds, so a
 * sub-minute adjustment is never concealed by minute-only formatting. The large
 * glanceable forecast is always minute precision and does not use it.
 */
export function needsSeconds(a: string, b: string): boolean {
  return a !== b && formatClockMinute(a) === formatClockMinute(b);
}

/** "5:43 PM" (Pacific). Seconds are dropped, not rounded, as a station clock reads. */
export function formatClockMinute(iso: string): string {
  return minuteFormat.format(new Date(iso));
}
