// The picker in HTTP mode: it must offer exactly the stations /api/v1/stations returned,
// and read the URL only once that list has arrived.

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from '../App';
import { HttpPredictionClient } from '../data/HttpPredictionClient';
import { API_BASE, API_RECORDING, createFakeApi, type FakeApi } from '../test/fakeApi';

const STATIONS_PATH = '/api/v1/stations';
const BOARD = (station: string, group: string) => `/api/v1/stations/${station}/predictions?boarding_group=${group}`;

/** An API whose station list is held back until `release` is called. */
function apiWithHeldStations(): { api: FakeApi; release: () => void } {
  const api = createFakeApi();
  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  api.respond(STATIONS_PATH, async () => {
    await gate;
    return new Response(JSON.stringify(API_RECORDING.responses[STATIONS_PATH]), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  return { api, release };
}

function renderAt(search: string, api: FakeApi) {
  window.history.replaceState(null, '', `/${search}`);
  render(<App client={new HttpPredictionClient(API_BASE, { fetch: api.fetch })} />);
}

const params = () => Object.fromEntries(new URLSearchParams(window.location.search));

describe('station picker over the HTTP client', () => {
  it('searches only the stations the API returned, not a simulated fixture', async () => {
    const user = userEvent.setup();
    renderAt('', createFakeApi());
    await user.click(await screen.findByRole('button', { name: /^Change boarding station/ }));
    await user.click(screen.getByRole('button', { name: 'Browse all 4 stations' }));
    const names = within(screen.getByRole('listbox')).getAllByRole('option').map((o) => o.querySelector('.picker__option-name')?.textContent);
    expect(names).toEqual(['Antioch', 'Castro Valley', 'Downtown Berkeley', 'Hayward']);

    // Embarcadero is in both simulated sets but not in this API's list.
    await user.type(screen.getByRole('combobox', { name: 'Where are you boarding?' }), 'Embarcadero');
    expect(screen.getByText('No stations match “Embarcadero”. Check the spelling, or browse all stations.')).toBeInTheDocument();
  });

  it('keeps a URL station while stations load, then requests only that board', async () => {
    const { api, release } = apiWithHeldStations();
    renderAt('?station=CAST&boarding=to-BAYF', api);
    await screen.findByText('Loading stations…');
    // Nothing is judged, rewritten or requested for a default station before the list arrives.
    expect(screen.queryByText(/isn’t in the list/)).not.toBeInTheDocument();
    expect(params()).toEqual({ station: 'CAST', boarding: 'to-BAYF' });
    expect(api.requests).not.toContain(BOARD('ANTC', 'to-PCTR'));

    release();
    expect(await screen.findByRole('button', { name: 'Change boarding station, currently Castro Valley' })).toBeInTheDocument();
    await screen.findByRole('heading', { level: 3, name: /^Castro Valley · / });
    expect(api.requests.filter((p) => p.includes('/predictions?'))).toEqual([BOARD('CAST', 'to-BAYF')]);
    expect(params()).toEqual({ station: 'CAST', boarding: 'to-BAYF' });
  });

  it('keeps an old direction link while stations load, then translates it from the API’s groups', async () => {
    const { api, release } = apiWithHeldStations();
    renderAt('?station=CAST&direction=1', api);
    await screen.findByText('Loading stations…');
    expect(params()).toEqual({ station: 'CAST', direction: '1' });
    release();
    await screen.findByRole('heading', { level: 3, name: /^Castro Valley · / });
    // At Castro Valley only the group toward Bay Fair carries GTFS direction 1.
    expect(api.requests.filter((p) => p.includes('/predictions?'))).toEqual([BOARD('CAST', 'to-BAYF')]);
    expect(params()).toEqual({ station: 'CAST', boarding: 'to-BAYF' });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('warns about an unknown URL station only after the list has loaded and been checked', async () => {
    const { api, release } = apiWithHeldStations();
    renderAt('?station=EMBR', api);
    await screen.findByText('Loading stations…');
    expect(screen.queryByText(/isn’t in the list/)).not.toBeInTheDocument();
    expect(params()).toEqual({ station: 'EMBR' });

    release();
    expect(await screen.findByText('Station “EMBR” isn’t in the list, so Antioch is shown instead.')).toBeInTheDocument();
    // The address is corrected by an effect after that render.
    await waitFor(() => expect(params()).toEqual({ station: 'ANTC', boarding: 'to-PCTR' }));
  });
});
