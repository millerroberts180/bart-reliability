// Words for the three ETAs and their differences (docs/showcase_replay.md). Revisions
// are changes to BART's published ETA: "ETA moved later", never anything about the train.

import { formatSpokenDuration, revisionDirectionWord } from './eta';
import type { Horizon } from './showcase';

export const TERMS = {
  bart: 'BART published ETA',
  adjusted: 'Model-adjusted ETA',
  final: 'BART later published',
} as const;

export const RETROSPECTIVE_NOTE = 'Retrospective: BART published this after the replay moment. The model did not know it.';

/** "Expected to move about 1 min later", "Expected to stay the same". */
export function describeExpected(seconds: number): string {
  const d = revisionDirectionWord(seconds);
  return d === 'unchanged' ? 'Expected to stay the same' : `Expected to move about ${formatSpokenDuration(seconds)} ${d}`;
}

/** "ETA moved about 1 min 18 sec later", "ETA did not move". */
export function describeMoved(seconds: number): string {
  const d = revisionDirectionWord(seconds);
  return d === 'unchanged' ? 'ETA did not move' : `ETA moved about ${formatSpokenDuration(seconds)} ${d}`;
}

/** A change to BART's ETA in a phrase: "about 1 min 18 sec later", "no change". */
export function describeChange(seconds: number): string {
  const d = revisionDirectionWord(seconds);
  return d === 'unchanged' ? 'no change' : `about ${formatSpokenDuration(seconds)} ${d}`;
}

/** How the model-adjusted ETA compared with what BART later published. */
export function describeModelError(errorSeconds: number): string {
  if (Math.round(errorSeconds) === 0) return 'The model-adjusted ETA matched what BART later published.';
  const relation = errorSeconds < 0 ? 'earlier' : 'later';
  return `The model-adjusted ETA was ${formatSpokenDuration(errorSeconds)} ${relation} than what BART later published.`;
}

export function describeDirectionMatch(match: boolean): string {
  return match ? 'Direction matched' : 'Direction differed';
}

export const HORIZON_LABELS: Record<Horizon, string> = {
  '300': '5 minutes',
  '600': '10 minutes',
  '900': '15 minutes',
};

export const HORIZON_ADJECTIVE: Record<Horizon, string> = {
  '300': '5-minute',
  '600': '10-minute',
  '900': '15-minute',
};

export const HORIZON_SHORT: Record<Horizon, string> = {
  '300': '5 min',
  '600': '10 min',
  '900': '15 min',
};

/** A station name's first part, for tight labels ("12th Street / Oakland City Center" -> "12th Street"). */
export function shortStationName(name: string): string {
  return name.split(' / ')[0] ?? name;
}
