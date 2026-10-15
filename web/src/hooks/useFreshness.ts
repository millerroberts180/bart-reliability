import { assessFreshness, type Freshness } from '../domain/eta';
import { usePredictionEnvironment } from '../data/PredictionClientContext';
import { useNow } from './useNow';

/** Freshness of a response's feed snapshot, re-evaluated as the clock ticks. */
export function useFreshness(feedTimestamp: string, receivedAt: Date): Freshness {
  const { now: clock } = usePredictionEnvironment();
  const tick = useNow(clock);
  return assessFreshness(feedTimestamp, tick > receivedAt ? tick : receivedAt);
}
