import { act, render, screen, within } from '@testing-library/react';
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

const note = () => screen.getByRole('status');

describe('selection in the URL', () => {
  it('starts from the station and boarding group in the query string', async () => {
    renderAt('?station=MCAR&boarding=to-19TH');
    expect(await heading('MacArthur · SF Airport train')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Toward San Francisco and Berryessa' })).toBeChecked();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('accepts lower-case station and boarding IDs, and writes them canonically', async () => {
    renderAt('?station=balb&boarding=TO-daly');
    expect(await heading('Balboa Park · Daly City train')).toBeInTheDocument();
    expect(params()).toEqual({ station: 'BALB', boarding: 'to-DALY' });
  });

  it('falls back safely from an unknown station and corrects the URL', async () => {
    renderAt('?station=NOPE&boarding=to-MONT');
    expect(await heading(/^Embarcadero · /)).toBeInTheDocument();
    expect(note()).toHaveTextContent('Station “NOPE” isn’t in the list, so Embarcadero is shown instead.');
    // A boarding group asked for at another station is not applied to the stand-in.
    expect(params()).toEqual({ station: 'EMBR', boarding: 'to-MONT' });
  });

  it('falls back to the first boarding group, with a visible note, when the group is invalid', async () => {
    renderAt('?station=MCAR&boarding=to-NOPE');
    expect(await heading(/^MacArthur · /)).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Toward Antioch and Richmond' })).toBeChecked();
    expect(note()).toHaveTextContent(
      '“to-NOPE” isn’t a boarding direction at MacArthur, so trains toward Antioch and Richmond are shown instead.',
    );
    expect(params()).toEqual({ station: 'MCAR', boarding: 'to-ASHB-ROCK' });
  });

  it('translates an old direction link when exactly one boarding group carries it', async () => {
    renderAt('?station=EMBR&direction=1');
    expect(await heading('Embarcadero · SF Airport train')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /^Toward Daly City, SFO and Millbrae/ })).toBeChecked();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    // The old parameter is replaced, never written back.
    expect(params()).toEqual({ station: 'EMBR', boarding: 'to-MONT' });
  });

  it('never guesses an old direction at Hayward, where both sides carry both GTFS directions', async () => {
    renderAt('?station=HAYW&direction=1', 'full');
    expect(await heading(/^Hayward · /)).toBeInTheDocument();
    expect(note()).toHaveTextContent(
      'This link’s direction “1” is from an older version of the page and could mean either side of Hayward, so ' +
        'trains toward Berryessa / North San Jose (platform 1) are shown instead. Choose the way you’re going below.',
    );
    expect(params()).toEqual({ station: 'HAYW', boarding: 'to-SHAY' });
  });

  it('says so when an old direction matches no boarding group at the station', async () => {
    renderAt('?station=ANTC&direction=0', 'full');
    expect(await heading(/^Antioch · /)).toBeInTheDocument();
    expect(note()).toHaveTextContent(/^This link’s direction “0” is from an older version of the page and matches no boarding direction at Antioch/);
    expect(params()).toEqual({ station: 'ANTC', boarding: 'to-PCTR' });
  });

  it('prefers the boarding group when a link carries both', async () => {
    renderAt('?station=EMBR&boarding=to-WOAK&direction=1');
    expect(await heading('Embarcadero · Antioch train')).toBeInTheDocument();
    expect(params()).toEqual({ station: 'EMBR', boarding: 'to-WOAK' });
  });

  it('updates the query string as the visitor chooses, keeping other parameters and the hash', async () => {
    const user = userEvent.setup();
    renderAt('?utm=share#example');
    await heading(/^Embarcadero · /);
    // Platform 1 first, as the API orders groups.
    expect(params()).toEqual({ utm: 'share', station: 'EMBR', boarding: 'to-MONT' });
    expect(window.location.hash).toBe('#example');
    await chooseStation(user, 'MacArthur');
    await heading(/^MacArthur · /);
    expect(params()).toEqual({ utm: 'share', station: 'MCAR', boarding: 'to-ASHB-ROCK' });
    await user.click(screen.getByRole('radio', { name: 'Toward San Francisco and Berryessa' }));
    await heading(/^MacArthur · SF Airport/);
    expect(params()).toEqual({ utm: 'share', station: 'MCAR', boarding: 'to-19TH' });
    expect(window.location.hash).toBe('#example');
  });

  it('removes a correction note once the visitor chooses', async () => {
    const user = userEvent.setup();
    renderAt('?station=MCAR&boarding=to-NOPE');
    await heading(/^MacArthur · /);
    expect(note()).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: 'Toward San Francisco and Berryessa' }));
    await heading(/^MacArthur · SF Airport/);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});

