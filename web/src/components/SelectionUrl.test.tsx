import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MockPredictionClient } from '../data/MockPredictionClient';
import { PredictionClientProvider } from '../data/PredictionClientContext';
import { chooseStation } from '../test/picker';
import { PredictionExample } from './PredictionExample';
import { INITIAL_TRAIN_LIMIT } from './TrainTimetable';

const NOW = new Date('2026-10-13T17:00:00Z');
const clock = () => NOW;

function renderAt(search: string, network: 'demo' | 'full' = 'demo') {
  window.history.replaceState(null, '', `/${search}`);
  render(
    <PredictionClientProvider client={new MockPredictionClient({ network, now: clock })} now={clock}>
      <PredictionExample />
    </PredictionClientProvider>,
  );
}

const params = () => Object.fromEntries(new URLSearchParams(window.location.search));
const heading = (name: string | RegExp) => screen.findByRole('heading', { level: 3, name });
const trainRadios = () => within(screen.getByRole('group', { name: 'Upcoming trains' })).getAllByRole('radio');

describe('selection in the URL', () => {
  it('starts from the station and direction in the query string', async () => {
    renderAt('?station=MCAR&direction=1');
    expect(await heading('MacArthur · SF Airport train')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Toward San Francisco and Berryessa' })).toBeChecked();
  });

  it('accepts a lower-case station ID', async () => {
    renderAt('?station=balb');
    expect(await heading(/^Balboa Park · /)).toBeInTheDocument();
    expect(params()).toEqual({ station: 'BALB', direction: '0' });
  });

  it('falls back safely from an unknown station and corrects the URL', async () => {
    renderAt('?station=NOPE&direction=1');
    expect(await heading(/^Embarcadero · /)).toBeInTheDocument();
    expect(screen.getByRole('status', { name: '' })).toHaveTextContent(
      'Station “NOPE” isn’t in the list, so Embarcadero is shown instead.',
    );
    expect(params()).toEqual({ station: 'EMBR', direction: '1' });
  });

  it('falls back to the first direction when the direction is invalid', async () => {
    renderAt('?station=MCAR&direction=7');
    expect(await heading(/^MacArthur · /)).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Toward Antioch and Richmond' })).toBeChecked();
    expect(params()).toEqual({ station: 'MCAR', direction: '0' });
  });

  it('updates the query string as the visitor chooses, keeping other parameters', async () => {
    const user = userEvent.setup();
    renderAt('?utm=share');
    await heading(/^Embarcadero · /);
    expect(params()).toEqual({ utm: 'share', station: 'EMBR', direction: '0' });
    await chooseStation(user, 'MacArthur');
    await heading(/^MacArthur · /);
    expect(params()).toEqual({ utm: 'share', station: 'MCAR', direction: '0' });
    await user.click(screen.getByRole('radio', { name: 'Toward San Francisco and Berryessa' }));
    await heading(/^MacArthur · SF Airport/);
    expect(params()).toEqual({ utm: 'share', station: 'MCAR', direction: '1' });
  });
});

describe('train list length', () => {
  it(`lists the next ${INITIAL_TRAIN_LIMIT} trains first, in time order`, async () => {
    renderAt('?station=EMBR&direction=0', 'full');
    await heading(/^Embarcadero · /);
    const rows = trainRadios();
    expect(rows).toHaveLength(INITIAL_TRAIN_LIMIT);
    const toggle = screen.getByRole('button', { name: 'Show 16 more trains' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    const etas = rows.map((r) => r.closest('label')?.querySelector('.timetable__eta')?.textContent ?? '');
    const seconds = etas.map((t) => {
      const [, m = '0', s = '0'] = /(?:(\d+) min)?\s*(?:(\d+) s)?/.exec(t) ?? [];
      return Number(m) * 60 + Number(s);
    });
    expect(seconds).toEqual([...seconds].sort((a, b) => a - b));
  });

  it('expands to all trains and collapses again', async () => {
    const user = userEvent.setup();
    renderAt('?station=EMBR&direction=0', 'full');
    await heading(/^Embarcadero · /);
    await user.click(screen.getByRole('button', { name: 'Show 16 more trains' }));
    expect(trainRadios()).toHaveLength(20);
    const toggle = screen.getByRole('button', { name: 'Show fewer trains' });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await user.click(toggle);
    expect(trainRadios()).toHaveLength(INITIAL_TRAIN_LIMIT);
    expect(screen.getByRole('button', { name: 'Show 16 more trains' })).toHaveFocus();
  });

  it('never hides the selected train when collapsing', async () => {
    const user = userEvent.setup();
    renderAt('?station=EMBR&direction=0', 'full');
    await heading(/^Embarcadero · /);
    await user.click(screen.getByRole('button', { name: 'Show 16 more trains' }));
    const seventh = trainRadios()[6];
    await user.click(seventh as HTMLElement);
    await user.click(screen.getByRole('button', { name: 'Show fewer trains' }));
    const rows = trainRadios();
    expect(rows).toHaveLength(INITIAL_TRAIN_LIMIT + 1);
    expect(rows.at(-1)).toBeChecked();
    expect(screen.getByText('Later train you selected')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show 15 more trains' })).toBeInTheDocument();
  });

  it('shows no toggle when every train already fits', async () => {
    renderAt('?station=EMBR&direction=0');
    await heading(/^Embarcadero · /);
    expect(trainRadios()).toHaveLength(4);
    expect(screen.queryByRole('button', { name: /more trains|fewer trains/ })).not.toBeInTheDocument();
  });
});
