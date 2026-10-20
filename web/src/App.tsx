import { lazy, Suspense, useMemo, useState } from 'react';
import { Opening } from './components/Opening';
import { PredictionExample } from './components/PredictionExample';
import { ProjectQuestion } from './components/ProjectQuestion';
import { SiteFooter } from './components/SiteFooter';
import { SiteHeader } from './components/SiteHeader';
import { createPredictionClient, resolveDataMode } from './data/createPredictionClient';
import type { MockHistoryScenario, MockNetwork, MockScenario } from './data/MockPredictionClient';
import type { PredictionClient } from './data/PredictionClient';
import { PredictionClientProvider } from './data/PredictionClientContext';

// Loaded only in development; the dynamic import is dropped from production builds.
const DevStateSelector = import.meta.env.DEV ? lazy(() => import('./dev/DevStateSelector')) : null;

const DATA_MODE = resolveDataMode(import.meta.env.VITE_DATA_MODE);
// Read only in HTTP mode, so a simulated build never carries a local API address.
const API_BASE_URL = import.meta.env.VITE_DATA_MODE === 'http' ? (import.meta.env.VITE_API_BASE_URL ?? '') : '';
const SIMULATED_LATENCY_MS = 350;

export function App({ client: injectedClient }: { client?: PredictionClient }) {
  const [scenario, setScenario] = useState<MockScenario>('live');
  const [historyScenario, setHistoryScenario] = useState<MockHistoryScenario>('normal');
  const [network, setNetwork] = useState<MockNetwork>('demo');
  const client = useMemo(
    () =>
      injectedClient ??
      createPredictionClient({
        mode: DATA_MODE,
        apiBaseUrl: API_BASE_URL,
        scenario,
        historyScenario,
        network,
        latencyMs: SIMULATED_LATENCY_MS,
      }),
    [injectedClient, scenario, historyScenario, network],
  );

  return (
    <PredictionClientProvider client={client}>
      <SiteHeader />
      <main id="top" className="page">
        <Opening />
        <PredictionExample />
        <ProjectQuestion />
      </main>
      <SiteFooter />
      {DevStateSelector && DATA_MODE === 'mock' && !injectedClient && (
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
    </PredictionClientProvider>
  );
}
