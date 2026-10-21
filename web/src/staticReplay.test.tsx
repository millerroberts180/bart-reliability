// The page on the published static replay (VITE_DATA_MODE=static, the GitHub Pages build),
// served from the files in web/public/replay as the site's host serves them.

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { App } from './App';
import { StaticReplayClient } from './data/StaticReplayClient';
import { createPublishedReplayHost, PUBLISHED_ROOT, type PublishedReplayHost } from './test/publishedReplay';
import { chooseStation } from './test/picker';

const EXPORT = 'v1-20261020T170000Z';
const LONG_MOMENT = 'Tuesday, October 20, 2026 at 10:00 AM Pacific';

function open(search = '', host: PublishedReplayHost = createPublishedReplayHost()) {
  window.history.replaceState(null, '', `/${search}`);
  render(<App client={new StaticReplayClient(PUBLISHED_ROOT, { fetch: host.fetch })} />);
  return host;
}

afterEach(() => window.history.replaceState(null, '', '/'));

const readout = () => screen.getByRole('region', { name: /·|Prediction|No upcoming|Loading/ });
const historyRegion = () => screen.getByRole('region', { name: 'How this ETA has changed' });
const trainGroup = () => screen.getByRole('group', { name: 'Upcoming trains' });
const histories = (host: PublishedReplayHost) => host.requests.filter((r) => r.includes('/history/'));
const trainRadio = (find: (radio: HTMLInputElement, i: number) => boolean) => {
  const radio = within(trainGroup()).getAllByRole<HTMLInputElement>('radio').find(find);
  if (!radio) throw new Error('no such train');
  return radio;
};

