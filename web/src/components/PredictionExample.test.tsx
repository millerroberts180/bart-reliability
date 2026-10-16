import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MockPredictionClient, type MockScenario } from '../data/MockPredictionClient';
import type { PredictionClient } from '../data/PredictionClient';
import { PredictionClientProvider } from '../data/PredictionClientContext';
import { chooseStation } from '../test/picker';
import { PredictionExample } from './PredictionExample';

// 17:00:00Z is 10:00 AM Pacific; the live fixture snapshot is 34 s earlier.
const NOW = new Date('2026-10-13T17:00:00Z');
const clock = () => NOW;

function renderExample(client: PredictionClient = new MockPredictionClient({ now: clock })) {
  render(
    <PredictionClientProvider client={client} now={clock}>
      <PredictionExample />
    </PredictionClientProvider>,
  );
}

const scenario = (s: MockScenario) => new MockPredictionClient({ scenario: s, now: clock });
const readoutHeading = (name: string | RegExp) => screen.findByRole('heading', { level: 3, name });
const readout = (name: string) => screen.getByRole('region', { name });
const forecast = () => screen.getByTestId('forecast');
const calc = (id: 'now' | 'adjust' | 'final') => screen.getByTestId(`calc-${id}`);
const follows = (a: Element, b: Element) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

