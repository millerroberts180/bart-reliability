import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MockPredictionClient, type MockHistoryScenario, type MockScenario } from '../data/MockPredictionClient';
import { PredictionClientProvider } from '../data/PredictionClientContext';
import { chooseStation } from '../test/picker';
import { PredictionExample } from './PredictionExample';

// 17:00:00Z is 10:00 AM Pacific; the live snapshot is 9:59:26 AM, the stale one 9:50:20 AM.
const NOW = new Date('2026-10-13T17:00:00Z');
const clock = () => NOW;

function renderExample({ scenario, historyScenario }: { scenario?: MockScenario; historyScenario?: MockHistoryScenario } = {}) {
  const client = new MockPredictionClient({ now: clock, ...(scenario && { scenario }), ...(historyScenario && { historyScenario }) });
  render(
    <PredictionClientProvider client={client} now={clock}>
      <PredictionExample />
    </PredictionClientProvider>,
  );
}

const history = () => screen.getByRole('region', { name: 'How this ETA has changed' });
const summary = () => screen.findByTestId('history-summary');
const selectTrain = async (user: ReturnType<typeof userEvent.setup>, name: RegExp) =>
  user.click(within(screen.getByRole('group', { name: 'Upcoming trains' })).getByRole('radio', { name }));

describe('ETA history', () => {
  it('summarises the selected train and stays in step with the selection', async () => {
    const user = userEvent.setup();
    renderExample();
    expect(await summary()).toHaveTextContent('Over the last 14 minutes, BART’s ETA for this train held steady.');
    expect(history()).toHaveTextContent('Embarcadero · Antioch train');

    await selectTrain(user, /Richmond/);
    await screen.findByText(/moved this ETA 2 min 5 sec later across three changes of 30 seconds or more/);
    expect(history()).toHaveTextContent('Embarcadero · Richmond train');
    expect(screen.getByRole('heading', { level: 3, name: 'Embarcadero · Richmond train' })).toBeInTheDocument();
    expect(within(history()).getByRole('group', { name: /Embarcadero · Richmond train/ })).toBeInTheDocument();

    await selectTrain(user, /Dublin\/Pleasanton/);
    expect(
      await screen.findByText(/moved this ETA 1 min 15 sec earlier across two changes of 30 seconds or more/),
    ).toBeInTheDocument();
  });

  it('follows station and direction changes', async () => {
    const user = userEvent.setup();
    renderExample();
    await summary();
    await user.click(screen.getByRole('radio', { name: 'Toward Daly City, SFO and Millbrae' }));
    await selectTrain(user, /Daly City/);
    expect(await screen.findByText(/changed this ETA twice by 30 seconds or more, but it ended where it started/)).toBeInTheDocument();
    await chooseStation(user, 'Balboa Park');
    await selectTrain(user, /Antioch/);
    expect(await screen.findByText(/Only one snapshot so far/)).toBeInTheDocument();
  });

  it('exposes every observation’s values to keyboard and screen-reader users', async () => {
    const user = userEvent.setup();
    renderExample();
    await summary();
    await selectTrain(user, /Richmond/);
    await screen.findByText(/across three changes of 30 seconds or more/);

    const points = within(history()).getAllByRole('img');
    expect(points).toHaveLength(15);
    const latest = points.at(-1) as HTMLElement;
    expect(latest).toHaveAccessibleName(
      'Latest snapshot 9:59:26 AM: BART published 10:05:36 AM, 6 min 10 sec away, unchanged from the previous snapshot.',
    );
    // One tab stop for the whole chart; arrow keys move between snapshots.
    expect(points.filter((p) => p.getAttribute('tabindex') === '0')).toEqual([latest]);
    latest.focus();
    await user.keyboard('{ArrowLeft}{ArrowLeft}{ArrowLeft}');
    expect(points[11]).toHaveFocus();
    expect(screen.getByTestId('history-inspect')).toHaveTextContent(
      'Snapshot 9:56:26 AM BART published 10:05:36 AM, 9 min 10 sec away, 50 seconds later than the previous snapshot.',
    );
    await user.keyboard('{Home}');
    expect(points[0]).toHaveFocus();

    const table = within(history()).getByRole('table');
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(16); // header + 15 observations
    expect(rows[12]).toHaveTextContent('9:56:26 AM10:05:36 AM9 min 10 sec50 seconds later than the previous snapshot');
  });

  it('describes a gap without counting it as a change, in the summary and the table', async () => {
    renderExample({ historyScenario: 'gaps' });
    expect(await summary()).toHaveTextContent(
      'From the first to the latest available snapshot, the ETA ended where it started. ' +
        'No change was observed outside one gap; changes during the gap are unknown.',
    );
    expect(within(history()).getByText(/No snapshots for 4 min \(gap in the feed\)/)).toBeInTheDocument();
  });

  it('reports the difference across a gap as unknown changes in the inspection line, point name and table', async () => {
    const user = userEvent.setup();
    renderExample({ historyScenario: 'gaps' });
    await summary();
    await selectTrain(user, /Richmond/);
    // +45 and +50 observed; the +30 step falls inside the forced gap (minutes 8–6).
    expect(
      await screen.findByText(
        'From the first to the latest available snapshot, the ETA ended 2 min 5 sec later. ' +
          'Two observed changes of 30 seconds or more occurred outside one gap; additional changes during the gap are unknown.',
      ),
    ).toBeInTheDocument();

    const afterGap =
      'BART published 10:04:46 AM, 10 min 20 sec away, 30 seconds later than the previous available snapshot, ' +
      'across a 4 min gap in the feed; changes during the gap are unknown.';
    const points = within(history()).getAllByRole('img');
    expect(points[6]).toHaveAccessibleName(`Snapshot 9:54:26 AM: ${afterGap}`);

    (points.at(-1) as HTMLElement).focus();
    await user.keyboard('{Home}{ArrowRight>6/}');
    expect(points[6]).toHaveFocus();
    expect(screen.getByTestId('history-inspect')).toHaveTextContent(`Snapshot 9:54:26 AM ${afterGap}`);

    const row = within(within(history()).getByRole('table'))
      .getAllByRole('row')
      .find((r) => r.textContent?.startsWith('9:54:26 AM'));
    expect(row).toHaveTextContent(
      '30 seconds later than the previous available snapshot, across a 4 min gap in the feed; changes during the gap are unknown',
    );
    expect(history()).not.toHaveTextContent(/across three changes|one revision/);
  });

  it('names a populated chart by its data, not by the chart key', async () => {
    renderExample({ historyScenario: 'gaps' });
    await summary();
    const figure = within(history()).getByRole('figure');
    expect(figure).toHaveAccessibleName(
      'Chart of BART’s published ETA for Embarcadero · Antioch train: 12 snapshots from 9:45:26 AM to 9:59:26 AM, with one gap in the feed.',
    );
    expect(figure).not.toHaveAccessibleName(/no snapshots/i);
    expect(figure).not.toHaveAccessibleDescription(/no snapshots/i);
    // The gap entry is part of a labelled key, phrased as a definition.
    expect(within(history()).getByRole('list', { name: 'Chart key' })).toHaveTextContent(
      'Shaded band: A span with no snapshots in the feed.',
    );
  });

  it('anchors the summary to the snapshot when data is stale', async () => {
    renderExample({ scenario: 'stale' });
    expect(await summary()).toHaveTextContent('In the 14 minutes before the 9:50:20 AM snapshot');
    expect(history()).toHaveTextContent(/These snapshots end at 9:50:20 AM, 9 min 40 sec ago/);
  });

  it('shows loading, failure and missing-history states', async () => {
    renderExample({ historyScenario: 'loading' });
    expect(await within(history()).findByText('Loading history…')).toBeInTheDocument();
  });

  it('explains a failed history request and offers a retry', async () => {
    renderExample({ historyScenario: 'error' });
    await screen.findByRole('heading', { level: 3, name: 'Embarcadero · Antioch train' });
    expect(await within(history()).findByText(/The history request failed/)).toBeInTheDocument();
    expect(within(history()).getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('handles the genuine no-history state without drawing a chart', async () => {
    renderExample({ historyScenario: 'none' });
    expect(await summary()).toHaveTextContent('No earlier snapshots of this ETA are available yet.');
    expect(within(history()).queryByRole('figure')).not.toBeInTheDocument();
    expect(within(history()).queryByRole('img')).not.toBeInTheDocument();
    expect(within(history()).queryByRole('list', { name: 'Chart key' })).not.toBeInTheDocument();
  });

  it('handles a single observation', async () => {
    renderExample({ historyScenario: 'single' });
    expect(await summary()).toHaveTextContent(/^Only one snapshot so far/);
    expect(within(history()).getByRole('figure')).toHaveAccessibleName(
      'Chart of BART’s published ETA for Embarcadero · Antioch train: one snapshot, at 9:59:26 AM.',
    );
  });

  it('waits for a prediction before showing history', async () => {
    renderExample({ scenario: 'error' });
    expect(await within(history()).findByText(/No history to show, because the prediction request failed/)).toBeInTheDocument();
  });
});
