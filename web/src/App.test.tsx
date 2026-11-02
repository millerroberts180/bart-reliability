import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from './App';
import { BART_DEVELOPER_URL, BART_LICENSE_URL } from './components/SiteFooter';
import { REPOSITORY_URL } from './components/SiteHeader';
import { MockPredictionClient } from './data/MockPredictionClient';
import { openSite } from './test/site';

const MOMENT = 'Monday, October 19, 2026, 8:10 AM PDT';
const FORBIDDEN = /actual arrival|true arrival|train lateness|the train was late|corrected arrival|arrival accuracy|BART ETA only/i;

function renderMock(search = '') {
  window.history.replaceState(null, '', `/${search}`);
  render(<App client={new MockPredictionClient()} />);
}

const nav = () => screen.getByRole('navigation', { name: 'Primary' });
const viewTitle = () => screen.getByRole('heading', { level: 1 });
const search = () => new URLSearchParams(window.location.search);

describe('the site shell', () => {
  it('has persistent navigation to the three views and the source', () => {
    renderMock();
    const links = within(nav()).getAllByRole('link');
    expect(links.map((l) => l.textContent)).toEqual(['Highlights', 'Network map', 'Train explorer', 'Source on GitHub']);
    expect(links.map((l) => l.getAttribute('href'))).toEqual([
      '?view=highlights',
      '?view=map',
      '?view=explorer',
      REPOSITORY_URL,
    ]);
    expect(screen.getByRole('link', { name: 'ETA Reliability' })).toHaveAttribute('href', '?view=highlights');
    expect(within(nav()).getByRole('link', { name: 'Highlights' })).toHaveAttribute('aria-current', 'page');
  });

  it('labels every view as not live, and says the model predicts ETA revisions, not arrivals', async () => {
    const user = userEvent.setup();
    renderMock();
    for (const view of ['Highlights', 'Network map', 'Train explorer']) {
      await user.click(within(nav()).getByRole('link', { name: view }));
      const strip = screen.getByRole('region', { name: 'About this data' });
      expect(strip).toHaveTextContent('Simulated data, not BART data');
      expect(strip).toHaveTextContent('Not live');
      expect(strip).toHaveTextContent('The model predicts revisions to BART’s published ETA, not physical arrival times.');
    }
  });

  it('credits BART’s GTFS and GTFS-Realtime data in the footer, with its developer page and license', () => {
    renderMock();
    const footer = screen.getByRole('contentinfo');
    expect(footer).toHaveTextContent(
      'Source data: GTFS schedule and GTFS-Realtime feeds from BART (San Francisco Bay Area Rapid Transit District), ' +
        'published through BART’s developer program and used under the BART Developer License Agreement.',
    );
    expect(within(footer).getByRole('link', { name: 'developer program' })).toHaveAttribute('href', BART_DEVELOPER_URL);
    expect(within(footer).getByRole('link', { name: 'BART Developer License Agreement' })).toHaveAttribute(
      'href',
      BART_LICENSE_URL,
    );
  });

  it('states in the footer that the site is independent and not an official BART product', () => {
    renderMock();
    expect(screen.getByRole('contentinfo')).toHaveTextContent(
      'ETA Reliability is an independent project. It is not an official BART product, and it is not affiliated with or endorsed by BART.',
    );
  });

  it('explains in the development modes that the curated replay is only in the published site', () => {
    renderMock('?view=map');
    expect(screen.getByText(/only the published site includes/)).toBeInTheDocument();
  });
});

