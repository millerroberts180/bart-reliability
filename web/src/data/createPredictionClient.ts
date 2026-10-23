import { HttpPredictionClient } from './HttpPredictionClient';
import {
  MockPredictionClient,
  type MockHistoryScenario,
  type MockNetwork,
  type MockScenario,
} from './MockPredictionClient';
import type { PredictionClient } from './PredictionClient';
import { StaticReplayClient } from './StaticReplayClient';

/**
 * "mock": simulated fixtures. "http": the local prediction API. "static": the historical
 * replay published with the site as static files (docs/static_replay.md).
 */
export type DataMode = 'mock' | 'http' | 'static';

/** Reads VITE_DATA_MODE; anything unrecognised falls back to simulated data. */
export function resolveDataMode(value: string | undefined): DataMode {
  return value === 'http' || value === 'static' ? value : 'mock';
}

export interface ClientOptions {
  mode: DataMode;
  apiBaseUrl?: string;
  /** Static mode: URL path of the published replay, e.g. "/bart-reliability/replay/". */
  staticReplayRoot?: string;
  scenario?: MockScenario;
  historyScenario?: MockHistoryScenario;
  network?: MockNetwork;
  now?: () => Date;
  latencyMs?: number;
}

export function createPredictionClient({
  mode,
  apiBaseUrl = '',
  staticReplayRoot = '/replay/',
  scenario,
  historyScenario,
  network,
  now,
  latencyMs,
}: ClientOptions): PredictionClient {
  if (mode === 'http') return new HttpPredictionClient(apiBaseUrl);
  if (mode === 'static') return new StaticReplayClient(staticReplayRoot);
  return new MockPredictionClient({
    ...(scenario && { scenario }),
    ...(historyScenario && { historyScenario }),
    ...(network && { network }),
    ...(now && { now }),
    ...(latencyMs !== undefined && { latencyMs }),
  });
}
