import { render, screen, waitFor, within } from '@testing-library/react';
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

// Most tests here read the scripted East Bay trains at Embarcadero, so they start there
// by URL, as a shared link would. The default group (platform 1) is tested on its own.
const EAST_BAY = '?station=EMBR&boarding=to-WOAK';

function renderExample(client: PredictionClient = new MockPredictionClient({ now: clock }), search = EAST_BAY) {
  window.history.replaceState(null, '', `/${search}`);
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
  it('selects the platform 1 group first by default, in the API’s order', async () => {
    renderExample(undefined, '');
    expect(await readoutHeading('Embarcadero · SF Airport train')).toBeInTheDocument();
    const ways = within(screen.getByRole('group', { name: 'Which way are you going?' })).getAllByRole('radio');
    expect(ways.map((r) => (r as HTMLInputElement).value)).toEqual(['to-MONT', 'to-WOAK']);
    expect(ways[0]).toBeChecked();
    expect(ways[0]).toHaveAccessibleName('Toward Daly City, SFO and Millbrae, Platform 1');
  });

  it('labels every control', async () => {
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    expect(screen.getByRole('button', { name: 'Change boarding station, currently Embarcadero' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Which way are you going?' })).toBeInTheDocument();
    const trains = screen.getByRole('group', { name: 'Upcoming trains' });
    expect(within(trains).getAllByRole('radio')).toHaveLength(4);
  });

  it('leads with the likely final published ETA, then a summary, then the calculation on request', async () => {
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

    // Visible at a glance: BART's ETA, the adjustment and stability, rounded like the forecast.
    expect(screen.getByTestId('summary-said')).toHaveTextContent('BART currently says10:01 AM · about 2 min away');
    expect(screen.getByTestId('summary-adjust')).toHaveTextContent('Expected adjustmentAbout 12 seconds later');
    expect(screen.getByTestId('summary-stability')).toHaveTextContent(
      'ETA stabilityLikely to hold · 8% chance BART changes this estimate by more than 60 seconds',
    );
    // The exact arithmetic is one press away, in a clearly labelled section.
    const calculation = screen.getByTestId('calculation');
    expect(calculation.tagName).toBe('DETAILS');
    expect(calculation).not.toHaveAttribute('open');
    expect(within(calculation).getByText('How the forecast is calculated').tagName).toBe('SUMMARY');
    expect(calculation).toContainElement(calc('now'));

    // Reading order: compact identity, forecast, summary, then the calculation.
    expect(follows(heading, forecast())).toBe(true);
    expect(follows(forecast(), screen.getByTestId('summary-said'))).toBe(true);
    expect(follows(screen.getByTestId('summary-stability'), calc('now'))).toBe(true);
    expect(follows(calc('now'), calc('adjust'))).toBe(true);
    expect(follows(calc('adjust'), calc('final'))).toBe(true);
    const panel = readout('Embarcadero · Antioch train');

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
    await user.click(screen.getByRole('radio', { name: 'Toward Daly City, SFO and Millbrae, Platform 1' }));
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
    expect(screen.getByTestId('summary-stability')).toHaveTextContent('May be revised · 41% chance');
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
    // One detailed explanation; the list itself stays terse.
    expect(within(screen.getByRole('group', { name: 'Upcoming trains' })).getByText('None listed')).toBeInTheDocument();
    // On screen, only the heading and its explanation say so (the other is the spoken announcement).
    const visible = screen.getAllByText(/no (upcoming )?trains/i).filter((el) => !el.closest('.visually-hidden'));
    expect(visible.map((el) => el.tagName)).toEqual(['H3', 'P']);
  });

  it('keeps the model details in a labelled section, with version and training date', async () => {
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    const details = screen.getByTestId('data-details');
    expect(details.tagName).toBe('DETAILS');
    expect(within(details).getByText('Data and model details').tagName).toBe('SUMMARY');
    expect(details).toHaveTextContent('Forecast generated9:59:30 AM');
    expect(details).toHaveTextContent('Version simulated-0.1, trained on data through Sun, Oct 11, 2026, 12:00 AM Pacific');
    expect(details).toHaveTextContent('Trip1561');
    // Not mixed into the commuter-facing result above it.
    expect(screen.getByTestId('forecast')).not.toHaveTextContent(/simulated-0\.1|Trip/);
    // Alerts stay visible: they can matter to a rider.
    expect(within(details).queryByText(/Service alerts/)).not.toBeInTheDocument();
  });
});

describe('a train without a model forecast', () => {
  const horizon = () => scenario('model-horizon');
  const trainRadios = () => within(screen.getByRole('group', { name: 'Upcoming trains' })).getAllByRole('radio');

  it('keeps the earliest train selected and offers the next model forecast explicitly', async () => {
    const user = userEvent.setup();
    renderExample(horizon());
    await readoutHeading('Embarcadero · Antioch train');
    // Never moved to a later train for the visitor.
    expect(trainRadios()[0]).toBeChecked();
    expect(screen.getByTestId('forecast')).toHaveTextContent(/^BART’s published ETA/);

    const view = screen.getByRole('button', { name: 'View the next model forecast' });
    expect(view).toHaveAccessibleDescription('Berryessa/North San José train, BART ETA 10:09 AM');
    await user.click(view);
    const heading = await readoutHeading('Embarcadero · Berryessa/North San José train');
    expect(trainRadios()[2]).toBeChecked();
    expect(screen.getByTestId('forecast')).toHaveTextContent(/^Likely final published ETA/);
    expect(screen.queryByRole('button', { name: /model forecast/ })).not.toBeInTheDocument();
    // The button is gone, so focus moves to the result it opened.
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it('offers an earlier forecast when none comes later', async () => {
    const user = userEvent.setup();
    renderExample(horizon());
    await chooseStation(user, 'Balboa Park');
    await readoutHeading(/^Balboa Park · /);
    await user.click(screen.getByRole('radio', { name: 'Toward the East Bay, Platform 2' }));
    await readoutHeading('Balboa Park · Berryessa/North San José train');
    await user.click(trainRadios()[2] as HTMLElement); // 820 s: no forecast, and none after it
    await readoutHeading('Balboa Park · Antioch train');
    await user.click(screen.getByRole('button', { name: 'View an earlier model forecast' }));
    expect(await readoutHeading('Balboa Park · Berryessa/North San José train')).toBeInTheDocument();
    expect(trainRadios()[0]).toBeChecked();
  });

  it('offers nothing when no train has a forecast', async () => {
    renderExample(scenario('eta-only'));
    await readoutHeading('Embarcadero · Antioch train');
    expect(screen.getByTestId('no-forecast')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /model forecast/ })).not.toBeInTheDocument();
  });
});