describe('three views with stable addresses', () => {
  it('opens on Highlights, and an unknown view falls back to it', async () => {
    openSite('?view=nowhere');
    expect(viewTitle()).toHaveTextContent('ETA Reliability');
    expect(document.title).toBe('Highlights · ETA Reliability');
  });

  it.each([
    ['?view=highlights', 'ETA Reliability', 'Highlights'],
    ['?view=map', 'Network map', 'Network map'],
    ['?view=explorer', 'Train explorer', 'Train explorer'],
  ])('loads %s directly', async (address, heading, title) => {
    openSite(address);
    expect(viewTitle()).toHaveTextContent(heading);
    expect(document.title).toBe(`${title} · ETA Reliability`);
    expect(within(nav()).getByRole('link', { name: title })).toHaveAttribute('aria-current', 'page');
    const strip = screen.getByRole('region', { name: 'About this data' });
    await waitFor(() => expect(strip).toHaveTextContent(`Fixed historical replay · ${MOMENT}`));
    expect(strip).toHaveTextContent('Not live');
  });

  it('pushes a history entry per view, moves focus to its heading, and honours back and forward', async () => {
    const user = userEvent.setup();
    openSite();
    await user.click(within(nav()).getByRole('link', { name: 'Network map' }));
    expect(viewTitle()).toHaveTextContent('Network map');
    expect(viewTitle()).toHaveFocus();
    await user.click(within(nav()).getByRole('link', { name: 'Train explorer' }));
    expect(viewTitle()).toHaveTextContent('Train explorer');

    window.history.back();
    await waitFor(() => expect(viewTitle()).toHaveTextContent('Network map'));
    window.history.back();
    await waitFor(() => expect(viewTitle()).toHaveTextContent('ETA Reliability'));
    window.history.forward();
    await waitFor(() => expect(viewTitle()).toHaveTextContent('Network map'));
  });
});

describe('Highlights', () => {
  it('explains the project on the first screen, with three restrained figures', async () => {
    openSite();
    expect(screen.getByText('How might BART revise a published ETA as a train approaches?')).toBeInTheDocument();
    expect(screen.getByText('It does not predict when a train physically arrives.')).toBeInTheDocument();
    const figures = await screen.findByText('Supported forecasts in this replay');
    const list = figures.closest('dl');
    expect(list).toHaveTextContent('Supported forecasts in this replay83');
    expect(list).toHaveTextContent('Stations represented37');
    expect(list).toHaveTextContent('Model version0.2.0+886fcd260732');
    expect(
      screen.getByText(
        'This curated replay shows only trains eligible for the model’s 5-, 10- and 15-minute forecast windows.',
      ),
    ).toBeInTheDocument();
  });

  it('shows the largest ETA changes one horizon at a time, five at most, and keeps the choice in the URL', async () => {
    const user = userEvent.setup();
    openSite();
    const horizon = await screen.findByRole('group', { name: 'Forecast horizon' });
    const option = (name: string) => within(horizon).getByRole('button', { name });
    expect(option('5 minutes')).toHaveAttribute('aria-pressed', 'true');
    const entries = () => screen.getAllByRole('listitem').filter((li) => li.classList.contains('change'));
    expect(entries()).toHaveLength(5);
    expect(entries()[0]).toHaveAccessibleName('Rockridge to Pittsburg/Bay Point');

    await user.click(option('10 minutes'));
    expect(option('10 minutes')).toHaveAttribute('aria-pressed', 'true');
    expect(option('5 minutes')).toHaveAttribute('aria-pressed', 'false');
    expect(search().get('horizon')).toBe('600');
    expect(entries()[0]).toHaveAccessibleName('Rockridge to Antioch');

    await user.click(option('15 minutes'));
    expect(entries()[0]).toHaveAccessibleName('Lafayette to Pittsburg/Bay Point');
    expect(entries().length).toBeLessThanOrEqual(5);
  });

  it('labels each step from BART’s ETA to what BART later published, and the last as retrospective', async () => {
    openSite();
    const first = await screen.findByRole('listitem', { name: 'Rockridge to Pittsburg/Bay Point' });
    expect(first).toHaveTextContent('BART said8:15:29 AMBART published ETA, 5 min 7 s away');
    expect(first).toHaveTextContent('Model expected8:16:29 AMModel-adjusted ETA');
    expect(first).toHaveTextContent('Predicted change: about 1 min later');
    expect(first).toHaveTextContent('BART later published8:16:47 AM');
    expect(first).toHaveTextContent('Retrospective. Realized change: about 1 min 18 sec later');
    expect(first).toHaveTextContent('Direction matched.');
    expect(first).toHaveTextContent('The model-adjusted ETA was 18 seconds earlier than what BART later published.');
    // The rankings show the largest changes; the whole replay's direction result is stated beside them.
    expect(
      screen.getByText(
        /^Across all 83 trains in this replay, the predicted direction matched what BART later published for 76 and differed for 7\. The moment was chosen from 1,440 snapshots of the day by coverage alone; no outcome or accuracy was read\.$/,
      ),
    ).toBeInTheDocument();
  });

  it('links each entry to that train in the explorer', async () => {
    const user = userEvent.setup();
    openSite();
    const link = (await screen.findAllByRole('link', { name: 'View in the train explorer' }))[0];
    if (!link) throw new Error('no link');
    expect(link).toHaveAttribute(
      'href',
      '?view=explorer&station=ROCK&boarding=to-ORIN&train=2026-10-19%3A1965313%3A17',
    );
    await user.click(link);
    expect(viewTitle()).toHaveTextContent('Train explorer');
    expect(await screen.findByRole('heading', { name: 'Rockridge · Pittsburg/Bay Point train' })).toBeInTheDocument();
    expect(search().get('train')).toBe('2026-10-19:1965313:17');
  });
});

