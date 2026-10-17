import './dev-panel.css';
import {
  MOCK_HISTORY_SCENARIOS,
  MOCK_NETWORKS,
  MOCK_SCENARIOS,
  type MockHistoryScenario,
  type MockNetwork,
  type MockScenario,
} from '../data/MockPredictionClient';

const LABELS: Record<MockScenario, string> = {
  live: 'Success',
  loading: 'Loading',
  error: 'Request failure',
  stale: 'Stale data',
  empty: 'No upcoming trains',
  'no-interval': 'No likely range',
  'eta-only': 'BART ETA only',
  'model-horizon': 'Forecasts only near 5, 10, 15 min',
};

const HISTORY_LABELS: Record<MockHistoryScenario, string> = {
  normal: 'As scripted',
  loading: 'Loading',
  error: 'Request failure',
  single: 'One observation',
  none: 'No history',
  gaps: 'Gaps',
};

const NETWORK_LABELS: Record<MockNetwork, string> = {
  demo: 'Demo (3 stations)',
  full: 'Full network (50 stations, 20 trains)',
};

/** Development-only control for reviewing each interface state. Not shipped. */
export default function DevStateSelector({
  scenario,
  historyScenario,
  network,
  onChange,
  onHistoryChange,
  onNetworkChange,
}: {
  scenario: MockScenario;
  historyScenario: MockHistoryScenario;
  network: MockNetwork;
  onChange: (scenario: MockScenario) => void;
  onHistoryChange: (scenario: MockHistoryScenario) => void;
  onNetworkChange: (network: MockNetwork) => void;
}) {
  return (
    <details className="dev-panel">
      <summary>Dev · preview state</summary>
      <fieldset>
        <legend>Mock response</legend>
        {MOCK_SCENARIOS.map((s) => (
          <label key={s}>
            <input type="radio" name="dev-scenario" checked={s === scenario} onChange={() => onChange(s)} />
            {LABELS[s]}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>History response</legend>
        {MOCK_HISTORY_SCENARIOS.map((s) => (
          <label key={s}>
            <input
              type="radio"
              name="dev-history-scenario"
              checked={s === historyScenario}
              onChange={() => onHistoryChange(s)}
            />
            {HISTORY_LABELS[s]}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Station set</legend>
        {MOCK_NETWORKS.map((n) => (
          <label key={n}>
            <input type="radio" name="dev-network" checked={n === network} onChange={() => onNetworkChange(n)} />
            {NETWORK_LABELS[n]}
          </label>
        ))}
      </fieldset>
    </details>
  );
}
