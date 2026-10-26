// The page for VITE_DATA_MODE=mock (the default): simulated fixtures, with the
// development-only state selector. vite.config.ts points '@data-mode' here for this mode
// only, so this build contains no other prediction client and no replay data.

import { lazy, Suspense, useMemo, useState } from 'react';
import { App } from '../App';
import {
  MockPredictionClient,
  type MockHistoryScenario,
  type MockNetwork,
  type MockScenario,
} from '../data/MockPredictionClient';

// Loaded only in development; the dynamic import is dropped from production builds.
const DevStateSelector = import.meta.env.DEV ? lazy(() => import('../dev/DevStateSelector')) : null;

const SIMULATED_LATENCY_MS = 350;

export function Site() {
  const [scenario, setScenario] = useState<MockScenario>('live');
  const [historyScenario, setHistoryScenario] = useState<MockHistoryScenario>('normal');
  const [network, setNetwork] = useState<MockNetwork>('demo');
  const client = useMemo(
    () => new MockPredictionClient({ scenario, historyScenario, network, latencyMs: SIMULATED_LATENCY_MS }),
    [scenario, historyScenario, network],
  );

  return (
    <>
      <App client={client} />
      {DevStateSelector && (
        <Suspense fallback={null}>
          <DevStateSelector
            scenario={scenario}
            historyScenario={historyScenario}
            network={network}
            onNetworkChange={setNetwork}
            onChange={setScenario}
            onHistoryChange={setHistoryScenario}
          />
        </Suspense>
      )}
    </>
  );
}