describe('Network map', () => {
  it('switches between the model forecast and what BART later published, in the URL', async () => {
    const user = userEvent.setup();
    openSite('?view=map');
    const modes = await screen.findByRole('group', { name: 'Map display' });
    const forecast = within(modes).getByRole('button', { name: 'Model forecast at the time' });
    const published = within(modes).getByRole('button', { name: 'What BART later published' });
    expect(forecast).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Median expected ETA revision')).toBeInTheDocument();

    await user.click(published);
    expect(published).toHaveAttribute('aria-pressed', 'true');
    expect(search().get('mode')).toBe('published');
    expect(screen.getByText('Median ETA revision BART later published')).toBeInTheDocument();
    expect(screen.getByText(/BART published this after the replay moment/)).toBeInTheDocument();
  });

  it('names every station, says which have no supported forecast, and selects one from the keyboard', async () => {
    const user = userEvent.setup();
    openSite('?view=map');
    const rockridge = await screen.findByRole('button', { name: /^Rockridge: 2 supported trains, median expected revision about/ });
    expect(screen.getByRole('button', { name: 'Antioch: no supported forecast at this replay moment' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { pressed: false, name: /: / }).length).toBeGreaterThanOrEqual(50);

    rockridge.focus();
    await user.keyboard('{Enter}');
    expect(rockridge).toHaveAttribute('aria-pressed', 'true');
    expect(search().get('station')).toBe('ROCK');
    const panel = screen.getByRole('complementary', { name: 'Rockridge' });
    expect(panel).toHaveTextContent('2 supported trains at this moment');
    expect(panel).toHaveTextContent('Largest expected ETA revision');
    expect(panel).toHaveTextContent('Largest ETA revision BART later published (retrospective)');
    const link = within(panel).getByRole('link', { name: /in the train explorer/ });
    expect(link.getAttribute('href')).toMatch(/^\?view=explorer&station=ROCK&boarding=to-[A-Z-]+&train=2026-10-19%3A/);

    await user.click(link);
    expect(viewTitle()).toHaveTextContent('Train explorer');
    expect(await screen.findByRole('heading', { name: /^Rockridge · / })).toBeInTheDocument();
  });

  it('reads the map one line at a time, in the URL, and says which stations the line skips', async () => {
    const user = userEvent.setup();
    openSite('?view=map&station=ROCK');
    const lines = await screen.findByRole('group', { name: 'Line' });
    expect(within(lines).getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(within(lines).getByRole('button', { name: 'Yellow' }));
    expect(within(lines).getByRole('button', { name: 'Yellow' })).toHaveAttribute('aria-pressed', 'true');
    expect(search().get('line')).toBe('yellow');
    expect(screen.getByText(/stations with a supported forecast on the Yellow line/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fremont, Yellow line: not on this line' })).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Rockridge' })).toHaveTextContent(
      /supported trains? on the Yellow line at this moment/,
    );
    await user.click(within(lines).getByRole('button', { name: 'All' }));
    expect(search().get('line')).toBeNull();
  });

  it('offers every station as a table, without relying on the drawing', async () => {
    const user = userEvent.setup();
    openSite('?view=map');
    await user.click(await screen.findByText('Every station as a table'));
    const table = screen.getByRole('table');
    expect(within(table).getAllByRole('row')).toHaveLength(51);
    await user.click(within(table).getByRole('button', { name: 'Antioch' }));
    expect(screen.getByRole('complementary', { name: 'Antioch' })).toHaveTextContent(
      'No supported forecast at this replay moment.',
    );
  });
});

describe('Train explorer', () => {
  it('opens the featured record, and lists only trains with a supported forecast', async () => {
    openSite('?view=explorer');
    expect(await screen.findByRole('heading', { name: 'Rockridge · Pittsburg/Bay Point train' })).toBeInTheDocument();
    const radios = within(screen.getByRole('group', { name: 'Upcoming trains' })).getAllByRole('radio');
    expect(radios.length).toBeGreaterThan(0);
    for (const row of radios.map((r) => r.closest('label'))) expect(row).toHaveTextContent(/Model-adjusted \d/);
    expect(screen.getByText(/only trains eligible for the model’s 5-, 10- and 15-minute/)).toBeInTheDocument();
  });

  it('reads the forecast in order, with what BART later published marked as retrospective', async () => {
    openSite('?view=explorer&station=ROCK&boarding=to-ORIN&train=2026-10-19%3A1965313%3A17');
    const forecast = await screen.findByTestId('forecast');
    expect(forecast).toHaveTextContent('BART published ETA at the replay moment8:15 AM');
    const steps = ['step-revision', 'step-adjusted', 'step-uncertainty', 'step-final'].map((id) => screen.getByTestId(id));
    expect(steps[0]).toHaveTextContent('Expected to move about 1 min later');
    expect(steps[1]).toHaveTextContent('Model-adjusted ETA8:16:29 AM');
    expect(steps[1]).toHaveTextContent('It is not an observed arrival time.');
    expect(steps[2]).toHaveTextContent('45% chance BART changes this ETA by more than 60 seconds');
    expect(steps[3]).toHaveTextContent('BART later published Retrospective8:16:47 AM · ETA moved about 1 min 18 sec later');
    expect(steps[3]).toHaveTextContent('The model did not know it.');
    steps.slice(1).forEach((step, i) => {
      const before = steps[i];
      expect(before && before.compareDocumentPosition(step) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });
    expect(await screen.findByRole('region', { name: 'How this ETA has changed' })).toBeInTheDocument();
  });

  it('keeps the selected train in the URL', async () => {
    const user = userEvent.setup();
    openSite('?view=explorer&station=ROCK&boarding=to-ORIN&train=2026-10-19%3A1965313%3A17');
    await screen.findByTestId('forecast');
    const radios = within(screen.getByRole('group', { name: 'Upcoming trains' })).getAllByRole('radio');
    const other = radios.find((r) => !(r as HTMLInputElement).checked);
    if (!other) throw new Error('only one train');
    await user.click(other);
    expect(search().get('train')).toBe((other as HTMLInputElement).value);
    expect(search().get('view')).toBe('explorer');
  });
});

describe('the published site’s words and drawings', () => {
  it('never uses physical-arrival or lateness language, nor a “BART ETA only” state, on any view', async () => {
    for (const address of ['?view=highlights', '?view=map&mode=published&station=ROCK', '?view=explorer']) {
      const { unmount } = openSite(address);
      await waitFor(() => expect(screen.getByRole('region', { name: 'About this data' })).toHaveTextContent(MOMENT));
      await waitFor(() => expect(document.body.textContent).toMatch(/BART later published|What BART later published/));
      expect(document.body.textContent).not.toMatch(FORBIDDEN);
      unmount();
    }
  });

  it('shows no images: no BART logo and no copied system map', async () => {
    openSite('?view=map');
    await screen.findByRole('group', { name: /Network schematic/ });
    expect(document.querySelector('img, picture, object, embed, iframe, image')).toBeNull();
    expect(screen.queryByRole('img', { name: /logo/i })).not.toBeInTheDocument();
  });
});
