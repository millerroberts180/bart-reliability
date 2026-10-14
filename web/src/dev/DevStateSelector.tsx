import './dev-panel.css';
import { MOCK_SCENARIOS, type MockScenario } from '../data/MockPredictionClient';

const LABELS: Record<MockScenario, string> = {
  live: 'Success',
  loading: 'Loading',
  error: 'Request failure',
  stale: 'Stale data',
  empty: 'No upcoming trains',
};

/** Development-only control for reviewing each interface state. Not shipped. */
export default function DevStateSelector({
  scenario,
  onChange,
}: {
  scenario: MockScenario;
  onChange: (scenario: MockScenario) => void;
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
    </details>
  );
}
