import './dev-panel.css';
import {
  MOCK_HISTORY_SCENARIOS,
  MOCK_SCENARIOS,
  type MockHistoryScenario,
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
};

const HISTORY_LABELS: Record<MockHistoryScenario, string> = {
  normal: 'As scripted',
  loading: 'Loading',
  error: 'Request failure',
  single: 'One observation',
  none: 'No history',
  gaps: 'Gaps',
};

/** Development-only control for reviewing each interface state. Not shipped. */
export default function DevStateSelector({
  scenario,
  historyScenario,
  onChange,
  onHistoryChange,
}: {
  scenario: MockScenario;
  historyScenario: MockHistoryScenario;
  onChange: (scenario: MockScenario) => void;
  onHistoryChange: (scenario: MockHistoryScenario) => void;
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
    </details>
  );
}
