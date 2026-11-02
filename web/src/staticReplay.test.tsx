// The train explorer on the published curated replay (VITE_DATA_MODE=static, the GitHub
// Pages build), served from web/public/replay and web/public/showcase as the host serves them.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { createPublishedReplayHost } from './test/publishedReplay';
import { chooseStation } from './test/picker';
import { openSite } from './test/site';

const EXPORT = 'v1-20261019T151023Z';
const FEATURED = '?view=explorer&station=ROCK&boarding=to-ORIN&train=2026-10-19%3A1965313%3A17';

const readout = () => screen.getByRole('region', { name: /·|Prediction|No upcoming|Loading/ });
const historyRegion = () => screen.getByRole('region', { name: 'How this ETA has changed' });
const trainGroup = () => screen.getByRole('group', { name: 'Upcoming trains' });
const trainRadio = (find: (radio: HTMLInputElement, i: number) => boolean) => {
  const radio = within(trainGroup()).getAllByRole<HTMLInputElement>('radio').find(find);
  if (!radio) throw new Error('no such train');
  return radio;
};

describe('the train explorer on the curated replay', () => {
  it('loads the station index, then only the shown board and the selected train’s history', async () => {
    const { host, showcaseRequests } = openSite(FEATURED);
    expect(await screen.findByRole('heading', { level: 3, name: 'Rockridge · Pittsburg/Bay Point train' })).toBeInTheDocument();
    await within(historyRegion()).findByTestId('history-summary');
    expect([...host.requests].sort()).toEqual(
      [
        'index.json',
        `${EXPORT}/health.json`,
        `${EXPORT}/stations.json`,
        `${EXPORT}/boards/ROCK/to-ORIN.json`,
        `${EXPORT}/history/2026-10-19_1965313_17.json`,
      ].sort(),
    );
    // The showcase's own four files, each once.
    expect([...showcaseRequests].sort()).toEqual([
      'largest-changes.json',
      'network-map.json',
      'retrospective.json',
      'showcase.json',
    ]);
  });

  it('opens the board of a train the curated replay does not include on its first supported train', async () => {
    openSite('?view=explorer&station=ROCK&boarding=to-ORIN&train=2026-10-20%3A1965313%3A17');
    expect(await screen.findByTestId('forecast')).toHaveTextContent('BART published ETA at the replay moment');
    expect(trainRadio((r) => r.checked).value).toBe('2026-10-19:1965313:17');
    expect(document.body.textContent).not.toMatch(/BART ETA only|No model forecast/);
  });

  it('finds a station by search and keeps it in the URL', async () => {
    const user = userEvent.setup();
    openSite(FEATURED);
    await screen.findByTestId('forecast');
    await chooseStation(user, 'Montgomery Street', 'mont');
    expect(await screen.findByRole('heading', { level: 3, name: /^Montgomery Street · / })).toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).get('station')).toBe('MONT');
  });

  it('shows the error state for a missing or corrupted file, and recovers on retry', async () => {
    const user = userEvent.setup();
    const host = createPublishedReplayHost();
    const board = `${EXPORT}/boards/ROCK/to-ORIN.json`;
    const good = JSON.stringify(await host.read(board));
    host.respond(board, { status: 404, body: '<!doctype html><title>Page not found</title>' });
    openSite(FEATURED, host);
    expect(await screen.findByRole('heading', { level: 3, name: 'Prediction unavailable' })).toBeInTheDocument();
    expect(screen.queryByTestId('forecast')).not.toBeInTheDocument();

    host.respond(board, { body: good });
    await user.click(within(readout()).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { level: 3, name: /^Rockridge · / })).toBeInTheDocument();

    // A corrupted history fails only the chart, which can be retried.
    const second = trainRadio((_, i) => i === 1).value;
    const history = `${EXPORT}/history/${second.replaceAll(':', '_')}.json`;
    const goodHistory = JSON.stringify(await host.read(history));
    host.respond(history, { body: '[{"feedTimestamp": ' });
    await user.click(trainRadio((_, i) => i === 1));
    expect(await within(historyRegion()).findByText(/The history request failed/)).toBeInTheDocument();
    host.respond(history, { body: goodHistory });
    await user.click(within(historyRegion()).getByRole('button', { name: 'Try again' }));
    expect(await within(historyRegion()).findByTestId('history-summary')).toBeInTheDocument();
  });

  it('says the prediction is unavailable when the replay cannot be loaded, and recovers', async () => {
    const user = userEvent.setup();
    const host = createPublishedReplayHost();
    const index = JSON.stringify(await host.read('index.json'));
    host.respond('index.json', { body: JSON.stringify({ ...JSON.parse(index), schemaVersion: 'static-replay-9' }) });
    openSite(FEATURED, host);
    expect(await screen.findByRole('heading', { level: 3, name: 'Prediction unavailable' })).toBeInTheDocument();

    host.respond('index.json', { body: index });
    await user.click(within(readout()).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { level: 3, name: /^Rockridge · / })).toBeInTheDocument();
  });
});