describe('the static historical replay', () => {
  it('says plainly that it is a fixed historical replay of October 20, not live data', async () => {
    open();
    await screen.findByTestId('forecast');

    const opening = screen.getByRole('region', { name: 'ETA Reliability' });
    const disclosure = within(opening).getByRole('complementary', { name: 'Historical replay of recorded BART data' });
    expect(disclosure).toHaveTextContent(`This page replays BART’s recorded feeds as they stood on ${LONG_MOMENT}.`);
    expect(disclosure).toHaveTextContent(
      'The data is fixed at that moment: it is not live, and nothing on the page updates or counts down.',
    );
    expect(opening).toHaveTextContent('It does not predict when a train physically arrives.');
    expect(screen.getByTestId('replay-notice')).toHaveTextContent(
      `Historical replay—fixed, not live. BART data as of ${LONG_MOMENT}.`,
    );
    expect(screen.getByTestId('forecast')).toHaveTextContent(/BART’s published ETA|Likely final published ETA/);
    expect(screen.getByTestId('data-details')).toHaveTextContent('Version 0.2.0+886fcd260732');

    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/simulat|prototype/i);
    expect(text.replace(/not live|Nothing here is live/g, '')).not.toMatch(/\blive\b/i);
    expect(text).not.toMatch(/currently says|right now|\bCurrent\b|Over the last/);
  });

  it('loads the station index first, then only the shown board and the selected train’s history', async () => {
    const user = userEvent.setup();
    const host = open();
    expect(await screen.findByRole('heading', { level: 3, name: '12th Street / Oakland City Center · Richmond train' })).toBeInTheDocument();
    await within(historyRegion()).findByTestId('history-summary');
    expect([...host.requests].sort()).toEqual(
      [
        'index.json',
        `${EXPORT}/health.json`,
        `${EXPORT}/stations.json`,
        `${EXPORT}/boards/12TH/to-19TH.json`,
        `${EXPORT}/history/2026-10-20_1965678_16.json`,
      ].sort(),
    );

    // Choosing another train fetches its history, and only that.
    await user.click(trainRadio((_, i) => i === 1));
    await within(historyRegion()).findByTestId('history-summary');
    expect(histories(host)).toHaveLength(2);

    // Another boarding group: its board, then its first train's history.
    await user.click(screen.getByRole('radio', { name: /^Toward Berryessa/ }));
    expect(await screen.findByRole('heading', { level: 3, name: /^12th Street \/ Oakland City Center · / })).toBeInTheDocument();
    await within(historyRegion()).findByTestId('history-summary');
    expect(host.requests.filter((r) => r.includes('/boards/'))).toEqual([
      `${EXPORT}/boards/12TH/to-19TH.json`,
      `${EXPORT}/boards/12TH/to-LAKE-WOAK.json`,
    ]);
    expect(histories(host)).toHaveLength(3);
    expect(host.requests.filter((r) => r === 'index.json')).toHaveLength(1);
  });

  it('opens a deep link to a fallback train’s board and shows BART’s ETA only', async () => {
    const user = userEvent.setup();
    open('?station=WDUB&boarding=to-DUBL');
    expect(await screen.findByRole('heading', { level: 3, name: /^West Dublin \/ Pleasanton · / })).toBeInTheDocument();
    await user.click(trainRadio((r) => r.value === '2026-10-20:1965828:16'));
    expect(await screen.findByTestId('no-forecast')).toHaveTextContent(
      'No model forecast: this train is outside what the model has been shown to support.',
    );
    expect(screen.getByTestId('forecast')).toHaveTextContent(/^BART’s published ETA/);
  });

  it('explains an empty board from what the replay shows', async () => {
    open('?station=PCTR&boarding=to-ANTC');
    expect(await screen.findByRole('heading', { level: 3, name: 'No upcoming trains' })).toBeInTheDocument();
    expect(readout()).toHaveTextContent(
      'BART’s feed does list 9 trains at Pittsburg Center that match no scheduled trip, so which way they’re going isn’t known and they aren’t shown.',
    );
  });

  it('finds a station by search and remembers it', async () => {
    const user = userEvent.setup();
    open();
    await screen.findByTestId('forecast');
    await chooseStation(user, 'Montgomery Street', 'mont');
    expect(await screen.findByRole('heading', { level: 3, name: /^Montgomery Street · / })).toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).get('station')).toBe('MONT');
  });

  it('shows the error state for a missing or corrupted file, and recovers on retry', async () => {
    const user = userEvent.setup();
    const host = createPublishedReplayHost();
    const board = `${EXPORT}/boards/MONT/to-EMBR.json`;
    const good = JSON.stringify(await host.read(board));
    host.respond(board, { status: 404, body: '<!doctype html><title>Page not found</title>' });
    open('?station=MONT&boarding=to-EMBR', host);
    expect(await screen.findByRole('heading', { level: 3, name: 'Prediction unavailable' })).toBeInTheDocument();
    expect(screen.queryByTestId('forecast')).not.toBeInTheDocument();

    host.respond(board, { body: good });
    await user.click(within(readout()).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { level: 3, name: /^Montgomery Street · / })).toBeInTheDocument();

    // A corrupted history fails only the chart, which can be retried.
    const history = `${EXPORT}/history/2026-10-20_1965254_11.json`;
    const goodHistory = JSON.stringify(await host.read(history));
    host.respond(history, { body: '[{"feedTimestamp": ' });
    await user.click(trainRadio((_, i) => i === 1));
    await user.click(trainRadio((_, i) => i === 0));
    expect(await within(historyRegion()).findByText(/The history request failed/)).toBeInTheDocument();
    host.respond(history, { body: goodHistory });
    await user.click(within(historyRegion()).getByRole('button', { name: 'Try again' }));
    expect(await within(historyRegion()).findByTestId('history-summary')).toBeInTheDocument();
  });

  it('says the data is unavailable when the replay cannot be loaded, and recovers', async () => {
    const user = userEvent.setup();
    const host = createPublishedReplayHost();
    const index = JSON.stringify(await host.read('index.json'));
    host.respond('index.json', { body: JSON.stringify({ ...JSON.parse(index), schemaVersion: 'static-replay-9' }) });
    open('', host);
    const disclosure = await screen.findByRole('complementary', { name: 'Data unavailable' });
    expect(await screen.findByRole('heading', { level: 3, name: 'Prediction unavailable' })).toBeInTheDocument();

    host.respond('index.json', { body: index });
    await user.click(within(disclosure).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('complementary', { name: 'Historical replay of recorded BART data' })).toBeInTheDocument();
  });
});
