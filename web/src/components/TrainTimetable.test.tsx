import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MockPredictionClient } from '../data/MockPredictionClient';
import { TrainTimetable } from './TrainTimetable';

describe('TrainTimetable destination wrapping', () => {
  it('allows a break only after "/" and keeps names and accessible labels intact', async () => {
    const { trains } = await new MockPredictionClient().getPredictions('EMBR', '0');
    render(<TrainTimetable state="ready" trains={trains} selectedId={null} onSelect={() => {}} />);

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
