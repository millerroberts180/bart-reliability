// Simulated trains and histories for the full-network fixture. Destinations and lines
// follow each station's real service pattern (network.ts); every number is generated
// deterministically from the station, direction and position, so reloads match.

import { NETWORK_SERVICE } from './network';
import type { SimulatedHistory, SimulatedTrain } from './simulated';

/** Upcoming trains listed per station and direction in the full network. */
export const NETWORK_TRAIN_COUNT = 20;

/** FNV-1a: a small, stable string hash. */
function hash(text: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h;
}

const CAR_COUNTS = [8, 9, 10, null] as const;

/** Undefined when the station has no service in that direction. */
export function networkTrains(stationId: string, directionId: string): SimulatedTrain[] | undefined {
  const service = NETWORK_SERVICE[`${stationId}:${directionId}`];
  if (!service) return undefined;
  const fallback = service[0];
  if (!fallback) return undefined;
  return Array.from({ length: NETWORK_TRAIN_COUNT }, (_, i) => {
    const pattern = service[i % service.length] ?? fallback;
    const h = hash(`${stationId}:${directionId}:${i}`);
    const revision = Math.round((((h >>> 3) % 241) - 60) / 5) * 5; // −60 … +180 s
    const spread = 20 + ((h >>> 9) % 90);
    return {
      tripId: String(4000 + i * 10 + (h % 10)),
      lineName: pattern.lineName,
      headsign: pattern.headsign,
      carCount: CAR_COUNTS[h % CAR_COUNTS.length] ?? null,
      // About every 2¾ minutes, in order, so the list stays chronological.
      etaSeconds: 75 + i * 165 + ((h >>> 5) % 60),
      revisionSeconds: revision,
      interval: [revision - spread, revision + spread] as const,
      probability: Math.round(Math.min(0.9, 0.04 + Math.abs(revision) / 260 + ((h >>> 13) % 20) / 100) * 100) / 100,
    };
  });
}

/** A deterministic history script for a full-network prediction. */
export function networkHistory(predictionId: string): SimulatedHistory {
  const h = hash(predictionId);
  switch (h % 3) {
    case 0:
      return { snapshots: 15, steps: [] };
    case 1:
      return { snapshots: 15, steps: [[9, 45]] };
    default:
      return { snapshots: 15, steps: [[11, 30], [4, -35]] };
  }
}