describe('back and forward', () => {
  /** What the browser does on back or forward: the address changes, then popstate fires. */
  function traverseTo(search: string) {
    act(() => {
      window.history.replaceState(null, '', `/${search}`);
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
  }

  it('shows whatever the address says after back or forward', async () => {
    renderAt('?station=EMBR&boarding=to-WOAK');
    await heading('Embarcadero · Antioch train');
    traverseTo('?station=MCAR&boarding=to-19TH');
    expect(await heading('MacArthur · SF Airport train')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Toward San Francisco and Berryessa' })).toBeChecked();
    traverseTo('?station=EMBR&boarding=to-MONT#example');
    expect(await heading('Embarcadero · SF Airport train')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Change boarding station, currently Embarcadero' })).toBeInTheDocument();
  });

  it('corrects an invalid address reached by back or forward, with a note', async () => {
    renderAt('?station=EMBR&boarding=to-WOAK');
    await heading('Embarcadero · Antioch train');
    traverseTo('?station=BALB&boarding=nowhere');
    expect(await heading(/^Balboa Park · /)).toBeInTheDocument();
    expect(note()).toHaveTextContent('“nowhere” isn’t a boarding direction at Balboa Park');
    expect(params()).toEqual({ station: 'BALB', boarding: 'to-DALY' });
  });

  it('keeps the chosen train when the address still matches what is shown', async () => {
    const user = userEvent.setup();
    renderAt('?station=EMBR&boarding=to-WOAK');
    await heading('Embarcadero · Antioch train');
    await user.click(within(screen.getByRole('group', { name: 'Upcoming trains' })).getByRole('radio', { name: /Richmond/ }));
    await heading('Embarcadero · Richmond train');
    traverseTo('?station=EMBR&boarding=to-WOAK#question'); // a fragment link, same selection
    expect(await heading('Embarcadero · Richmond train')).toBeInTheDocument();
  });
});

describe('boarding groups at Hayward (full network)', () => {
  it('offers each platform side once, never mixing Berryessa with Daly City or Richmond', async () => {
    const user = userEvent.setup();
    renderAt('?station=HAYW', 'full');
    await heading(/^Hayward · /);
    const ways = within(screen.getByRole('group', { name: 'Which way are you going?' })).getAllByRole('radio');
    expect(ways.map((r) => r.closest('label')?.textContent)).toEqual([
      'Toward Berryessa / North San Jose, Platform 1',
      'Toward Richmond and Daly City, Platform 2',
    ]);
    const headsigns = () => [...document.querySelectorAll('.timetable__headsign')].map((h) => h.textContent);
    expect(new Set(headsigns())).toEqual(new Set(['Berryessa / North San Jose']));
    await user.click(ways[1] as HTMLElement);
    await heading(/^Hayward · (Richmond|Daly City) train$/);
    expect(new Set(headsigns())).toEqual(new Set(['Richmond', 'Daly City']));
    expect(params()).toEqual({ station: 'HAYW', boarding: 'to-BAYF' });
  });

  it('says a terminal is the end of the line, with its one way out', async () => {
    renderAt('?station=ANTC', 'full');
    await heading(/^Antioch · /);
    expect(within(screen.getByRole('group', { name: 'Which way are you going?' })).getAllByRole('radio')).toHaveLength(1);
    expect(
      screen.getByText('Antioch is the end of the line. Trains arriving here end their trips, so only trains leaving are listed.'),
    ).toBeInTheDocument();
  });
});

describe('train list length', () => {
  it(`lists the next ${INITIAL_TRAIN_LIMIT} trains first, in time order`, async () => {
    renderAt('?station=EMBR&boarding=to-WOAK', 'full');
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
    renderAt('?station=EMBR&boarding=to-WOAK', 'full');
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
    renderAt('?station=EMBR&boarding=to-WOAK', 'full');
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
    renderAt('?station=EMBR&boarding=to-WOAK');
    await heading(/^Embarcadero · /);
    expect(trainRadios()).toHaveLength(4);
    expect(screen.queryByRole('button', { name: /more trains|fewer trains/ })).not.toBeInTheDocument();
  });
});
