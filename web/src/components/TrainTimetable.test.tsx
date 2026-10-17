import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MockPredictionClient } from '../data/MockPredictionClient';
import { TrainTimetable } from './TrainTimetable';

const NOW = new Date('2026-10-13T17:00:00Z'); // 10:00 AM Pacific; the snapshot is 34 s earlier
const clock = () => NOW;

describe('TrainTimetable destination wrapping', () => {
  it('allows a break only after "/" and keeps names and accessible labels intact', async () => {
    const { trains } = await new MockPredictionClient().getPredictions('EMBR', 'to-WOAK');
    render(<TrainTimetable state="ready" trains={trains} selectedId={null} groupPlatform="2" onSelect={() => {}} />);

    const headsigns = [...document.querySelectorAll('.timetable__headsign')];
    expect(headsigns.map((h) => h.textContent)).toEqual(trains.map((t) => t.headsign));
    for (const h of headsigns) {
      // One <wbr> per slash, each directly after it; nothing else inserted.
      expect(h.querySelectorAll('wbr')).toHaveLength((h.textContent ?? '').split('/').length - 1);
      for (const wbr of h.querySelectorAll('wbr')) expect(wbr.previousSibling?.textContent).toBe('/');
    }
    expect(screen.getByRole('radio', { name: /Berryessa\/North San José/ })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Dublin\/Pleasanton/ })).toBeInTheDocument();
  });
});

describe('TrainTimetable rows', () => {
  it('leads with BART’s ETA as a clock time, the time away beneath it', async () => {
    const { trains } = await new MockPredictionClient({ now: clock }).getPredictions('EMBR', 'to-WOAK');
    render(<TrainTimetable state="ready" trains={trains} selectedId={null} groupPlatform="2" onSelect={() => {}} />);
    const [first] = document.querySelectorAll('.timetable__row');
    // Snapshot 9:59:26 AM + 130 s = 10:01:36 AM, shown to the minute as a station clock reads.
    expect(first?.querySelector('.timetable__clock')?.textContent).toBe('10:01 AM');
    expect(first?.querySelector('.timetable__eta')?.textContent).toBe('2 min 10 s');
    expect(screen.getByText('BART ETA')).toBeInTheDocument();
    expect(screen.getAllByRole('radio')[0]).toHaveAccessibleName(/^10:01 AM, 2 min 10 s Antioch Yellow line/);
  });

  it('shows the likely final published ETA for a supported train, and BART ETA only otherwise', async () => {
    const mock = new MockPredictionClient({ now: clock, scenario: 'model-horizon' });
    const { trains } = await mock.getPredictions('EMBR', 'to-WOAK');
    render(<TrainTimetable state="ready" trains={trains} selectedId={null} groupPlatform="2" onSelect={() => {}} />);
    const rows = [...document.querySelectorAll('.timetable__row')];
    // 130 s and 370 s are not near 5, 10 or 15 minutes; 610 s and 905 s are.
    expect(rows.map((r) => r.querySelector('.timetable__forecast, .tone-eta-only')?.textContent)).toEqual([
      'BART ETA only',
      'BART ETA only',
      'Likely final 10:11 AM Likely to be revised', // 10:09:36 AM, 2 min 20 s later
      'Likely final 10:13 AM May be revised', // 10:14:31 AM, 40 s earlier
    ]);
  });

  it('names each train’s platform only when the boarding group has no single platform', async () => {
    const mock = new MockPredictionClient({ now: clock });
    const { trains } = await mock.getPredictions('MCAR', 'to-ASHB-ROCK');
    const { unmount } = render(
      <TrainTimetable state="ready" trains={trains} selectedId={null} groupPlatform={null} onSelect={() => {}} />,
    );
    const lines = [...document.querySelectorAll('.timetable__line')].map((l) => l.textContent);
    expect(lines).toEqual(['Orange line · Platform 1', 'Yellow line · Platform 3', 'Red line · Platform 1']);
    unmount();

    const embarcadero = await mock.getPredictions('EMBR', 'to-WOAK');
    render(
      <TrainTimetable state="ready" trains={embarcadero.trains} selectedId={null} groupPlatform="2" onSelect={() => {}} />,
    );
    expect(document.querySelector('.timetable__line')?.textContent).toBe('Yellow line');
  });

  it('keeps an empty list terse, leaving the explanation to the result', () => {
    render(<TrainTimetable state="empty" trains={[]} selectedId={null} groupPlatform={null} onSelect={() => {}} />);
    const list = screen.getByRole('group', { name: 'Upcoming trains' });
    expect(within(list).getByText('None listed')).toBeInTheDocument();
    expect(list).not.toHaveTextContent(/no trains/i);
  });
});
