import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MockPredictionClient, type MockScenario } from '../data/MockPredictionClient';
import type { PredictionClient } from '../data/PredictionClient';
import { PredictionClientProvider } from '../data/PredictionClientContext';
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
const step = (id: 'now' | 'change' | 'final') => screen.getByTestId(`step-${id}`);

describe('PredictionExample', () => {
  it('labels every control', async () => {
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    expect(screen.getByRole('combobox', { name: 'Station' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Direction' })).toBeInTheDocument();
    const trains = screen.getByRole('group', { name: 'Upcoming trains' });
    expect(within(trains).getAllByRole('radio')).toHaveLength(4);
  });

  it('shows what BART says, the expected change and the likely final published ETA, in that order', async () => {
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    // Snapshot 9:59:26 AM; BART's ETA is 130 s later, the model expects +12 s.
    expect(step('now')).toHaveTextContent('BART says now10:01:36 AM2 min 10 sec away');
    expect(step('change')).toHaveTextContent('Expected change to BART’s ETAAbout 12 seconds later');
    expect(step('change')).toHaveTextContent('Likely range (80%): 10 seconds earlier to 35 seconds later');
    expect(step('final')).toHaveTextContent('Likely final published ETA10:01:48 AMAbout 2 min 22 sec away');
    expect(step('now').compareDocumentPosition(step('change')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(step('change').compareDocumentPosition(step('final')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    const panel = readout('Embarcadero · Antioch train');
    expect(panel).toHaveTextContent(
      '2 min 10 sec current published ETA + 12 seconds predicted revision = 2 min 22 sec likely final published ETA',
    );
    expect(within(panel).getByText(/It is not an observed arrival time/)).toBeInTheDocument();
    expect(within(panel).getByText('Simulated')).toBeInTheDocument();
    expect(within(panel).getByText('Likely to hold')).toBeInTheDocument();
  });

  it('shows different clock times for a revision of under a minute', async () => {
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    // A 12-second revision within the same minute must still read as a change.
    const nowClock = step('now').querySelector('.result__clock')?.textContent;
    const finalClock = step('final').querySelector('.result__clock')?.textContent;
    expect(nowClock).toBe('10:01:36 AM');
    expect(finalClock).toBe('10:01:48 AM');
    // The screen-reader summary carries the same precision.
    expect(readout('Embarcadero · Antioch train')).toHaveTextContent(
      'BART says 10:01:36 AM, 2 min 10 sec away. Expected change: about 12 seconds later. ' +
        'Likely final published ETA: 10:01:48 AM, about 2 min 22 sec away.',
    );
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
    await user.selectOptions(screen.getByRole('combobox', { name: 'Station' }), 'MacArthur');
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
    expect(step('now')).toHaveTextContent('10:05:36 AM6 min 10 sec away');
    expect(step('change')).toHaveTextContent('About 1 min 25 sec later');
    expect(step('change')).toHaveTextContent('20 seconds to 2 min 30 sec later');
    expect(step('final')).toHaveTextContent('10:07:01 AMAbout 7 min 35 sec away');
    expect(step('final')).toHaveTextContent('Likely range (80%): 6 min 30 sec to 8 min 40 sec away');
    const panel = readout('Embarcadero · Richmond train');
    expect(within(panel).getByText('May be revised')).toBeInTheDocument();
    expect(within(panel).getByText('41%')).toBeInTheDocument();
  });

  it('words an earlier revision as earlier', async () => {
    const user = userEvent.setup();
    renderExample();
    await readoutHeading('Embarcadero · Antioch train');
    await user.click(screen.getByRole('radio', { name: /Dublin\/Pleasanton/ }));
    await readoutHeading('Embarcadero · Dublin/Pleasanton train');
    expect(step('change')).toHaveTextContent('About 40 seconds earlier');
    expect(step('change')).toHaveTextContent('2 min 10 sec earlier to 50 seconds later');
    expect(step('final')).toHaveTextContent('About 14 min 25 sec away');
  });

  it('shows a loading state while the request is pending', async () => {
    renderExample(scenario('loading'));
    expect(await readoutHeading('Loading prediction…')).toBeInTheDocument();
    expect(screen.queryByTestId('step-final')).not.toBeInTheDocument();
  });

  it('warns when the feed snapshot is stale', async () => {
    renderExample(scenario('stale'));
    await readoutHeading('Embarcadero · Antioch train');
    expect(screen.getByRole('status')).toHaveTextContent(
      /Stale data\. This snapshot is from 9:50 AM, 9 min 40 sec ago.*BART may already have revised/,
    );
    // The current ETA is described in the past tense once its snapshot is stale.
    expect(step('now')).toHaveTextContent('BART said at 9:50 AM');
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
