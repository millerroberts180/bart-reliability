import type { StabilityClass } from '../domain/types';

// A small trace of an ETA over time: flat (holds), one step (may move), two
// steps (likely moves). Always paired with a text label; never the only cue.
const PATHS: Record<StabilityClass, string> = {
  likely_to_hold: 'M1 6 H21',
  may_be_revised: 'M1 9 H9 V3 H21',
  likely_to_be_revised: 'M1 10 H7 V6 H13 V2 H21',
};

export function StabilityMark({ stability }: { stability: StabilityClass }) {
  return (
    <svg className="stability-mark" viewBox="0 0 22 12" width="22" height="12" aria-hidden="true" focusable="false">
      <path d={PATHS[stability]} />
    </svg>
  );
}
