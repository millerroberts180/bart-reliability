import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MockPredictionClient, type MockNetwork } from '../data/MockPredictionClient';
import { PredictionClientProvider } from '../data/PredictionClientContext';
import { PredictionExample } from './PredictionExample';

const NOW = new Date('2026-10-13T17:00:00Z');
const clock = () => NOW;

function renderExample(network: MockNetwork = 'full') {
  render(
    <PredictionClientProvider client={new MockPredictionClient({ network, now: clock })} now={clock}>
      <PredictionExample />
    </PredictionClientProvider>,
  );
}

const changeButton = () => screen.findByRole('button', { name: /^Change boarding station, currently/ });
const combobox = () => screen.getByRole('combobox', { name: 'Where are you boarding?' });
const options = () => within(screen.getByRole('listbox')).queryAllByRole('option');
const optionNames = () => options().map((o) => o.querySelector('.picker__option-name')?.textContent);
const status = () => screen.getByTestId('picker-status');

async function openPicker(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await changeButton());
}

describe('StationPicker', () => {
  it('shows the chosen station compactly and opens to a focused search field', async () => {
    const user = userEvent.setup();
    renderExample();
    const change = await changeButton();
    // With nothing chosen, the default is the first station the client lists.
    expect(change).toHaveAccessibleName('Change boarding station, currently 12th Street / Oakland City Center');
    expect(change).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    await user.click(change);
    expect(combobox()).toHaveFocus();
    expect(combobox()).toHaveAttribute('aria-expanded', 'true');
    expect(combobox()).toHaveAttribute('aria-controls', screen.getByRole('listbox').id);
    // No recent stations yet: suggest the current station, without guessing a location.
    expect(screen.getByRole('listbox', { name: 'Suggested' })).toBeInTheDocument();
    expect(optionNames()).toEqual(['12th Street / Oakland City Center']);
    expect(status()).toHaveTextContent('Suggested: 12th Street / Oakland City Center. Type to search all 50 stations.');
  });

  it('filters immediately as you type, including aliases such as SFO', async () => {
    const user = userEvent.setup();
    renderExample();
    await openPicker(user);
    await user.type(combobox(), 'SFO');
    expect(screen.getByRole('listbox', { name: 'Matching stations' })).toBeInTheDocument();
    expect(optionNames()[0]).toBe('San Francisco International Airport');

    await user.clear(combobox());
    await user.type(combobox(), 'st');
    expect(options()).toHaveLength(8);
    expect(screen.getByText(/Showing 8 of \d+\. Keep typing to narrow the list\./)).toBeInTheDocument();
    expect(status()).toHaveTextContent(/^8 of \d+ stations match “st”\.$/);
  });

  it('explains when nothing matches', async () => {
    const user = userEvent.setup();
    renderExample();
    await openPicker(user);
    await user.type(combobox(), 'zzz');
    expect(options()).toHaveLength(0);
    expect(screen.getByText('No stations match “zzz”. Check the spelling, or browse all stations.')).toBeInTheDocument();
    expect(status()).toHaveTextContent('No stations match “zzz”.');
    expect(combobox()).not.toHaveAttribute('aria-activedescendant');
  });

  it('browses every station inside the panel', async () => {
    const user = userEvent.setup();
    renderExample();
    await openPicker(user);
    await user.click(screen.getByRole('button', { name: 'Browse all 50 stations' }));
    expect(screen.getByRole('listbox', { name: 'All stations' })).toBeInTheDocument();
    expect(options()).toHaveLength(50);
    expect(optionNames()[0]).toBe('12th Street / Oakland City Center');
    expect(combobox()).toHaveFocus();
    // The full list lives in the scrolling panel, not the page flow.
    expect(screen.getByRole('listbox').closest('.picker__panel')).not.toBeNull();
  });

  it('moves with the arrow keys, selects with Enter and returns focus to Change', async () => {
    const user = userEvent.setup();
    renderExample();
    await openPicker(user);
    await user.type(combobox(), 'oak');
    const first = options()[0];
    expect(combobox()).toHaveAttribute('aria-activedescendant', first?.id);
    expect(first).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{ArrowDown}');
    const second = options()[1];
    expect(combobox()).toHaveAttribute('aria-activedescendant', second?.id);
    expect(second).toHaveAttribute('aria-selected', 'true');
    expect(first).toHaveAttribute('aria-selected', 'false');
    const chosen = second?.querySelector('.picker__option-name')?.textContent ?? '';

    await user.keyboard('{Enter}');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    const change = await changeButton();
    expect(change).toHaveFocus();
    expect(change).toHaveAccessibleName(`Change boarding station, currently ${chosen}`);
    expect(screen.getByText(`${chosen} selected as your boarding station.`)).toBeInTheDocument();
  });

  it('closes on Escape without changing the station', async () => {
    const user = userEvent.setup();
    renderExample();
    await openPicker(user);
    await user.type(combobox(), 'mac');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(await changeButton()).toHaveFocus();
    expect(await changeButton()).toHaveAccessibleName('Change boarding station, currently 12th Street / Oakland City Center');
  });

  it('lets Tab continue past the panel and closes it', async () => {
    const user = userEvent.setup();
    renderExample();
    await openPicker(user);
    await user.tab();
    expect(screen.getByRole('button', { name: 'Browse all 50 stations' })).toHaveFocus();
    await user.tab();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.getAllByRole('radio', { name: /^Toward/ })[0]).toHaveFocus();
  });

  it('remembers up to three recent stations, most recent first, as IDs only', async () => {
    const user = userEvent.setup();
    renderExample();
    for (const query of ['MacArthur', 'Balboa', 'Fruitvale', 'Antioch']) {
      await openPicker(user);
      await user.type(combobox(), query);
      await user.keyboard('{Enter}');
    }
    await openPicker(user);
    expect(screen.getByRole('listbox', { name: 'Recent' })).toBeInTheDocument();
    expect(optionNames()).toEqual(['Antioch', 'Fruitvale', 'Balboa Park']);
    expect(status()).toHaveTextContent('3 recent stations. Type to search all 50.');
    expect(JSON.parse(window.localStorage.getItem('eta-reliability.recent-stations') ?? '[]')).toEqual([
      'ANTC',
      'FTVL',
      'BALB',
    ]);
  });

  it('keeps long station names whole in the options and the selected row', async () => {
    const user = userEvent.setup();
    renderExample();
    await openPicker(user);
    await user.type(combobox(), 'pleasant hill');
    expect(optionNames()).toEqual(['Pleasant Hill / Contra Costa Centre']);
    await user.keyboard('{Enter}');
    expect(screen.getByText('Pleasant Hill / Contra Costa Centre', { selector: '.picker__current' })).toBeInTheDocument();
    expect(
      await screen.findByRole('heading', { level: 3, name: /^Pleasant Hill \/ Contra Costa Centre · / }),
    ).toBeInTheDocument();
  });

  it('works with the small demo station set too', async () => {
    const user = userEvent.setup();
    renderExample('demo');
    await openPicker(user);
    await user.click(screen.getByRole('button', { name: 'Browse all 3 stations' }));
    expect(optionNames()).toEqual(['Balboa Park', 'Embarcadero', 'MacArthur']);
  });
});