describe('PredictionExample', () => {
  it('labels every control', async () => {
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    expect(screen.getByRole('button', { name: 'Change boarding station, currently Embarcadero' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Direction' })).toBeInTheDocument();
    const trains = screen.getByRole('group', { name: 'Upcoming trains' });
    expect(within(trains).getAllByRole('radio')).toHaveLength(4);
  });

  it('leads with the likely final published ETA, then the calculation beneath it', async () => {
    renderExample();
    const heading = await readoutHeading('Embarcadero · Antioch train');
    // Snapshot 9:59:26 AM; BART's ETA is 130 s later, the model expects 12 s later.
    expect(forecast()).toHaveTextContent(
      'Likely final published ETA10:01 AMAbout 2 min away80% likely range: 2 min to 2 min 45 sec away' +
        'Model forecast of BART’s last published ETA, not an observed arrival.',
    );
    expect(calc('now')).toHaveTextContent('BART currently says10:01:36 AM · 2 min 10 sec away');
    expect(calc('adjust')).toHaveTextContent('Expected adjustmentAbout 12 seconds later');
    expect(calc('final')).toHaveTextContent('Likely final published ETA10:01:48 AM · about 2 min 22 sec away');

    // Reading order: compact identity, forecast, calculation, then supporting detail.
    expect(follows(heading, forecast())).toBe(true);
    expect(follows(forecast(), calc('now'))).toBe(true);
    expect(follows(calc('now'), calc('adjust'))).toBe(true);
    expect(follows(calc('adjust'), calc('final'))).toBe(true);
    const panel = readout('Embarcadero · Antioch train');
    expect(follows(calc('final'), within(panel).getByText('Likely to hold'))).toBe(true);

    expect(within(panel).getByText(/It is not an observed arrival time/)).toBeInTheDocument();
    expect(within(panel).getByText('Simulated')).toBeInTheDocument();
    expect(within(panel).getByText(/Adjustment range \(80%\)/).parentElement).toHaveTextContent(
      '10 seconds earlier to 35 seconds later',
    );
  });

  it('shows the route as text with a cased colour cue that carries no extra meaning', async () => {
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    const tag = within(readout('Embarcadero · Antioch train')).getByText('Yellow line');
    expect(tag.querySelector('.route-tag__swatch')).toHaveAttribute('aria-hidden', 'true');
    expect((tag.closest('.result-block') as HTMLElement).style.getPropertyValue('--route')).toBe('#ffff33');
  });

  it('keeps the glance at minute precision and the exact seconds in the calculation (same minute)', async () => {
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    // 12 seconds later, within one minute: the glance reads 10:01 AM; the calculation keeps the seconds.
    expect(forecast().querySelector('.clock')?.textContent).toBe('10:01 AM');
    expect(forecast()).toHaveTextContent('About 2 min away');
    expect(forecast()).not.toHaveTextContent('10:01:48');
    expect(calc('now')).toHaveTextContent('BART currently says10:01:36 AM · 2 min 10 sec away');
    expect(calc('adjust')).toHaveTextContent('Expected adjustmentAbout 12 seconds later');
    expect(calc('final')).toHaveTextContent('Likely final published ETA10:01:48 AM · about 2 min 22 sec away');
    // Screen readers hear the glance first, then the exact calculation, with no conflicting values.
    expect(readout('Embarcadero · Antioch train')).toHaveTextContent(
      'Embarcadero, Antioch train. Likely final published ETA: 10:01 AM, about 2 min away. ' +
        'Exact calculation: BART currently says 10:01:36 AM, 2 min 10 sec away; expected adjustment about 12 seconds later; ' +
        'likely final published ETA 10:01:48 AM, about 2 min 22 sec away.',
    );
  });

  it('uses minutes in the calculation when the adjustment crosses into another minute (later)', async () => {
    const user = userEvent.setup();
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    await user.click(within(screen.getByRole('group', { name: 'Upcoming trains' })).getByRole('radio', { name: /Richmond/ }));
    await readoutHeading('Embarcadero · Richmond train');
    // 6 min 10 sec + 1 min 25 sec later = 7 min 35 sec, which rounds to 8 min for the glance.
    expect(forecast().querySelector('.clock')?.textContent).toBe('10:07 AM');
    expect(forecast()).toHaveTextContent('About 8 min away');
    expect(calc('now')).toHaveTextContent('10:05 AM · 6 min 10 sec away');
    expect(calc('adjust')).toHaveTextContent('About 1 min 25 sec later');
    expect(calc('final')).toHaveTextContent('10:07 AM · about 7 min 35 sec away');
  });

  it('says “Less than 1 min away” when the forecast is under a minute away', async () => {
    const mock = new MockPredictionClient({ now: clock });
    // Test-only stub: the first train 40 s away, adjusted 12 s later (52 s in all).
    const nearby: PredictionClient = {
      source: 'simulated',
      listStations: (signal) => mock.listStations(signal),
      getPredictionHistory: (id, signal) => mock.getPredictionHistory(id, signal),
      getModelMetadata: (signal) => mock.getModelMetadata(signal),
      getHealth: (signal) => mock.getHealth(signal),
      getPredictions: async (stationId, directionId, signal) => {
        const response = await mock.getPredictions(stationId, directionId, signal);
        const [first, ...rest] = response.trains;
        if (!first) return response;
        const currentEtaAt = new Date(Date.parse(response.feedTimestamp) + 40_000).toISOString();
        return { ...response, trains: [{ ...first, currentEtaSeconds: 40, currentEtaAt }, ...rest] };
      },
    };
    renderExample(nearby);
    await readoutHeading('Embarcadero · Antioch train');
    expect(forecast()).toHaveTextContent('Less than 1 min away');
    expect(calc('now')).toHaveTextContent('40 seconds away');
    expect(calc('final')).toHaveTextContent('about 52 seconds away');
  });

  it('names the station, destination and direction in the result heading', async () => {
    renderExample();
    const heading = await readoutHeading('Embarcadero · Antioch train');
    expect(heading.nextElementSibling).toHaveTextContent('Toward the East Bay');
  });

  it('updates when the station changes', async () => {
    const user = userEvent.setup();
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    await chooseStation(user, 'MacArthur');
    expect(await readoutHeading('MacArthur · Richmond train')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Toward Antioch and Richmond' })).toBeChecked();
    expect(screen.getByText(/elevator out of service/)).toBeInTheDocument();
  });

  it('updates when the direction changes', async () => {
    const user = userEvent.setup();
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    await user.click(screen.getByRole('radio', { name: 'Toward Daly City, SFO and Millbrae' }));
    expect(await readoutHeading('Embarcadero · SF Airport train')).toBeInTheDocument();
  });

  it('updates when another train is selected', async () => {
    const user = userEvent.setup();
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    const trains = screen.getByRole('group', { name: 'Upcoming trains' });
    await user.click(within(trains).getByRole('radio', { name: /Richmond/ }));
    expect(await readoutHeading('Embarcadero · Richmond train')).toBeInTheDocument();
    // 6 min 10 s + 1 min 25 s; the 80% range +20 s … +2 min 30 s carries through the same sum.
    expect(forecast()).toHaveTextContent('10:07 AMAbout 8 min away80% likely range: 6 min 30 sec to 8 min 40 sec away');
    expect(calc('adjust')).toHaveTextContent('About 1 min 25 sec later');
    const panel = readout('Embarcadero · Richmond train');
    expect(within(panel).getByText(/Adjustment range/).parentElement).toHaveTextContent('20 seconds to 2 min 30 sec later');
    expect(within(panel).getByText('May be revised')).toBeInTheDocument();
    expect(within(panel).getByText('41%')).toBeInTheDocument();
    expect(within(panel).getByText('Red line')).toBeInTheDocument();
  });

  it('words an earlier revision as earlier', async () => {
    const user = userEvent.setup();
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    await user.click(screen.getByRole('radio', { name: /Dublin\/Pleasanton/ }));
    await readoutHeading('Embarcadero · Dublin/Pleasanton train');
    expect(calc('adjust')).toHaveTextContent('About 40 seconds earlier');
    // 15 min 5 sec − 40 sec = 14 min 25 sec, which rounds to 14 min for the glance.
    expect(forecast()).toHaveTextContent('10:13 AMAbout 14 min away');
    expect(calc('now')).toHaveTextContent('10:14 AM · 15 min 5 sec away');
    expect(calc('final')).toHaveTextContent('10:13 AM · about 14 min 25 sec away');
    expect(within(readout('Embarcadero · Dublin/Pleasanton train')).getByText(/Adjustment range/).parentElement).toHaveTextContent(
      '2 min 10 sec earlier to 50 seconds later',
    );
  });

  it('shows a loading state while the request is pending', async () => {
    renderExample(scenario('loading'));
    expect(await readoutHeading('Loading prediction…')).toBeInTheDocument();
    expect(screen.queryByTestId('forecast')).not.toBeInTheDocument();
  });

  it('warns when the feed snapshot is stale', async () => {
    renderExample(scenario('stale'));
    await readoutHeading('Embarcadero · Antioch train');
    expect(screen.getByRole('status')).toHaveTextContent(
      /Stale data\. This snapshot is from 9:50 AM, 9 min 40 sec ago.*BART may already have revised/,
    );
    // The current ETA is described in the past tense once its snapshot is stale.
    expect(calc('now')).toHaveTextContent('BART said at 9:50 AM');
    expect(screen.getByText('Stale')).toBeInTheDocument();
  });

  it('marks a fresh snapshot as current', async () => {
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    expect(screen.getByText('Current')).toBeInTheDocument();
    expect(screen.queryByText(/Stale data/)).not.toBeInTheDocument();
  });

  it('explains a request failure and recovers on retry', async () => {
    const user = userEvent.setup();
    const mock = new MockPredictionClient({ now: clock });
    let failures = 1;
    const flaky: PredictionClient = {
      source: 'simulated',
      listStations: (signal) => mock.listStations(signal),
      getPredictionHistory: (id, signal) => mock.getPredictionHistory(id, signal),
      getModelMetadata: (signal) => mock.getModelMetadata(signal),
      getHealth: (signal) => mock.getHealth(signal),
      getPredictions: (stationId, directionId, signal) =>
        failures-- > 0 ? Promise.reject(new Error('offline')) : mock.getPredictions(stationId, directionId, signal),
    };
    renderExample(flaky);

    expect(await readoutHeading('Prediction unavailable')).toBeInTheDocument();
    expect(screen.getByText(/No estimate is shown/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await readoutHeading('Embarcadero · Antioch train')).toBeInTheDocument();
  });

  it('explains when no trains are listed', async () => {
    renderExample(scenario('empty'));
    expect(await readoutHeading('No upcoming trains')).toBeInTheDocument();
    expect(screen.getByText(/lists no trains toward the East Bay from Embarcadero/)).toBeInTheDocument();
    expect(screen.getByText('No trains listed in this snapshot.')).toBeInTheDocument();
  });
});
