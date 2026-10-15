import { assessFreshness, type Freshness } from '../domain/eta';
import type { ReplayInfo } from '../domain/types';
import { usePredictionEnvironment } from '../data/PredictionClientContext';
import { useNow } from './useNow';

/**
 * Freshness of a response's feed snapshot. Live and simulated data age with the clock;
 * a historical replay is judged at its replay time, which does not move, so recorded
 * data is never shown as going stale (or as current) by the visitor's clock.
 */
export function useFreshness(feedTimestamp: string, receivedAt: Date, replay: ReplayInfo | null = null): Freshness {
  const { now: clock } = usePredictionEnvironment();
  const tick = useNow(clock);
  if (replay) return assessFreshness(feedTimestamp, new Date(replay.asOf));
  return assessFreshness(feedTimestamp, tick > receivedAt ? tick : receivedAt);
}
