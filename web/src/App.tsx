import { lazy, Suspense, useMemo, useState } from 'react';
import { Opening } from './components/Opening';
import { PredictionExample } from './components/PredictionExample';
import { SiteFooter } from './components/SiteFooter';
import { SiteHeader } from './components/SiteHeader';
import { createPredictionClient, resolveDataMode } from './data/createPredictionClient';
import type { MockHistoryScenario, MockScenario } from './data/MockPredictionClient';
import type { PredictionClient } from './data/PredictionClient';
import { PredictionClientProvider } from './data/PredictionClientContext';

// Loaded only in development; the dynamic import is dropped from production builds.
const DevStateSelector = import.meta.env.DEV ? lazy(() => import('./dev/DevStateSelector')) : null;

const DATA_MODE = resolveDataMode(import.meta.env.VITE_DATA_MODE);
const SIMULATED_LATENCY_MS = 350;

export function App({ client: injectedClient }: { client?: PredictionClient }) {
  const [scenario, setScenario] = useState<MockScenario>('live');
  const [historyScenario, setHistoryScenario] = useState<MockHistoryScenario>('normal');
  const client = useMemo(
    () =>
      injectedClient ??
      createPredictionClient({
        mode: DATA_MODE,
        apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? '',
        scenario,
        historyScenario,
        latencyMs: SIMULATED_LATENCY_MS,
      }),
    [injectedClient, scenario, historyScenario],
  );

  return (
    <PredictionClientProvider client={client}>
      <SiteHeader />
      <main id="top" className="page">
        <Opening />
        <PredictionExample />
      </main>
      <SiteFooter />
      {DevStateSelector && DATA_MODE === 'mock' && !injectedClient && (
        <Suspense fallback={null}>
          <DevStateSelector
            scenario={scenario}
            historyScenario={historyScenario}
            onChange={setScenario}
            onHistoryChange={setHistoryScenario}
          />
        </Suspense>
      )}
    </PredictionClientProvider>
  );
}
